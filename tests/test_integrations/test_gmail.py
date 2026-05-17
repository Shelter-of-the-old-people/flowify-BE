import base64
from email import message_from_bytes
from email.header import Header, decode_header, make_header
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
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
    async def test_get_message_marks_attachment_metadata(self, gmail):
        with patch.object(gmail, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "id": "msg_1",
                "payload": {
                    "headers": [],
                    "parts": [
                        {
                            "filename": "report.pdf",
                            "mimeType": "application/pdf",
                            "headers": [
                                {
                                    "name": "Content-Disposition",
                                    "value": 'attachment; filename="report.pdf"',
                                }
                            ],
                            "body": {"attachmentId": "att_1", "size": 123},
                        },
                        {
                            "filename": "logo.png",
                            "mimeType": "image/png",
                            "headers": [
                                {
                                    "name": "Content-Disposition",
                                    "value": 'inline; filename="logo.png"',
                                }
                            ],
                            "body": {"attachmentId": "att_inline", "size": 10},
                        },
                    ],
                },
            }

            result = await gmail.get_message("token", "msg_1")

        assert result["attachments"][0]["source_service"] == "gmail"
        assert result["attachments"][0]["message_id"] == "msg_1"
        assert result["attachments"][0]["attachment_id"] == "att_1"
        assert result["attachments"][0]["inline"] is False
        assert result["attachments"][1]["inline"] is True

    @pytest.mark.asyncio
    async def test_download_attachment_bytes_decodes_base64url(self, gmail):
        encoded = base64.urlsafe_b64encode("본문".encode()).decode().rstrip("=")
        with patch.object(gmail, "_request", new_callable=AsyncMock, return_value={"data": encoded}):
            result = await gmail.download_attachment_bytes("token", "msg_1", "att_1")

        assert result == "본문".encode()

    @pytest.mark.asyncio
    async def test_extract_attachment_text_disabled_does_not_download(self, gmail):
        with patch.object(gmail, "download_attachment_bytes", new_callable=AsyncMock) as mock_download:
            result = await gmail.extract_attachment_text(
                "token",
                message_id="msg_1",
                attachment_id="att_1",
                mime_type="text/plain",
                filename="note.txt",
            )

        assert result["content_status"] == "unsupported"
        assert result["content_metadata"]["source_service"] == "gmail"
        assert result["content_metadata"]["message_id"] == "msg_1"
        assert result["content_metadata"]["attachment_id"] == "att_1"
        mock_download.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_extract_attachment_text_uses_common_extractor(self, gmail, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_GMAIL_ATTACHMENT_EXTRACTION", True)

        with (
            patch.object(gmail, "download_attachment_bytes", new_callable=AsyncMock, return_value=b"hello"),
            patch(
                "app.services.integrations.google_drive.GoogleDriveService.extract_file_text_from_bytes",
                new_callable=AsyncMock,
                return_value={
                    "content": "hello",
                    "text": "hello",
                    "status": "success",
                    "content_status": "available",
                    "content_error": None,
                    "content_metadata": {"extraction_method": "plain_text"},
                },
            ) as mock_extract,
        ):
            result = await gmail.extract_attachment_text(
                "token",
                message_id="msg_1",
                attachment_id="att_1",
                mime_type="text/plain",
                filename="note.txt",
                file_size=5,
            )

        assert result["content"] == "hello"
        mock_extract.assert_awaited_once_with(
            b"hello",
            "text/plain",
            filename="note.txt",
            file_size=5,
            extraction_action=None,
            metadata={
                "source_service": "gmail",
                "message_id": "msg_1",
                "attachment_id": "att_1",
                "inline": False,
            },
        )

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
