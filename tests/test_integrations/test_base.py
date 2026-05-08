from unittest.mock import AsyncMock, patch

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
            result = await BaseIntegrationService._request(
                "GET", "https://api.test.com", "token123"
            )
            assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_401_raises_oauth_invalid(self):
        resp = _mock_response(401)

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(FlowifyException) as exc_info:
                await BaseIntegrationService._request("GET", "https://api.test.com", "bad_token")
            assert exc_info.value.error_code == ErrorCode.OAUTH_TOKEN_INVALID

    @pytest.mark.asyncio
    async def test_403_scope_error_raises_oauth_scope_insufficient(self):
        resp = _mock_response(
            403,
            {
                "error": {
                    "code": 403,
                    "message": "Request had insufficient authentication scopes.",
                    "status": "PERMISSION_DENIED",
                    "details": [
                        {
                            "reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
                            "metadata": {"service": "gmail.googleapis.com"},
                        }
                    ],
                }
            },
        )

        with (
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp),
            pytest.raises(FlowifyException) as exc_info,
        ):
            await BaseIntegrationService._request("GET", "https://gmail.test.com", "token")

        assert exc_info.value.error_code == ErrorCode.OAUTH_SCOPE_INSUFFICIENT
        assert exc_info.value.context["status"] == 403
        assert exc_info.value.context["provider_error"]["error"]["status"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_429_raises_external_rate_limited(self):
        resp = _mock_response(
            429,
            {
                "error": {
                    "code": 429,
                    "message": "Quota exceeded.",
                    "status": "RESOURCE_EXHAUSTED",
                }
            },
        )

        with (
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp),
            pytest.raises(FlowifyException) as exc_info,
        ):
            await BaseIntegrationService._request("GET", "https://gmail.test.com", "token")

        assert exc_info.value.error_code == ErrorCode.EXTERNAL_RATE_LIMITED
        assert exc_info.value.context["status"] == 429

    @pytest.mark.asyncio
    async def test_5xx_retries_then_raises(self):
        resp = _mock_response(503)

        with (
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp),
            patch("asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(FlowifyException) as exc_info,
        ):
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

        with (
            patch("httpx.AsyncClient.request", side_effect=counting_request),
            pytest.raises(FlowifyException),
        ):
            await BaseIntegrationService._request("GET", "https://api.test.com", "token")
        assert call_count == 1  # 재시도 없음

    @pytest.mark.asyncio
    async def test_connect_error_retries(self):
        with (
            patch(
                "httpx.AsyncClient.request",
                new_callable=AsyncMock,
                side_effect=httpx.ConnectError("Connection refused"),
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(FlowifyException) as exc_info:
                await BaseIntegrationService._request("GET", "https://api.test.com", "token")
            assert exc_info.value.error_code == ErrorCode.EXTERNAL_API_ERROR
