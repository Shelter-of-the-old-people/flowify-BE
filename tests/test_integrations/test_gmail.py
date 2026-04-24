import base64
from unittest.mock import AsyncMock, patch

import pytest

from app.services.integrations.gmail import GmailService


@pytest.fixture()
def gmail():
    return GmailService()


class TestGmailService:
    @pytest.mark.asyncio
    async def test_get_message(self, gmail):
        body_text = "Hello, World!"
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

        with patch.object(gmail, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "id": "msg_1",
                "snippet": "Hello...",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Test Subject"},
                        {"name": "From", "value": "sender@test.com"},
                        {"name": "To", "value": "me@test.com"},
                        {"name": "Date", "value": "2026-04-15"},
                    ],
                    "body": {"data": encoded_body},
                },
            }

            result = await gmail.get_message("token", "msg_1")
            assert result["subject"] == "Test Subject"
            assert result["from"] == "sender@test.com"
            assert result["body"] == body_text

    @pytest.mark.asyncio
    async def test_send_message(self, gmail):
        with patch.object(gmail, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"id": "sent_1", "labelIds": ["SENT"]}
            result = await gmail.send_message("token", "to@test.com", "Subject", "Body")
            assert result["id"] == "sent_1"
            # raw 필드가 base64 인코딩되어 전송되는지 확인
            call_kwargs = mock_req.call_args
            assert "raw" in call_kwargs.kwargs.get("json", {}) or "raw" in (
                call_kwargs[1].get("json", {}) if len(call_kwargs) > 1 else {}
            )

    @pytest.mark.asyncio
    async def test_list_messages(self, gmail):
        with patch.object(gmail, "_request", new_callable=AsyncMock) as mock_req:
            # list 호출 → 메시지 ID 목록 반환
            mock_req.return_value = {"messages": [{"id": "msg_1"}, {"id": "msg_2"}]}
            # get_message도 mock
            with patch.object(gmail, "get_message", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {"id": "msg_1", "subject": "Test"}
                result = await gmail.list_messages("token", query="is:unread", max_results=2)
                assert len(result) == 2
