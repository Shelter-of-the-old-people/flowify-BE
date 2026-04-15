from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.base import BaseIntegrationService


def _mock_response(status_code=200, json_data=None, content_type="application/json"):
    resp = httpx.Response(
        status_code=status_code,
        request=httpx.Request("GET", "https://test.com"),
        json=json_data,
        headers={"content-type": content_type},
    )
    return resp


class TestBaseIntegrationService:
    @pytest.mark.asyncio
    async def test_successful_request(self):
        resp = _mock_response(200, {"ok": True})

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp):
            result = await BaseIntegrationService._request("GET", "https://api.test.com", "token123")
            assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_401_raises_oauth_invalid(self):
        resp = _mock_response(401)

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(FlowifyException) as exc_info:
                await BaseIntegrationService._request("GET", "https://api.test.com", "bad_token")
            assert exc_info.value.error_code == ErrorCode.OAUTH_TOKEN_INVALID

    @pytest.mark.asyncio
    async def test_5xx_retries_then_raises(self):
        resp = _mock_response(503)

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(FlowifyException) as exc_info:
                    await BaseIntegrationService._request("GET", "https://api.test.com", "token")
                assert exc_info.value.error_code == ErrorCode.EXTERNAL_API_ERROR

    @pytest.mark.asyncio
    async def test_4xx_does_not_retry(self):
        resp = _mock_response(400)
        call_count = 0

        async def counting_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return resp

        with patch("httpx.AsyncClient.request", side_effect=counting_request):
            with pytest.raises(FlowifyException):
                await BaseIntegrationService._request("GET", "https://api.test.com", "token")
        assert call_count == 1  # 재시도 없음

    @pytest.mark.asyncio
    async def test_connect_error_retries(self):
        with patch(
            "httpx.AsyncClient.request",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(FlowifyException) as exc_info:
                    await BaseIntegrationService._request("GET", "https://api.test.com", "token")
                assert exc_info.value.error_code == ErrorCode.EXTERNAL_API_ERROR
