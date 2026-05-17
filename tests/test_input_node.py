"""InputNodeStrategy v2 테스트.

v2 시그니처: execute(node: dict, input_data: dict | None, service_tokens: dict) -> dict
runtime_source 기반 라우팅. canonical payload 반환.
conftest.py의 service_tokens fixture 사용 가능.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.google_sheets_common import hash_record
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
        mock_drive.get_file_metadata = AsyncMock(
            return_value={
                "id": "file_123",
                "name": "report.txt",
                "mimeType": "text/plain",
                "size": "10",
                "createdTime": "2026-05-04T12:00:00Z",
                "modifiedTime": "2026-05-04T12:10:00Z",
                "webViewLink": "https://drive.google.com/file/d/file_123/view",
            }
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result | {"content_metadata": {}} == {
        "type": "SINGLE_FILE",
        "source_service": "google_drive",
        "file_id": "file_123",
        "filename": "report.txt",
        "content": None,
        "content_status": "not_requested",
        "content_error": None,
        "content_metadata": {},
        "extracted_text": None,
        "extraction_status": "not_requested",
        "mime_type": "text/plain",
        "size": "10",
        "created_time": "2026-05-04T12:00:00Z",
        "modified_time": "2026-05-04T12:10:00Z",
        "url": "https://drive.google.com/file/d/file_123/view",
    }
    mock_drive.get_file_metadata.assert_awaited_once_with(
        service_tokens["google_drive"], "file_123"
    )


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
    assert [item["content_status"] for item in result["items"]] == [
        "not_requested",
        "not_requested",
    ]
    assert result["items"][0]["filename"] == "a.txt"
    assert result["items"][1]["filename"] == "b.pdf"
    mock_drive.list_files.assert_awaited_once_with(
        service_tokens["google_drive"], folder_id="folder_123", include_folders=False
    )


async def test_google_drive_folder_new_file_reads_latest_created_file(service_tokens: dict) -> None:
    """folder_new_file uses latest-created file metadata and downloads that file."""
    strategy = InputNodeStrategy({})
    node = _source_node("google_drive", "folder_new_file", "folder_123")

    with patch("app.core.nodes.input_node.GoogleDriveService") as mock_drive_class:
        mock_drive = mock_drive_class.return_value
        mock_drive.list_files = AsyncMock(
            return_value=[
                {
                    "id": "file_latest",
                    "name": "latest.pdf",
                    "mimeType": "application/pdf",
                    "createdTime": "2026-05-04T12:00:00Z",
                    "modifiedTime": "2026-05-04T12:10:00Z",
                }
            ]
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result | {"content_metadata": {}} == {
        "type": "SINGLE_FILE",
        "source_service": "google_drive",
        "file_id": "file_latest",
        "filename": "latest.pdf",
        "content": None,
        "content_status": "not_requested",
        "content_error": None,
        "content_metadata": {},
        "extracted_text": None,
        "extraction_status": "not_requested",
        "mime_type": "application/pdf",
        "size": None,
        "created_time": "2026-05-04T12:00:00Z",
        "modified_time": "2026-05-04T12:10:00Z",
        "url": "https://drive.google.com/file/d/file_latest",
    }
    mock_drive.list_files.assert_awaited_once_with(
        service_tokens["google_drive"],
        folder_id="folder_123",
        max_results=1,
        order_by="createdTime desc",
        include_folders=False,
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
                    "id": "msg_1",
                    "threadId": "thread_1",
                    "subject": "테스트 메일",
                    "from": "sender@example.com",
                    "to": ["me@example.com"],
                    "date": "2026-04-24",
                    "body": "본문",
                    "bodyPreview": "본문",
                    "labels": ["INBOX"],
                }
            ]
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result == {
        "type": "SINGLE_EMAIL",
        "email": {
            "id": "msg_1",
            "threadId": "thread_1",
            "subject": "테스트 메일",
            "from": "sender@example.com",
            "sender": "sender@example.com",
            "to": ["me@example.com"],
            "date": "2026-04-24",
            "body": "본문",
            "bodyPreview": "본문",
            "labels": ["INBOX"],
            "attachments": [],
        },
        "id": "msg_1",
        "threadId": "thread_1",
        "subject": "테스트 메일",
        "from": "sender@example.com",
        "sender": "sender@example.com",
        "to": ["me@example.com"],
        "date": "2026-04-24",
        "body": "본문",
        "bodyPreview": "본문",
        "labels": ["INBOX"],
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
                    "id": "msg_1",
                    "threadId": "thread_1",
                    "subject": "메일 1",
                    "from": "a@example.com",
                    "date": "2026-04-24",
                    "body": "첫 번째",
                    "bodyPreview": "첫 번째",
                    "labels": ["INBOX"],
                },
                {
                    "id": "msg_2",
                    "threadId": "thread_2",
                    "subject": "메일 2",
                    "from": "b@example.com",
                    "date": "2026-04-25",
                    "body": "두 번째",
                    "bodyPreview": "두 번째",
                    "labels": ["IMPORTANT"],
                },
            ]
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result["type"] == "EMAIL_LIST"
    expected_emails = [
        {
            "id": "msg_1",
            "threadId": "thread_1",
            "subject": "메일 1",
            "from": "a@example.com",
            "sender": "a@example.com",
            "to": [],
            "date": "2026-04-24",
            "body": "",
            "bodyPreview": "첫 번째",
            "labels": ["INBOX"],
            "attachments": [],
        },
        {
            "id": "msg_2",
            "threadId": "thread_2",
            "subject": "메일 2",
            "from": "b@example.com",
            "sender": "b@example.com",
            "to": [],
            "date": "2026-04-25",
            "body": "",
            "bodyPreview": "두 번째",
            "labels": ["IMPORTANT"],
            "attachments": [],
        },
    ]
    assert result["emails"] == expected_emails
    assert result["items"] == expected_emails
    assert result["metadata"] == {
        "count": 2,
        "truncated": False,
        "sourceMode": "label_emails",
    }
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

    assert result == {
        "type": "EMAIL_LIST",
        "emails": [],
        "items": [],
        "metadata": {
            "count": 0,
            "truncated": False,
            "sourceMode": "label_emails",
        },
    }
    mock_gmail.list_messages.assert_awaited_once_with(
        service_tokens["gmail"], query="label:IMPORTANT", max_results=100
    )


# ── Removed services ─────────────────────────────────────────────


async def test_removed_slack_source_raises_unsupported() -> None:
    """기존 workflow에 남은 Slack source는 API 호출 없이 unsupported로 실패합니다."""
    strategy = InputNodeStrategy({})
    node = _source_node("slack", "channel_messages", "C123")

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(node, None, {})

    assert exc_info.value.error_code == ErrorCode.UNSUPPORTED_RUNTIME_SOURCE


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
        "spreadsheet_id": "sheet_123",
        "headers": ["name", "age"],
        "rows": [["Alice", 30], ["Bob", 25]],
        "sheet_name": "Sheet1",
        "metadata": {"mode": "sheet_all", "row_count": 2},
    }
    mock_sheets.read_range.assert_awaited_once_with(
        service_tokens["google_sheets"], "sheet_123", "Sheet1"
    )


async def test_sheets_new_row_first_run_skips_existing(service_tokens: dict) -> None:
    strategy = InputNodeStrategy({})
    node = {
        "runtime_source": {
            "service": "google_sheets",
            "mode": "new_row",
            "target": "sheet_123",
            "canonical_input_type": "SPREADSHEET_DATA",
            "config": {
                "spreadsheet_id": "sheet_123",
                "sheet_name": "Responses",
                "initial_sync_mode": "skip_existing",
            },
        }
    }

    with patch("app.core.nodes.input_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[["id", "status"], ["a", "open"], ["b", "done"]]
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result["rows"] == []
    assert result["node_state_update"] == {
        "service": "google_sheets",
        "state": {"last_seen_row_index": 2},
    }


async def test_sheets_row_updated_returns_changed_rows(service_tokens: dict) -> None:
    strategy = InputNodeStrategy({})
    unchanged_hash = hash_record({"id": "b", "status": "done"})
    node = {
        "runtime_source": {
            "service": "google_sheets",
            "mode": "row_updated",
            "target": "sheet_123",
            "canonical_input_type": "SPREADSHEET_DATA",
            "config": {
                "spreadsheet_id": "sheet_123",
                "sheet_name": "Responses",
                "key_column": "id",
            },
            "state": {"row_snapshot": {"a": "old-hash", "b": unchanged_hash}},
        }
    }

    with patch("app.core.nodes.input_node.GoogleSheetsService") as mock_sheets_class:
        mock_sheets = mock_sheets_class.return_value
        mock_sheets.read_range = AsyncMock(
            return_value=[["id", "status"], ["a", "open"], ["b", "done"]]
        )

        result = await strategy.execute(node, None, service_tokens)

    assert result["rows"] == [["a", "open"]]
    assert result["node_state_update"]["service"] == "google_sheets"
    assert result["node_state_update"]["state"]["last_seen_row_index"] == 2
    assert "a" in result["node_state_update"]["state"]["row_snapshot"]


# ── 에러 케이스 ──────────────────────────────────────────────────


async def test_missing_token_raises_oauth_error() -> None:
    """서비스 토큰이 없으면 OAuth 토큰 에러를 발생시킵니다."""
    strategy = InputNodeStrategy({})
    node = _source_node("gmail", "new_email")

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(node, None, {})

    assert exc_info.value.error_code == ErrorCode.OAUTH_TOKEN_INVALID


async def test_web_news_seboard_posts_runs_without_token() -> None:
    """web_news source returns ARTICLE_LIST without OAuth token."""
    strategy = InputNodeStrategy({})
    node = _source_node("web_news", "seboard_posts", "2")
    node["config"] = {"maxResults": 3, "includeContent": True}

    with patch("app.core.nodes.input_node.WebNewsService") as mock_web_news_class:
        mock_web_news = mock_web_news_class.return_value
        mock_web_news.fetch_articles = AsyncMock(
            return_value={
                "type": "ARTICLE_LIST",
                "items": [{"id": "123", "title": "Release note"}],
                "metadata": {"provider": "seboard", "count": 1},
            }
        )

        result = await strategy.execute(node, None, {})

    assert result["type"] == "ARTICLE_LIST"
    assert result["items"][0]["title"] == "Release note"
    mock_web_news.fetch_articles.assert_awaited_once_with(
        "seboard_posts",
        "2",
        limit=3,
        include_content=True,
        keyword=None,
    )


async def test_web_news_seboard_new_posts_reuses_seboard_fetch() -> None:
    """SE Board 신규 공지 mode는 기존 SE Board 목록 조회를 재사용합니다."""
    strategy = InputNodeStrategy({})
    node = _source_node("web_news", "seboard_new_posts", "2")

    with patch("app.core.nodes.input_node.WebNewsService") as mock_web_news_class:
        mock_web_news = mock_web_news_class.return_value
        mock_web_news.fetch_articles = AsyncMock(
            return_value={
                "type": "ARTICLE_LIST",
                "items": [{"id": "123", "title": "Release note"}],
                "metadata": {"provider": "seboard", "count": 1},
            }
        )

        result = await strategy.execute(node, None, {})

    assert result["type"] == "ARTICLE_LIST"
    assert strategy.validate(node) is True
    mock_web_news.fetch_articles.assert_awaited_once_with(
        "seboard_posts",
        "2",
        limit=10,
        include_content=False,
        keyword=None,
    )


async def test_web_news_website_feed_runs_without_token() -> None:
    """website_feed source returns ARTICLE_LIST without OAuth token."""
    strategy = InputNodeStrategy({})
    node = _source_node("web_news", "website_feed", "https://example.com")
    node["config"] = {"maxResults": 2}

    with patch("app.core.nodes.input_node.WebNewsService") as mock_web_news_class:
        mock_web_news = mock_web_news_class.return_value
        mock_web_news.fetch_articles = AsyncMock(
            return_value={
                "type": "ARTICLE_LIST",
                "items": [{"id": "post-1", "title": "RSS release"}],
                "metadata": {"provider": "rss", "count": 1},
            }
        )

        result = await strategy.execute(node, None, {})

    assert result["type"] == "ARTICLE_LIST"
    assert result["items"][0]["title"] == "RSS release"
    assert strategy.validate(node) is True
    mock_web_news.fetch_articles.assert_awaited_once_with(
        "website_feed",
        "https://example.com",
        limit=2,
        include_content=False,
        keyword=None,
    )


async def test_web_news_website_feed_uses_multiple_targets() -> None:
    """website_feed source uses targets config when multiple sources are selected."""
    strategy = InputNodeStrategy({})
    node = _source_node("web_news", "website_feed", "https://a.example.com")
    node["config"] = {
        "maxResults": 3,
        "targets": [
            "https://a.example.com",
            "https://b.example.com",
            "https://a.example.com",
        ],
    }

    with patch("app.core.nodes.input_node.WebNewsService") as mock_web_news_class:
        mock_web_news = mock_web_news_class.return_value
        mock_web_news.fetch_articles_from_sources = AsyncMock(
            return_value={
                "type": "ARTICLE_LIST",
                "items": [{"id": "post-1", "title": "Merged"}],
                "metadata": {"provider": "rss", "count": 1},
            }
        )

        result = await strategy.execute(node, None, {})

    assert result["type"] == "ARTICLE_LIST"
    mock_web_news.fetch_articles_from_sources.assert_awaited_once_with(
        "website_feed",
        ["https://a.example.com", "https://b.example.com"],
        limit=3,
        include_content=False,
        keyword=None,
    )
    mock_web_news.fetch_articles.assert_not_called()


async def test_web_news_website_feed_passes_keyword() -> None:
    """website_feed source passes keyword filter to RSS runtime."""
    strategy = InputNodeStrategy({})
    node = _source_node("web_news", "website_feed", "https://example.com")
    node["config"] = {"maxResults": 2, "keyword": " 교육 "}

    with patch("app.core.nodes.input_node.WebNewsService") as mock_web_news_class:
        mock_web_news = mock_web_news_class.return_value
        mock_web_news.fetch_articles = AsyncMock(
            return_value={
                "type": "ARTICLE_LIST",
                "items": [{"id": "post-1", "title": "교육 소식"}],
                "metadata": {"provider": "rss", "count": 1},
            }
        )

        result = await strategy.execute(node, None, {})

    assert result["type"] == "ARTICLE_LIST"
    mock_web_news.fetch_articles.assert_awaited_once_with(
        "website_feed",
        "https://example.com",
        limit=2,
        include_content=False,
        keyword="교육",
    )


async def test_naver_news_article_search_runs_without_token() -> None:
    """naver_news source returns ARTICLE_LIST without OAuth token."""
    strategy = InputNodeStrategy({})
    node = _source_node("naver_news", "article_search", "인공지능")
    node["config"] = {"maxResults": 2}

    with patch("app.core.nodes.input_node.NaverNewsService") as mock_naver_news_class:
        mock_naver_news = mock_naver_news_class.return_value
        mock_naver_news.search_articles = AsyncMock(
            return_value={
                "type": "ARTICLE_LIST",
                "items": [{"id": "news-1", "title": "AI news"}],
                "metadata": {"provider": "naver_news", "count": 1},
            }
        )

        result = await strategy.execute(node, None, {})

    assert result["type"] == "ARTICLE_LIST"
    assert result["items"][0]["title"] == "AI news"
    assert strategy.validate(node) is True
    mock_naver_news.search_articles.assert_awaited_once_with(
        "인공지능",
        limit=2,
    )


async def test_naver_news_new_articles_uses_news_search() -> None:
    """네이버 신규 기사 mode는 최신 뉴스 검색 adapter를 사용합니다."""
    strategy = InputNodeStrategy({})
    node = _source_node("naver_news", "new_articles", "AI")

    with patch("app.core.nodes.input_node.NaverNewsService") as mock_naver_news_class:
        mock_naver_news = mock_naver_news_class.return_value
        mock_naver_news.search_articles = AsyncMock(
            return_value={
                "type": "ARTICLE_LIST",
                "items": [{"id": "news-1", "title": "AI news"}],
                "metadata": {"provider": "naver_news", "count": 1},
            }
        )

        result = await strategy.execute(node, None, {})

    assert result["type"] == "ARTICLE_LIST"
    assert strategy.validate(node) is True
    mock_naver_news.search_articles.assert_awaited_once_with(
        "AI",
        limit=10,
    )


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
                            "id": "gmail-msg_1:a1",
                            "name": "agenda.pdf",
                            "filename": "agenda.pdf",
                            "mimeType": "application/pdf",
                            "mime_type": "application/pdf",
                            "size": 512,
                            "source": "gmail",
                            "messageId": "msg_1",
                            "attachmentId": "a1",
                            "content": None,
                            "downloadUrl": None,
                            "url": "https://gmail.googleapis.com/gmail/v1/users/me/messages/msg_1/attachments/a1",
                        }
                    ],
                }
            ]
        )

        result = await strategy.execute(node, None, service_tokens)

    expected_files = [
        {
            "id": "gmail-msg_1:a1",
            "name": "agenda.pdf",
            "filename": "agenda.pdf",
            "mimeType": "application/pdf",
            "mime_type": "application/pdf",
            "size": 512,
            "source": "gmail",
            "source_service": "gmail",
            "messageId": "msg_1",
            "message_id": "msg_1",
            "attachmentId": "a1",
            "attachment_id": "a1",
            "inline": False,
            "content": None,
            "content_status": "not_requested",
            "content_error": None,
            "content_metadata": {
                "extraction_method": "none",
                "content_kind": "none",
                "truncated": False,
                "char_count": 0,
                "original_char_count": 0,
                "limits": {
                    "max_download_bytes": 10485760,
                    "max_extracted_chars": 60000,
                    "max_llm_input_chars": 60000,
                },
            },
            "extracted_text": None,
            "extraction_status": "not_requested",
            "downloadUrl": None,
            "url": "https://gmail.googleapis.com/gmail/v1/users/me/messages/msg_1/attachments/a1",
        }
    ]
    assert result == {
        "type": "FILE_LIST",
        "files": expected_files,
        "items": expected_files,
        "metadata": {
            "count": 1,
            "truncated": False,
        },
    }
    mock_gmail.list_messages.assert_awaited_once_with(
        service_tokens["gmail"], query="has:attachment", max_results=1
    )
