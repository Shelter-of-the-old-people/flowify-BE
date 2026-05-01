"""OutputNodeStrategy v2 tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.output_node import OutputNodeStrategy


def _sink_node(service: str, **config) -> dict:
    return {"runtime_sink": {"service": service, "config": config}}


async def test_slack_send_text(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node("slack", channel="#test")
    input_data = {"type": "TEXT", "content": "Hello Slack"}

    with patch("app.core.nodes.output_node.SlackService") as mock_slack_class:
        mock_slack = mock_slack_class.return_value
        mock_slack.send_message = AsyncMock(return_value={"ok": True, "ts": "1.23"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "slack",
        "detail": {"ok": True, "ts": "1.23"},
    }
    mock_slack.send_message.assert_awaited_once_with(
        service_tokens["slack"], "#test", "Hello Slack"
    )


async def test_gmail_send_text(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "gmail",
        to="receiver@example.com",
        subject="Flowify",
        action="send",
    )
    input_data = {"type": "TEXT", "content": "Mail body"}

    with patch("app.core.nodes.output_node.GmailService") as mock_gmail_class:
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.send_message = AsyncMock(return_value={"id": "msg_123"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "gmail",
        "detail": {"id": "msg_123"},
    }
    mock_gmail.send_message.assert_awaited_once_with(
        service_tokens["gmail"], "receiver@example.com", "Flowify", "Mail body"
    )


async def test_gmail_draft_uses_create_draft(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "gmail",
        to="receiver@example.com",
        subject="Draft subject",
        action="draft",
    )
    input_data = {"type": "TEXT", "content": "Draft body"}

    with patch("app.core.nodes.output_node.GmailService") as mock_gmail_class:
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.create_draft = AsyncMock(return_value={"id": "draft_123"})
        mock_gmail.send_message = AsyncMock()

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "gmail",
        "detail": {"id": "draft_123"},
    }
    mock_gmail.create_draft.assert_awaited_once_with(
        service_tokens["gmail"], "receiver@example.com", "Draft subject", "Draft body"
    )
    mock_gmail.send_message.assert_not_awaited()


async def test_gmail_rejects_single_email_type(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "gmail",
        to="receiver@example.com",
        subject="Forward",
        action="send",
    )

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            node,
            {"type": "SINGLE_EMAIL", "body": "Original body"},
            service_tokens,
        )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_notion_create_page_text(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node("notion", target_type="page", target_id="page_123")
    input_data = {"type": "TEXT", "content": "Notion content"}

    with patch("app.core.nodes.output_node.NotionService") as mock_notion_class:
        mock_notion = mock_notion_class.return_value
        mock_notion.create_page = AsyncMock(return_value={"id": "notion_page"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "notion",
        "detail": {"id": "notion_page"},
    }
    mock_notion.create_page.assert_awaited_once_with(
        service_tokens["notion"], "page_123", "Flowify Output", "Notion content"
    )


async def test_google_calendar_update_schedule_data(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "google_calendar",
        calendar_id="primary",
        event_title_template="Flowify Event",
        action="update",
        event_id="event_123",
    )
    input_data = {
        "type": "SCHEDULE_DATA",
        "items": [
            {
                "title": "Updated meeting",
                "start_time": "2026-04-25T10:00:00+09:00",
                "end_time": "2026-04-25T11:00:00+09:00",
                "location": "Room A",
                "description": "Updated description",
            }
        ],
    }

    with patch("app.core.nodes.output_node.GoogleCalendarService") as mock_calendar_class:
        mock_calendar = mock_calendar_class.return_value
        mock_calendar.update_event = AsyncMock(return_value={"id": "event_123"})
        mock_calendar.create_event = AsyncMock()

        result = await strategy.execute(node, input_data, service_tokens)

    assert result["detail"]["events_updated"] == 1
    mock_calendar.update_event.assert_awaited_once_with(
        service_tokens["google_calendar"],
        "primary",
        "event_123",
        {
            "summary": "Updated meeting",
            "start": {"dateTime": "2026-04-25T10:00:00+09:00"},
            "end": {"dateTime": "2026-04-25T11:00:00+09:00"},
            "location": "Room A",
            "description": "Updated description",
        },
    )
    mock_calendar.create_event.assert_not_awaited()


async def test_google_drive_file_list_uploads_each_item(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node("google_drive", folder_id="folder_123")
    input_data = {
        "type": "FILE_LIST",
        "items": [
            {
                "filename": "a.txt",
                "mime_type": "text/plain",
                "content": "alpha",
            },
            {
                "filename": "b.pdf",
                "mime_type": "application/pdf",
                "size": 20,
                "url": "https://example.com/b.pdf",
            },
        ],
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"%PDF-1.7 binary"
    mock_response.raise_for_status = MagicMock()

    with (
        patch("app.core.nodes.output_node.GoogleDriveService") as mock_drive_class,
        patch("app.core.nodes.output_node.httpx.AsyncClient") as mock_client_class,
    ):
        mock_drive = mock_drive_class.return_value
        mock_drive.upload_file = AsyncMock(
            side_effect=[
                {"id": "drive_1", "name": "a.txt"},
                {"id": "drive_2", "name": "b.pdf"},
            ]
        )
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = await strategy.execute(node, input_data, service_tokens)

    assert result["detail"]["count"] == 2
    assert result["detail"]["uploaded"] == [
        {"id": "drive_1", "name": "a.txt"},
        {"id": "drive_2", "name": "b.pdf"},
    ]
    assert mock_drive.upload_file.await_count == 2
    mock_drive.upload_file.assert_any_await(
        service_tokens["google_drive"], "a.txt", b"alpha", "folder_123", "text/plain"
    )
    url_file_call = mock_drive.upload_file.await_args_list[1]
    assert url_file_call.args == (
        service_tokens["google_drive"],
        "b.pdf",
        b"%PDF-1.7 binary",
        "folder_123",
        "application/pdf",
    )
    mock_client.get.assert_awaited_once_with("https://example.com/b.pdf", headers={})


async def test_google_drive_single_file_downloads_canvas_url(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node("google_drive", folder_id="folder_123")
    input_data = {
        "type": "SINGLE_FILE",
        "filename": "lecture.pdf",
        "mime_type": "application/pdf",
        "content": None,
        "url": "https://canvas.kumoh.ac.kr/files/67890/download?token=abc",
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"canvas-pdf"
    mock_response.raise_for_status = MagicMock()

    with (
        patch("app.core.nodes.output_node.GoogleDriveService") as mock_drive_class,
        patch("app.core.nodes.output_node.httpx.AsyncClient") as mock_client_class,
    ):
        mock_drive = mock_drive_class.return_value
        mock_drive.upload_file = AsyncMock(return_value={"id": "drive_1", "name": "lecture.pdf"})
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "google_drive",
        "detail": {"id": "drive_1", "name": "lecture.pdf"},
    }
    mock_client.get.assert_awaited_once_with(
        "https://canvas.kumoh.ac.kr/files/67890/download?token=abc",
        headers={"Authorization": f"Bearer {service_tokens['canvas_lms']}"},
    )
    mock_drive.upload_file.assert_awaited_once_with(
        service_tokens["google_drive"],
        "lecture.pdf",
        b"canvas-pdf",
        "folder_123",
        "application/pdf",
    )


async def test_google_drive_spreadsheet_data_uploads_csv(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node("google_drive", folder_id="folder_123")
    input_data = {
        "type": "SPREADSHEET_DATA",
        "headers": ["name", "score"],
        "rows": [["Alice", 95], ["Bob", 82]],
        "sheet_name": "Scores",
    }

    with patch("app.core.nodes.output_node.GoogleDriveService") as mock_drive_class:
        mock_drive = mock_drive_class.return_value
        mock_drive.upload_file = AsyncMock(return_value={"id": "csv_1", "name": "Scores.csv"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "google_drive",
        "detail": {"id": "csv_1", "name": "Scores.csv"},
    }
    mock_drive.upload_file.assert_awaited_once_with(
        service_tokens["google_drive"],
        "Scores.csv",
        b"name,score\r\nAlice,95\r\nBob,82\r\n",
        "folder_123",
        "text/csv",
    )


async def test_unsupported_sink_raises() -> None:
    strategy = OutputNodeStrategy({})

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            _sink_node("unknown_service"),
            {"type": "TEXT", "content": ""},
            {"unknown_service": "token"},
        )

    assert exc_info.value.error_code == ErrorCode.UNSUPPORTED_RUNTIME_SINK


async def test_incompatible_input_type_raises(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            _sink_node("slack", channel="#test"),
            {"type": "SPREADSHEET_DATA", "headers": [], "rows": []},
            service_tokens,
        )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_missing_token_raises() -> None:
    strategy = OutputNodeStrategy({})

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            _sink_node("slack", channel="#test"),
            {"type": "TEXT", "content": "hello"},
            {},
        )

    assert exc_info.value.error_code == ErrorCode.OAUTH_TOKEN_INVALID


def test_validate_supported_sink_returns_true() -> None:
    strategy = OutputNodeStrategy({})

    assert strategy.validate(_sink_node("slack", channel="#test")) is True


def test_validate_missing_required_config_returns_false() -> None:
    strategy = OutputNodeStrategy({})

    assert strategy.validate(_sink_node("slack")) is False
    assert strategy.validate({}) is False
