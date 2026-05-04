"""InputNodeStrategy v2 테스트.

v2 시그니처: execute(node: dict, input_data: dict | None, service_tokens: dict) -> dict
runtime_source 기반 라우팅. canonical payload 반환.
conftest.py의 service_tokens fixture 사용 가능.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.input_node import InputNodeStrategy

# ── 테스트 헬퍼 ──────────────────────────────────────────────────


def _source_node(service: str, mode: str, target: str = "") -> dict:
    """runtime_source가 설정된 노드 dict 생성."""
    return {
        "runtime_source": {
            "service": service,
            "mode": mode,
            "target": target,
            "canonical_input_type": "TEXT",
        }
    }


# ── Google Drive ─────────────────────────────────────────────────


async def test_google_drive_single_file(service_tokens: dict) -> None:
    """Google Drive 단일 파일을 SINGLE_FILE payload로 변환합니다."""
    strategy = InputNodeStrategy({})
    node = _source_node("google_drive", "single_file", "file_123")

    with patch("app.core.nodes.input_node.GoogleDriveService") as mock_drive_class:
        mock_drive = mock_drive_class.return_value
        mock_drive.download_file = AsyncMock(
            return_value={
                "name": "report.txt",
                "content": "hello",
                "mimeType": "text/plain",
            }
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result == {
        "type": "SINGLE_FILE",
        "filename": "report.txt",
        "content": "hello",
        "mime_type": "text/plain",
        "url": "https://drive.google.com/file/d/file_123",
    }
    mock_drive.download_file.assert_awaited_once_with(service_tokens["google_drive"], "file_123")


async def test_google_drive_folder_all_files(service_tokens: dict) -> None:
    """Google Drive 폴더 파일 목록을 FILE_LIST payload로 변환합니다."""
    strategy = InputNodeStrategy({})
    node = _source_node("google_drive", "folder_all_files", "folder_123")

    with patch("app.core.nodes.input_node.GoogleDriveService") as mock_drive_class:
        mock_drive = mock_drive_class.return_value
        mock_drive.list_files = AsyncMock(
            return_value=[
                {
                    "id": "file_1",
                    "name": "a.txt",
                    "mimeType": "text/plain",
                    "size": 12,
                },
                {
                    "id": "file_2",
                    "name": "b.pdf",
                    "mimeType": "application/pdf",
                    "size": 34,
                },
            ]
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result["type"] == "FILE_LIST"
    assert result["items"] == [
        {
            "filename": "a.txt",
            "mime_type": "text/plain",
            "size": 12,
            "url": "https://drive.google.com/file/d/file_1",
        },
        {
            "filename": "b.pdf",
            "mime_type": "application/pdf",
            "size": 34,
            "url": "https://drive.google.com/file/d/file_2",
        },
    ]
    mock_drive.list_files.assert_awaited_once_with(
        service_tokens["google_drive"], folder_id="folder_123"
    )


# ── Gmail ────────────────────────────────────────────────────────


async def test_gmail_new_email(service_tokens: dict) -> None:
    """최신 Gmail 메시지를 SINGLE_EMAIL payload로 변환합니다."""
    strategy = InputNodeStrategy({})
    node = _source_node("gmail", "new_email")

    with patch("app.core.nodes.input_node.GmailService") as mock_gmail_class:
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.list_messages = AsyncMock(
            return_value=[
                {
                    "subject": "테스트 메일",
                    "from": "sender@example.com",
                    "date": "2026-04-24",
                    "body": "본문",
                }
            ]
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result == {
        "type": "SINGLE_EMAIL",
        "subject": "테스트 메일",
        "from": "sender@example.com",
        "date": "2026-04-24",
        "body": "본문",
        "attachments": [],
    }
    mock_gmail.list_messages.assert_awaited_once_with(
        service_tokens["gmail"], query="", max_results=1
    )


async def test_gmail_label_emails(service_tokens: dict) -> None:
    """Gmail 라벨 검색 결과를 EMAIL_LIST payload로 변환합니다."""
    strategy = InputNodeStrategy({})
    node = _source_node("gmail", "label_emails", "work")

    with patch("app.core.nodes.input_node.GmailService") as mock_gmail_class:
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.list_messages = AsyncMock(
            return_value=[
                {
                    "subject": "메일 1",
                    "from": "a@example.com",
                    "date": "2026-04-24",
                    "body": "첫 번째",
                },
                {
                    "subject": "메일 2",
                    "from": "b@example.com",
                    "date": "2026-04-25",
                    "body": "두 번째",
                },
            ]
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result["type"] == "EMAIL_LIST"
    assert result["items"] == [
        {
            "subject": "메일 1",
            "from": "a@example.com",
            "date": "2026-04-24",
            "body": "첫 번째",
        },
        {
            "subject": "메일 2",
            "from": "b@example.com",
            "date": "2026-04-25",
            "body": "두 번째",
        },
    ]
    mock_gmail.list_messages.assert_awaited_once_with(
        service_tokens["gmail"], query="label:work", max_results=20
    )


async def test_gmail_label_emails_uses_configured_max_results(service_tokens: dict) -> None:
    """Gmail label_emails uses node.config.maxResults when it is configured."""
    strategy = InputNodeStrategy({})
    node = _source_node("gmail", "label_emails", "IMPORTANT")
    node["config"] = {"maxResults": 100}

    with patch("app.core.nodes.input_node.GmailService") as mock_gmail_class:
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.list_messages = AsyncMock(return_value=[])

        result = await strategy.execute(node, None, service_tokens)

    assert result == {"type": "EMAIL_LIST", "items": []}
    mock_gmail.list_messages.assert_awaited_once_with(
        service_tokens["gmail"], query="label:IMPORTANT", max_results=100
    )


# ── Slack ────────────────────────────────────────────────────────


async def test_slack_channel_messages(service_tokens: dict) -> None:
    """Slack 채널 메시지를 TEXT payload로 변환합니다."""
    strategy = InputNodeStrategy({})
    node = _source_node("slack", "channel_messages", "C123")

    with patch("app.core.nodes.input_node.SlackService") as mock_slack_class:
        mock_slack = mock_slack_class.return_value
        mock_slack._request = AsyncMock(
            return_value={"messages": [{"text": "hello"}, {"text": "world"}]}
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result == {"type": "TEXT", "content": "hello\nworld"}
    mock_slack._request.assert_awaited_once_with(
        "GET",
        "https://slack.com/api/conversations.history",
        service_tokens["slack"],
        params={"channel": "C123", "limit": 20},
    )


# ── Google Sheets ────────────────────────────────────────────────


async def test_sheets_sheet_all(service_tokens: dict) -> None:
    """Google Sheets 범위를 SPREADSHEET_DATA payload로 변환합니다."""
    strategy = InputNodeStrategy({})
    node = _source_node("google_sheets", "sheet_all", "sheet_123")

    with patch("app.core.nodes.input_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[["name", "age"], ["Alice", 30], ["Bob", 25]]
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result == {
        "type": "SPREADSHEET_DATA",
        "headers": ["name", "age"],
        "rows": [["Alice", 30], ["Bob", 25]],
        "sheet_name": "Sheet1",
    }
    mock_sheets.read_range.assert_awaited_once_with(
        service_tokens["google_sheets"], "sheet_123", "Sheet1"
    )


# ── 에러 케이스 ──────────────────────────────────────────────────


async def test_missing_token_raises_oauth_error() -> None:
    """서비스 토큰이 없으면 OAuth 토큰 에러를 발생시킵니다."""
    strategy = InputNodeStrategy({})
    node = _source_node("gmail", "new_email")

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(node, None, {})

    assert exc_info.value.error_code == ErrorCode.OAUTH_TOKEN_INVALID


async def test_unsupported_source_raises() -> None:
    """지원하지 않는 source는 UNSUPPORTED_RUNTIME_SOURCE를 발생시킵니다."""
    strategy = InputNodeStrategy({})
    node = _source_node("unknown", "new_item")

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(node, None, {"unknown": "token"})

    assert exc_info.value.error_code == ErrorCode.UNSUPPORTED_RUNTIME_SOURCE


# ── validate ─────────────────────────────────────────────────────


def test_validate_supported_source_returns_true() -> None:
    """지원하는 source/mode 조합이면 True를 반환합니다."""
    strategy = InputNodeStrategy({})

    assert strategy.validate(_source_node("gmail", "new_email")) is True


def test_validate_unknown_source_returns_false() -> None:
    """지원하지 않는 source는 False를 반환합니다."""
    strategy = InputNodeStrategy({})

    assert strategy.validate(_source_node("unknown", "new_item")) is False


def test_validate_no_runtime_source_returns_false() -> None:
    """runtime_source가 없으면 False를 반환합니다."""
    strategy = InputNodeStrategy({})

    assert strategy.validate({}) is False


async def test_gmail_attachment_email_returns_file_list_metadata(service_tokens: dict) -> None:
    """attachment_email returns canonical FILE_LIST with attachment metadata."""
    strategy = InputNodeStrategy({})
    node = _source_node("gmail", "attachment_email")

    with patch("app.core.nodes.input_node.GmailService") as mock_gmail_class:
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.list_messages = AsyncMock(
            return_value=[
                {
                    "id": "msg_1",
                    "attachments": [
                        {
                            "filename": "agenda.pdf",
                            "mime_type": "application/pdf",
                            "size": 512,
                            "url": "https://gmail.googleapis.com/gmail/v1/users/me/messages/msg_1/attachments/a1",
                        }
                    ],
                }
            ]
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result == {
        "type": "FILE_LIST",
        "items": [
            {
                "filename": "agenda.pdf",
                "mime_type": "application/pdf",
                "size": 512,
                "url": "https://gmail.googleapis.com/gmail/v1/users/me/messages/msg_1/attachments/a1",
            }
        ],
    }
    mock_gmail.list_messages.assert_awaited_once_with(
        service_tokens["gmail"], query="has:attachment", max_results=1
    )
