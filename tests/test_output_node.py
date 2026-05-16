"""OutputNodeStrategy v2 tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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


async def test_discord_send_text_without_service_token() -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "discord",
        webhook_url="https://discord.com/api/webhooks/test/token",
        username="Flowify",
    )
    input_data = {"type": "TEXT", "content": "Hello Discord"}

    with patch("app.core.nodes.output_node.httpx.AsyncClient") as mock_client_class:
        mock_client = mock_client_class.return_value.__aenter__.return_value
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=204))

        result = await strategy.execute(node, input_data, {})

    assert result == {
        "status": "sent",
        "service": "discord",
        "detail": {"status_code": 204},
    }
    mock_client.post.assert_awaited_once_with(
        "https://discord.com/api/webhooks/test/token",
        json={"content": "Hello Discord", "username": "Flowify"},
    )


async def test_discord_applies_message_template() -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "discord",
        webhook_url="https://discord.com/api/webhooks/test/token",
        message_template="새 요약 결과입니다.\n\n{{content}}",
    )
    input_data = {"type": "TEXT", "content": "요약 본문"}

    with patch("app.core.nodes.output_node.httpx.AsyncClient") as mock_client_class:
        mock_client = mock_client_class.return_value.__aenter__.return_value
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=204))

        await strategy.execute(node, input_data, {})

    mock_client.post.assert_awaited_once_with(
        "https://discord.com/api/webhooks/test/token",
        json={"content": "새 요약 결과입니다.\n\n요약 본문"},
    )


async def test_discord_rejects_empty_webhook_url() -> None:
    strategy = OutputNodeStrategy({})

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            _sink_node("discord", webhook_url=""),
            {"type": "TEXT", "content": "Hello Discord"},
            {},
        )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_discord_rejects_empty_message() -> None:
    strategy = OutputNodeStrategy({})

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            _sink_node("discord", webhook_url="https://discord.com/api/webhooks/test/token"),
            {"type": "TEXT", "content": "  "},
            {},
        )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_discord_rejects_file_list_input() -> None:
    strategy = OutputNodeStrategy({})

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            _sink_node("discord", webhook_url="https://discord.com/api/webhooks/test/token"),
            {"type": "FILE_LIST", "items": []},
            {},
        )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_discord_external_error_raises() -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node("discord", webhook_url="https://discord.com/api/webhooks/test/token")
    input_data = {"type": "TEXT", "content": "Hello Discord"}

    with patch("app.core.nodes.output_node.httpx.AsyncClient") as mock_client_class:
        mock_client = mock_client_class.return_value.__aenter__.return_value
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=400))

        with pytest.raises(FlowifyException) as exc_info:
            await strategy.execute(node, input_data, {})

    assert exc_info.value.error_code == ErrorCode.EXTERNAL_API_ERROR


async def test_discord_network_error_raises_external_api_error() -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node("discord", webhook_url="https://discord.com/api/webhooks/test/token")
    input_data = {"type": "TEXT", "content": "Hello Discord"}

    with patch("app.core.nodes.output_node.httpx.AsyncClient") as mock_client_class:
        mock_client = mock_client_class.return_value.__aenter__.return_value
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection failed"))

        with pytest.raises(FlowifyException) as exc_info:
            await strategy.execute(node, input_data, {})

    assert exc_info.value.error_code == ErrorCode.EXTERNAL_API_ERROR


async def test_google_sheets_update_row_by_key(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "google_sheets",
        spreadsheet_id="sheet_123",
        sheet_name="Results",
        write_mode="update_row_by_key",
        key_column="id",
    )
    input_data = {
        "type": "API_RESPONSE",
        "data": {"id": "2", "status": "done"},
    }

    with patch("app.core.nodes.output_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[
                ["id", "status"],
                ["1", "open"],
                ["2", "pending"],
            ]
        )
        mock_sheets.write_range = AsyncMock(return_value={"updatedRange": "Results!A3:B3"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "google_sheets",
        "detail": {"mode": "update", "updated": 1, "inserted": 0},
    }
    mock_sheets.read_range.assert_awaited_once_with(
        service_tokens["google_sheets"],
        "sheet_123",
        "Results",
    )
    mock_sheets.write_range.assert_awaited_once_with(
        service_tokens["google_sheets"],
        "sheet_123",
        "'Results'!A3:B3",
        [["2", "done"]],
    )


async def test_google_sheets_update_row_by_key_preserves_existing_columns(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "google_sheets",
        spreadsheet_id="sheet_123",
        sheet_name="Results",
        write_mode="update_row_by_key",
        key_column="id",
    )
    input_data = {
        "type": "API_RESPONSE",
        "data": {"id": "2", "status": "done"},
    }

    with patch("app.core.nodes.output_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[
                ["id", "subject", "status"],
                ["1", "alpha", "open"],
                ["2", "beta", "pending"],
            ]
        )
        mock_sheets.write_range = AsyncMock(return_value={"updatedRange": "Results!A3:C3"})

        await strategy.execute(node, input_data, service_tokens)

    mock_sheets.write_range.assert_awaited_once_with(
        service_tokens["google_sheets"],
        "sheet_123",
        "'Results'!A3:C3",
        [["2", "beta", "done"]],
    )


async def test_google_sheets_upsert_row_by_key_appends_when_missing(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "google_sheets",
        spreadsheet_id="sheet_123",
        sheet_name="Results",
        write_mode="upsert_row_by_key",
        key_column="id",
    )
    input_data = {
        "type": "API_RESPONSE",
        "data": {"id": "3", "status": "new"},
    }

    with patch("app.core.nodes.output_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[
                ["id", "status"],
                ["1", "open"],
                ["2", "pending"],
            ]
        )
        mock_sheets.append_rows = AsyncMock(return_value={"updates": {"updatedRows": 1}})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "google_sheets",
        "detail": {"mode": "upsert", "updated": 0, "inserted": 1},
    }
    mock_sheets.append_rows.assert_awaited_once_with(
        service_tokens["google_sheets"],
        "sheet_123",
        "Results",
        [["3", "new"]],
    )


async def test_google_sheets_upsert_row_by_key_preserves_existing_columns_on_update(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "google_sheets",
        spreadsheet_id="sheet_123",
        sheet_name="Results",
        write_mode="upsert_row_by_key",
        key_column="id",
    )
    input_data = {
        "type": "API_RESPONSE",
        "data": {"id": "2", "status": "done"},
    }

    with patch("app.core.nodes.output_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[
                ["id", "subject", "status"],
                ["1", "alpha", "open"],
                ["2", "beta", "pending"],
            ]
        )
        mock_sheets.write_range = AsyncMock(return_value={"updatedRange": "Results!A3:C3"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "google_sheets",
        "detail": {"mode": "upsert", "updated": 1, "inserted": 0},
    }
    mock_sheets.read_range.assert_awaited_once_with(
        service_tokens["google_sheets"],
        "sheet_123",
        "Results",
    )
    mock_sheets.write_range.assert_awaited_once_with(
        service_tokens["google_sheets"],
        "sheet_123",
        "'Results'!A3:C3",
        [["2", "beta", "done"]],
    )


async def test_google_sheets_upsert_row_by_key_reads_full_table_for_a1_range(
    service_tokens: dict,
) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "google_sheets",
        spreadsheet_id="sheet_123",
        sheet_name="Results",
        range_a1="A1",
        write_mode="upsert_row_by_key",
        key_column="message_id",
    )
    input_data = {
        "type": "API_RESPONSE",
        "data": {
            "message_id": "m_2",
            "sender": "user@example.com",
            "subject": "updated",
            "date": "2026-05-12",
        },
    }

    with patch("app.core.nodes.output_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[
                ["message_id", "sender", "subject", "date"],
                ["m_1", "alpha@example.com", "alpha", "2026-05-10"],
                ["m_2", "beta@example.com", "beta", "2026-05-11"],
            ]
        )
        mock_sheets.write_range = AsyncMock(return_value={"updatedRange": "Results!A3:D3"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "google_sheets",
        "detail": {"mode": "upsert", "updated": 1, "inserted": 0},
    }
    mock_sheets.read_range.assert_awaited_once_with(
        service_tokens["google_sheets"],
        "sheet_123",
        "'Results'!A1:ZZZ10000000",
    )
    mock_sheets.write_range.assert_awaited_once_with(
        service_tokens["google_sheets"],
        "sheet_123",
        "'Results'!A3:D3",
        [["m_2", "user@example.com", "updated", "2026-05-12"]],
    )


async def test_google_sheets_update_row_by_key_respects_offset_range(
    service_tokens: dict,
) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "google_sheets",
        spreadsheet_id="sheet_123",
        sheet_name="Results",
        range_a1="B3:D20",
        write_mode="update_row_by_key",
        key_column="id",
    )
    input_data = {
        "type": "API_RESPONSE",
        "data": {"id": "2", "status": "done"},
    }

    with patch("app.core.nodes.output_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[
                ["id", "subject", "status"],
                ["1", "alpha", "open"],
                ["2", "beta", "pending"],
            ]
        )
        mock_sheets.write_range = AsyncMock(return_value={"updatedRange": "Results!B5:D5"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "google_sheets",
        "detail": {"mode": "update", "updated": 1, "inserted": 0},
    }
    mock_sheets.read_range.assert_awaited_once_with(
        service_tokens["google_sheets"],
        "sheet_123",
        "'Results'!B3:D20",
    )
    mock_sheets.write_range.assert_awaited_once_with(
        service_tokens["google_sheets"],
        "sheet_123",
        "'Results'!B5:D5",
        [["2", "beta", "done"]],
    )


async def test_google_sheets_update_row_by_key_requires_existing_target_headers(
    service_tokens: dict,
) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "google_sheets",
        spreadsheet_id="sheet_123",
        sheet_name="Results",
        write_mode="update_row_by_key",
        key_column="id",
    )
    input_data = {
        "type": "API_RESPONSE",
        "data": {"id": "2", "status": "done"},
    }

    with patch("app.core.nodes.output_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(return_value=[])

        with pytest.raises(FlowifyException) as exc_info:
            await strategy.execute(node, input_data, service_tokens)

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
    assert (
        exc_info.value.detail
        == "Google Sheets update_row_by_key requires existing target sheet headers."
    )


async def test_google_sheets_update_row_by_key_requires_key_column_in_incoming_data(
    service_tokens: dict,
) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "google_sheets",
        spreadsheet_id="sheet_123",
        sheet_name="Results",
        write_mode="update_row_by_key",
        key_column="id",
    )
    input_data = {
        "type": "API_RESPONSE",
        "data": {"subject": "missing id"},
    }

    with patch("app.core.nodes.output_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[
                ["id", "subject"],
                ["1", "alpha"],
            ]
        )

        with pytest.raises(FlowifyException) as exc_info:
            await strategy.execute(node, input_data, service_tokens)

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
    assert exc_info.value.detail == "Google Sheets incoming data must include key_column 'id'."


async def test_google_sheets_upsert_row_by_key_rejects_unknown_incoming_columns(
    service_tokens: dict,
) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "google_sheets",
        spreadsheet_id="sheet_123",
        sheet_name="Results",
        write_mode="upsert_row_by_key",
        key_column="id",
    )
    input_data = {
        "type": "API_RESPONSE",
        "data": {"id": "2", "status": "done", "unexpected": "value"},
    }

    with patch("app.core.nodes.output_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[
                ["id", "status"],
                ["1", "open"],
                ["2", "pending"],
            ]
        )

        with pytest.raises(FlowifyException) as exc_info:
            await strategy.execute(node, input_data, service_tokens)

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
    assert exc_info.value.detail == "Google Sheets incoming columns are not present in target sheet."
    assert exc_info.value.context == {"missing_headers": ["unexpected"]}


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
        mock_gmail.send_message = AsyncMock(
            return_value={"id": "msg_123", "threadId": "thread_123"}
        )

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "gmail",
        "detail": {
            "type": "SEND_RESULT",
            "service": "gmail",
            "status": "sent",
            "messageId": "msg_123",
            "threadId": "thread_123",
            "to": ["receiver@example.com"],
            "subject": "Flowify",
        },
    }
    mock_gmail.send_message.assert_awaited_once_with(
        service_tokens["gmail"], "receiver@example.com", "Flowify", "Mail body"
    )


async def test_gmail_send_text_uses_runtime_display_name(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "gmail",
        to="receiver@example.com",
        subject="Flowify",
        action="send",
    )
    node["runtime_context"] = {
        "user_profile": {
            "display_name": "김민호",
            "email": "sender@example.com",
        }
    }
    input_data = {"type": "TEXT", "content": "Mail body"}

    with patch("app.core.nodes.output_node.GmailService") as mock_gmail_class:
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.send_message = AsyncMock(
            return_value={"id": "msg_123", "threadId": "thread_123"}
        )

        await strategy.execute(node, input_data, service_tokens)

    mock_gmail.send_message.assert_awaited_once_with(
        service_tokens["gmail"],
        "receiver@example.com",
        "Flowify",
        "Mail body",
        preferred_display_name="김민호",
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
        mock_gmail.create_draft = AsyncMock(
            return_value={
                "id": "draft_123",
                "message": {"id": "msg_123", "threadId": "thread_123"},
            }
        )
        mock_gmail.send_message = AsyncMock()

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "gmail",
        "detail": {
            "type": "SEND_RESULT",
            "service": "gmail",
            "status": "drafted",
            "messageId": "msg_123",
            "threadId": "thread_123",
            "to": ["receiver@example.com"],
            "subject": "Draft subject",
            "draftId": "draft_123",
        },
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


async def test_gmail_single_file_uses_drive_source_bytes(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "gmail",
        to="receiver@example.com",
        subject="Drive file",
        action="send",
    )
    input_data = {
        "type": "SINGLE_FILE",
        "source_service": "google_drive",
        "file_id": "file_123",
        "filename": "lecture.pdf",
        "mime_type": "application/pdf",
        "content": "stale text should not be attached",
    }

    with (
        patch("app.core.nodes.output_node.GoogleDriveService") as mock_drive_class,
        patch("app.core.nodes.output_node.GmailService") as mock_gmail_class,
    ):
        mock_drive = mock_drive_class.return_value
        mock_drive.download_file_bytes = AsyncMock(return_value=b"%PDF-1.7 real bytes")
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.send_message = AsyncMock(
            return_value={"id": "msg_123", "threadId": "thread_123"}
        )

        result = await strategy.execute(node, input_data, service_tokens)

    assert result["detail"]["messageId"] == "msg_123"
    mock_drive.download_file_bytes.assert_awaited_once_with(
        service_tokens["google_drive"],
        "file_123",
    )
    mock_gmail.send_message.assert_awaited_once_with(
        service_tokens["gmail"],
        "receiver@example.com",
        "Drive file",
        "Attached file: lecture.pdf",
        [
            {
                "filename": "lecture.pdf",
                "mime_type": "application/pdf",
                "content": b"%PDF-1.7 real bytes",
            }
        ],
    )


async def test_gmail_file_list_uses_drive_source_bytes(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "gmail",
        to="receiver@example.com",
        subject="Drive files",
        action="send",
    )
    input_data = {
        "type": "FILE_LIST",
        "items": [
            {
                "source_service": "google_drive",
                "file_id": "file_1",
                "filename": "a.pdf",
                "mime_type": "application/pdf",
                "content": "stale a",
            },
            {
                "source_service": "google_drive",
                "file_id": "file_2",
                "filename": "b.txt",
                "mime_type": "text/plain",
                "content": "stale b",
            },
        ],
    }

    with (
        patch("app.core.nodes.output_node.GoogleDriveService") as mock_drive_class,
        patch("app.core.nodes.output_node.GmailService") as mock_gmail_class,
    ):
        mock_drive = mock_drive_class.return_value
        mock_drive.download_file_bytes = AsyncMock(side_effect=[b"real-pdf", b"real-text"])
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.send_message = AsyncMock(
            return_value={"id": "msg_123", "threadId": "thread_123"}
        )

        await strategy.execute(node, input_data, service_tokens)

    assert mock_drive.download_file_bytes.await_count == 2
    mock_drive.download_file_bytes.assert_any_await(
        service_tokens["google_drive"],
        "file_1",
    )
    mock_drive.download_file_bytes.assert_any_await(
        service_tokens["google_drive"],
        "file_2",
    )
    attachments = mock_gmail.send_message.await_args.args[4]
    assert attachments == [
        {"filename": "a.pdf", "mime_type": "application/pdf", "content": b"real-pdf"},
        {"filename": "b.txt", "mime_type": "text/plain", "content": b"real-text"},
    ]


async def test_gmail_file_list_preserves_content_items(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "gmail",
        to="receiver@example.com",
        subject="Content files",
        action="send",
    )
    input_data = {
        "type": "FILE_LIST",
        "items": [
            {
                "filename": "note.txt",
                "mime_type": "text/plain",
                "content": "hello",
            }
        ],
    }

    with (
        patch("app.core.nodes.output_node.GoogleDriveService") as mock_drive_class,
        patch("app.core.nodes.output_node.GmailService") as mock_gmail_class,
    ):
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.send_message = AsyncMock(
            return_value={"id": "msg_123", "threadId": "thread_123"}
        )

        await strategy.execute(node, input_data, service_tokens)

    mock_drive_class.assert_not_called()
    attachments = mock_gmail.send_message.await_args.args[4]
    assert attachments == [
        {"filename": "note.txt", "mime_type": "text/plain", "content": b"hello"}
    ]


async def test_gmail_drive_file_requires_drive_token(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "gmail",
        to="receiver@example.com",
        subject="Drive file",
        action="send",
    )
    input_data = {
        "type": "SINGLE_FILE",
        "source_service": "google_drive",
        "file_id": "file_123",
        "filename": "lecture.pdf",
        "mime_type": "application/pdf",
    }
    missing_drive_tokens = dict(service_tokens)
    missing_drive_tokens.pop("google_drive")

    with (
        patch("app.core.nodes.output_node.GoogleDriveService") as mock_drive_class,
        patch("app.core.nodes.output_node.GmailService") as mock_gmail_class,
    ):
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.send_message = AsyncMock()

        with pytest.raises(FlowifyException) as exc_info:
            await strategy.execute(node, input_data, missing_drive_tokens)

    assert exc_info.value.error_code == ErrorCode.OAUTH_TOKEN_INVALID
    mock_drive_class.assert_not_called()
    mock_gmail.send_message.assert_not_awaited()


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


async def test_notion_create_page_uses_title_template(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "notion",
        target_type="page",
        target_id="page_123",
        title_template="업로드 기록 - {{filename}}",
    )
    input_data = {
        "type": "TEXT",
        "content": "Summarized content",
        "filename": "latest.pdf",
    }

    with patch("app.core.nodes.output_node.NotionService") as mock_notion_class:
        mock_notion = mock_notion_class.return_value
        mock_notion.create_page = AsyncMock(return_value={"id": "notion_page"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "notion",
        "detail": {"id": "notion_page"},
    }
    create_args = mock_notion.create_page.await_args.args
    assert create_args[0] == service_tokens["notion"]
    assert create_args[1] == "page_123"
    assert create_args[2] == "업로드 기록 - latest.pdf"
    assert create_args[3] == "Summarized content"


async def test_notion_title_template_with_subject(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "notion",
        target_type="page",
        target_id="page_123",
        title_template="메일 요약 - {{date}} - {{subject}}",
    )
    input_data = {
        "type": "TEXT",
        "content": "Notion content",
        "subject": "중요 메일",
    }

    with patch("app.core.nodes.output_node.NotionService") as mock_notion_class:
        mock_notion = mock_notion_class.return_value
        mock_notion.create_page = AsyncMock(return_value={"id": "notion_page"})

        await strategy.execute(node, input_data, service_tokens)

    create_args = mock_notion.create_page.await_args.args
    assert create_args[0] == service_tokens["notion"]
    assert create_args[1] == "page_123"
    assert create_args[2].startswith("메일 요약 - ")
    assert create_args[2].endswith(" - 중요 메일")
    assert create_args[3] == "Notion content"


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


async def test_google_drive_file_list_creates_course_subfolder(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node("google_drive", folder_id="folder_root")
    input_data = {
        "type": "FILE_LIST",
        "items": [
            {
                "filename": "데이터베이스/Week01_Introduction.pdf",
                "mime_type": "application/pdf",
                "url": "https://canvas.kumoh.ac.kr/files/67890/download?token=abc",
            }
        ],
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
        mock_drive.ensure_folder_path = AsyncMock(return_value="course_folder_1")
        mock_drive.upload_file = AsyncMock(
            return_value={"id": "drive_1", "name": "Week01_Introduction.pdf"}
        )
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = await strategy.execute(node, input_data, service_tokens)

    assert result["detail"]["count"] == 1
    mock_drive.ensure_folder_path.assert_awaited_once_with(
        service_tokens["google_drive"],
        "folder_root",
        ["데이터베이스"],
    )
    mock_drive.upload_file.assert_awaited_once_with(
        service_tokens["google_drive"],
        "Week01_Introduction.pdf",
        b"canvas-pdf",
        "course_folder_1",
        "application/pdf",
    )


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


async def test_google_drive_single_file_uses_drive_source_bytes(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node("google_drive", folder_id="folder_123")
    input_data = {
        "type": "SINGLE_FILE",
        "source_service": "google_drive",
        "file_id": "file_123",
        "filename": "lecture.pdf",
        "mime_type": "application/pdf",
        "content": "%PDF raw text should not be uploaded",
        "url": "https://drive.google.com/file/d/file_123",
    }

    with patch("app.core.nodes.output_node.GoogleDriveService") as mock_drive_class:
        mock_drive = mock_drive_class.return_value
        mock_drive.download_file_bytes = AsyncMock(return_value=b"%PDF-1.7 real bytes")
        mock_drive.upload_file = AsyncMock(return_value={"id": "drive_1", "name": "lecture.pdf"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "google_drive",
        "detail": {"id": "drive_1", "name": "lecture.pdf"},
    }
    mock_drive.download_file_bytes.assert_awaited_once_with(
        service_tokens["google_drive"],
        "file_123",
    )
    mock_drive.upload_file.assert_awaited_once_with(
        service_tokens["google_drive"],
        "lecture.pdf",
        b"%PDF-1.7 real bytes",
        "folder_123",
        "application/pdf",
    )


async def test_google_drive_file_list_uses_drive_source_bytes(service_tokens: dict) -> None:
    strategy = OutputNodeStrategy({})
    node = _sink_node("google_drive", folder_id="folder_123")
    input_data = {
        "type": "FILE_LIST",
        "items": [
            {
                "source_service": "google_drive",
                "file_id": "file_1",
                "filename": "a.pdf",
                "mime_type": "application/pdf",
                "content": "%PDF raw text should not be uploaded",
            }
        ],
    }

    with patch("app.core.nodes.output_node.GoogleDriveService") as mock_drive_class:
        mock_drive = mock_drive_class.return_value
        mock_drive.download_file_bytes = AsyncMock(return_value=b"real-pdf")
        mock_drive.upload_file = AsyncMock(return_value={"id": "drive_1", "name": "a.pdf"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result["detail"]["count"] == 1
    mock_drive.download_file_bytes.assert_awaited_once_with(
        service_tokens["google_drive"],
        "file_1",
    )
    mock_drive.upload_file.assert_awaited_once_with(
        service_tokens["google_drive"],
        "a.pdf",
        b"real-pdf",
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
