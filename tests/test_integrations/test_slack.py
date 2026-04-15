from unittest.mock import AsyncMock, patch

import pytest

from app.common.errors import FlowifyException
from app.services.integrations.slack import SlackService


@pytest.fixture()
def slack():
    return SlackService()


class TestSlackService:
    @pytest.mark.asyncio
    async def test_send_message_success(self, slack):
        with patch.object(slack, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"ok": True, "ts": "1234567890.123456"}
            result = await slack.send_message("xoxb-token", "#general", "Hello!")
            assert result["ok"] is True
            mock_req.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_failure(self, slack):
        with patch.object(slack, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"ok": False, "error": "channel_not_found"}
            with pytest.raises(FlowifyException) as exc_info:
                await slack.send_message("xoxb-token", "#nonexistent", "Hello!")
            assert "channel_not_found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_list_channels(self, slack):
        with patch.object(slack, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "ok": True,
                "channels": [
                    {"id": "C01", "name": "general", "is_private": False},
                    {"id": "C02", "name": "random", "is_private": False},
                ],
            }
            result = await slack.list_channels("xoxb-token")
            assert len(result) == 2
            assert result[0]["name"] == "general"
