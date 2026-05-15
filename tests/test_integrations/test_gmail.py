import base64
from email import message_from_bytes
from email.header import Header, decode_header, make_header
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
                "threadId": "thread_1",
                "labelIds": ["INBOX"],
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
        assert result["sender"] == "sender@test.com"
        assert result["to"] == ["me@test.com"]
        assert result["threadId"] == "thread_1"
        assert result["labels"] == ["INBOX"]
        assert result["bodyPreview"] == "Hello..."
        assert result["body"] == body_text

    @pytest.mark.asyncio
    async def test_get_message_decodes_mime_headers(self, gmail):
        body_text = "Hello, World!"
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()
        encoded_subject = Header("테스트 메일", "utf-8").encode()
        encoded_from = f'{Header("김민호", "utf-8").encode()} <sender@test.com>'
        encoded_to = f'{Header("수신자", "utf-8").encode()} <me@test.com>'

        with patch.object(gmail, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "id": "msg_1",
                "threadId": "thread_1",
                "labelIds": ["INBOX"],
                "snippet": "Hello...",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": encoded_subject},
                        {"name": "From", "value": encoded_from},
                        {"name": "To", "value": encoded_to},
                        {"name": "Date", "value": "2026-04-15"},
                    ],
                    "body": {"data": encoded_body},
                },
            }

            result = await gmail.get_message("token", "msg_1")

        assert result["subject"] == "테스트 메일"
        assert result["from"] == "김민호 <sender@test.com>"
        assert result["sender"] == "김민호 <sender@test.com>"
        assert result["to"] == ["me@test.com"]

    @pytest.mark.asyncio
    async def test_send_message(self, gmail):
        with patch.object(gmail, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [
                {
                    "sendAs": [
                        {
                            "sendAsEmail": "sender@test.com",
                            "displayName": "김민호",
                            "isPrimary": True,
                        }
                    ]
                },
                {"id": "sent_1", "labelIds": ["SENT"]},
            ]

            result = await gmail.send_message("token", "to@test.com", "Subject", "Body")

        assert result["id"] == "sent_1"
        assert mock_req.await_count == 2

        send_call = mock_req.await_args_list[1]
        raw = send_call.kwargs["json"]["raw"]
        parsed = message_from_bytes(base64.urlsafe_b64decode(raw))
        decoded_from = str(make_header(decode_header(parsed["From"])))
        assert decoded_from == "김민호 <sender@test.com>"
        assert parsed["To"] == "to@test.com"
        assert parsed["Subject"] == "Subject"

    @pytest.mark.asyncio
    async def test_create_draft_uses_sender_identity_in_from_header(self, gmail):
        with patch.object(gmail, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [
                {
                    "sendAs": [
                        {
                            "sendAsEmail": "sender@test.com",
                            "displayName": "김민호",
                            "isPrimary": True,
                        }
                    ]
                },
                {"id": "draft_1", "message": {"id": "msg_1", "threadId": "thread_1"}},
            ]

            result = await gmail.create_draft("token", "to@test.com", "Subject", "Body")

        assert result["id"] == "draft_1"
        assert mock_req.await_count == 2

        draft_call = mock_req.await_args_list[1]
        raw = draft_call.kwargs["json"]["message"]["raw"]
        parsed = message_from_bytes(base64.urlsafe_b64decode(raw))
        decoded_from = str(make_header(decode_header(parsed["From"])))
        assert decoded_from == "김민호 <sender@test.com>"
        assert parsed["To"] == "to@test.com"
        assert parsed["Subject"] == "Subject"

    @pytest.mark.asyncio
    async def test_send_message_falls_back_to_bare_email_when_display_name_missing(self, gmail):
        with patch.object(gmail, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [
                {
                    "sendAs": [
                        {
                            "sendAsEmail": "sender@test.com",
                            "displayName": "",
                            "isPrimary": True,
                        }
                    ]
                },
                {"id": "sent_1", "labelIds": ["SENT"]},
            ]

            await gmail.send_message("token", "to@test.com", "Subject", "Body")

        send_call = mock_req.await_args_list[1]
        raw = send_call.kwargs["json"]["raw"]
        parsed = message_from_bytes(base64.urlsafe_b64decode(raw))
        assert parsed["From"] == "sender@test.com"

    @pytest.mark.asyncio
    async def test_send_message_falls_back_to_profile_email_when_send_as_lookup_fails(self, gmail):
        with patch.object(gmail, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [
                RuntimeError("sendAs unavailable"),
                {"emailAddress": "sender@test.com"},
                {"id": "sent_1", "labelIds": ["SENT"]},
            ]

            await gmail.send_message("token", "to@test.com", "Subject", "Body")

        assert mock_req.await_count == 3
        send_call = mock_req.await_args_list[2]
        raw = send_call.kwargs["json"]["raw"]
        parsed = message_from_bytes(base64.urlsafe_b64decode(raw))
        assert parsed["From"] == "sender@test.com"

    @pytest.mark.asyncio
    async def test_send_message_prefers_runtime_display_name_over_send_as(self, gmail):
        with patch.object(gmail, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [
                {
                    "sendAs": [
                        {
                            "sendAsEmail": "sender@test.com",
                            "displayName": "Old Name",
                            "isPrimary": True,
                        }
                    ]
                },
                {"id": "sent_1", "labelIds": ["SENT"]},
            ]

            await gmail.send_message(
                "token",
                "to@test.com",
                "Subject",
                "Body",
                preferred_display_name="김민호",
            )

        send_call = mock_req.await_args_list[1]
        raw = send_call.kwargs["json"]["raw"]
        parsed = message_from_bytes(base64.urlsafe_b64decode(raw))
        decoded_from = str(make_header(decode_header(parsed["From"])))
        assert decoded_from == "김민호 <sender@test.com>"

    @pytest.mark.asyncio
    async def test_list_messages(self, gmail):
        with patch.object(gmail, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"messages": [{"id": "msg_1"}, {"id": "msg_2"}]}

            with patch.object(gmail, "get_message", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {"id": "msg_1", "subject": "Test"}
                result = await gmail.list_messages("token", query="is:unread", max_results=2)

        assert len(result) == 2
