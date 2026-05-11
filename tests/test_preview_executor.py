"""WorkflowPreviewExecutor tests."""

from unittest.mock import AsyncMock, patch

from app.core.engine.preview_executor import WorkflowPreviewExecutor
from app.models.workflow import NodeDefinition


def _source_node(service: str, mode: str, target: str = "target_1") -> NodeDefinition:
    return NodeDefinition(
        id="node_source",
        type=service,
        role="start",
        runtime_type="input",
        runtime_source={
            "service": service,
            "mode": mode,
            "target": target,
            "canonical_input_type": "FILE_LIST",
        },
    )


async def test_google_drive_single_file_preview_uses_metadata_only() -> None:
    executor = WorkflowPreviewExecutor()
    node = _source_node("google_drive", "single_file", "file_1")

    with patch("app.core.engine.preview_executor.GoogleDriveService") as mock_drive_class:
        mock_drive = mock_drive_class.return_value
        mock_drive.get_file_metadata = AsyncMock(
            return_value={
                "id": "file_1",
                "name": "report.pdf",
                "mimeType": "application/pdf",
                "size": "1024",
                "createdTime": "2026-05-01T00:00:00Z",
                "modifiedTime": "2026-05-02T00:00:00Z",
                "webViewLink": "https://drive.google.com/file/d/file_1/view",
            }
        )
        mock_drive.extract_file_text = AsyncMock()

        response = await executor.preview_node(
            workflow_id="wf1",
            node_id="node_source",
            nodes=[node],
            service_tokens={"google_drive": "token"},
            limit=5,
            include_content=False,
        )

    assert response.available is True
    assert response.output_data == {
        "type": "SINGLE_FILE",
        "source_service": "google_drive",
        "file_id": "file_1",
        "filename": "report.pdf",
        "content": None,
        "extracted_text": None,
        "extraction_status": "not_requested",
        "mime_type": "application/pdf",
        "size": "1024",
        "created_time": "2026-05-01T00:00:00Z",
        "modified_time": "2026-05-02T00:00:00Z",
        "url": "https://drive.google.com/file/d/file_1/view",
    }
    mock_drive.get_file_metadata.assert_awaited_once_with("token", "file_1")
    mock_drive.extract_file_text.assert_not_called()


async def test_google_drive_single_file_preview_extracts_text_when_requested() -> None:
    executor = WorkflowPreviewExecutor()
    node = _source_node("google_drive", "single_file", "file_1")

    with patch("app.core.engine.preview_executor.GoogleDriveService") as mock_drive_class:
        mock_drive = mock_drive_class.return_value
        mock_drive.get_file_metadata = AsyncMock(
            return_value={
                "id": "file_1",
                "name": "report.pdf",
                "mimeType": "application/pdf",
            }
        )
        mock_drive.extract_file_text = AsyncMock(
            return_value={
                "text": "문서 본문",
                "status": "success",
                "truncated": False,
                "error": None,
            }
        )

        response = await executor.preview_node(
            workflow_id="wf1",
            node_id="node_source",
            nodes=[node],
            service_tokens={"google_drive": "token"},
            limit=5,
            include_content=True,
        )

    assert response.output_data["content"] is None
    assert response.output_data["extracted_text"] == "문서 본문"
    assert response.output_data["extraction_status"] == "success"
    mock_drive.extract_file_text.assert_awaited_once_with("token", "file_1", "application/pdf")


async def test_google_drive_folder_preview_applies_limit() -> None:
    executor = WorkflowPreviewExecutor()
    node = _source_node("google_drive", "folder_all_files", "folder_1")

    with patch("app.core.engine.preview_executor.GoogleDriveService") as mock_drive_class:
        mock_drive = mock_drive_class.return_value
        mock_drive.list_files = AsyncMock(
            return_value=[
                {"id": "file_1", "name": "a.txt", "mimeType": "text/plain"},
                {"id": "file_2", "name": "b.txt", "mimeType": "text/plain"},
            ]
        )

        response = await executor.preview_node(
            workflow_id="wf1",
            node_id="node_source",
            nodes=[node],
            service_tokens={"google_drive": "token"},
            limit=2,
            include_content=False,
        )

    assert response.available is True
    assert response.output_data["type"] == "FILE_LIST"
    assert len(response.output_data["items"]) == 2
    assert response.output_data["truncated"] is True
    assert response.output_data["items"][0]["source_service"] == "google_drive"
    mock_drive.list_files.assert_awaited_once_with(
        "token",
        folder_id="folder_1",
        max_results=2,
        include_folders=False,
    )


async def test_middle_node_preview_is_not_implemented_yet() -> None:
    executor = WorkflowPreviewExecutor()
    node = NodeDefinition(
        id="node_middle",
        type="AI",
        role="middle",
        runtime_type="llm",
    )

    response = await executor.preview_node(
        workflow_id="wf1",
        node_id="node_middle",
        nodes=[node],
        service_tokens={},
        limit=5,
        include_content=False,
    )

    assert response.available is False
    assert response.status == "unavailable"
    assert response.reason == "PREVIEW_NOT_IMPLEMENTED"


async def test_web_news_preview_returns_article_list_without_token() -> None:
    executor = WorkflowPreviewExecutor()
    node = _source_node("web_news", "seboard_posts", "2")

    with patch("app.core.engine.preview_executor.WebNewsService") as mock_web_news_class:
        mock_web_news = mock_web_news_class.return_value
        mock_web_news.fetch_articles = AsyncMock(
            return_value={
                "type": "ARTICLE_LIST",
                "items": [{"id": "123", "title": "Release note"}],
                "metadata": {"provider": "seboard", "count": 1},
            }
        )

        response = await executor.preview_node(
            workflow_id="wf1",
            node_id="node_source",
            nodes=[node],
            service_tokens={},
            limit=5,
            include_content=False,
        )

    assert response.available is True
    assert response.output_data["type"] == "ARTICLE_LIST"
    assert response.output_data["items"][0]["title"] == "Release note"
    mock_web_news.fetch_articles.assert_awaited_once_with(
        "seboard_posts",
        "2",
        limit=5,
        include_content=False,
    )


async def test_web_news_website_feed_preview_returns_article_list_without_token() -> None:
    executor = WorkflowPreviewExecutor()
    node = _source_node("web_news", "website_feed", "https://example.com")

    with patch("app.core.engine.preview_executor.WebNewsService") as mock_web_news_class:
        mock_web_news = mock_web_news_class.return_value
        mock_web_news.fetch_articles = AsyncMock(
            return_value={
                "type": "ARTICLE_LIST",
                "items": [{"id": "post-1", "title": "RSS release"}],
                "metadata": {"provider": "rss", "count": 1},
            }
        )

        response = await executor.preview_node(
            workflow_id="wf1",
            node_id="node_source",
            nodes=[node],
            service_tokens={},
            limit=5,
            include_content=False,
        )

    assert response.available is True
    assert response.output_data["type"] == "ARTICLE_LIST"
    assert response.output_data["items"][0]["title"] == "RSS release"
    mock_web_news.fetch_articles.assert_awaited_once_with(
        "website_feed",
        "https://example.com",
        limit=5,
        include_content=False,
    )


async def test_web_news_new_posts_preview_reuses_seboard_fetch() -> None:
    executor = WorkflowPreviewExecutor()
    node = _source_node("web_news", "seboard_new_posts", "2")

    with patch("app.core.engine.preview_executor.WebNewsService") as mock_web_news_class:
        mock_web_news = mock_web_news_class.return_value
        mock_web_news.fetch_articles = AsyncMock(
            return_value={
                "type": "ARTICLE_LIST",
                "items": [{"id": "123", "title": "Release note"}],
                "metadata": {"provider": "seboard", "count": 1},
            }
        )

        response = await executor.preview_node(
            workflow_id="wf1",
            node_id="node_source",
            nodes=[node],
            service_tokens={},
            limit=5,
            include_content=False,
        )

    assert response.available is True
    assert response.output_data["type"] == "ARTICLE_LIST"
    mock_web_news.fetch_articles.assert_awaited_once_with(
        "seboard_posts",
        "2",
        limit=5,
        include_content=False,
    )


async def test_naver_news_preview_returns_article_list_without_token() -> None:
    executor = WorkflowPreviewExecutor()
    node = _source_node("naver_news", "article_search", "인공지능")

    with patch("app.core.engine.preview_executor.NaverNewsService") as mock_naver_news_class:
        mock_naver_news = mock_naver_news_class.return_value
        mock_naver_news.search_articles = AsyncMock(
            return_value={
                "type": "ARTICLE_LIST",
                "items": [{"id": "news-1", "title": "AI news"}],
                "metadata": {"provider": "naver_news", "count": 1},
            }
        )

        response = await executor.preview_node(
            workflow_id="wf1",
            node_id="node_source",
            nodes=[node],
            service_tokens={},
            limit=5,
            include_content=False,
        )

    assert response.available is True
    assert response.output_data["type"] == "ARTICLE_LIST"
    assert response.output_data["items"][0]["title"] == "AI news"
    mock_naver_news.search_articles.assert_awaited_once_with(
        "인공지능",
        limit=5,
    )


async def test_naver_news_new_articles_preview_uses_news_search() -> None:
    executor = WorkflowPreviewExecutor()
    node = _source_node("naver_news", "new_articles", "AI")

    with patch("app.core.engine.preview_executor.NaverNewsService") as mock_naver_news_class:
        mock_naver_news = mock_naver_news_class.return_value
        mock_naver_news.search_articles = AsyncMock(
            return_value={
                "type": "ARTICLE_LIST",
                "items": [{"id": "news-1", "title": "AI news"}],
                "metadata": {"provider": "naver_news", "count": 1},
            }
        )

        response = await executor.preview_node(
            workflow_id="wf1",
            node_id="node_source",
            nodes=[node],
            service_tokens={},
            limit=5,
            include_content=False,
        )

    assert response.available is True
    assert response.output_data["type"] == "ARTICLE_LIST"
    mock_naver_news.search_articles.assert_awaited_once_with(
        "AI",
        limit=5,
    )


async def test_gmail_label_emails_preview_returns_canonical_aliases() -> None:
    executor = WorkflowPreviewExecutor()
    node = _source_node("gmail", "label_emails", "Label_1")

    with patch("app.core.engine.preview_executor.GmailService") as mock_gmail_class:
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.list_messages = AsyncMock(
            return_value=[
                {
                    "id": "msg_1",
                    "threadId": "thread_1",
                    "subject": "Preview",
                    "from": "sender@example.com",
                    "date": "2026-05-08T10:00:00Z",
                    "body": "full body",
                    "bodyPreview": "preview body",
                    "labels": ["INBOX"],
                }
            ]
        )

        response = await executor.preview_node(
            workflow_id="wf1",
            node_id="node_source",
            nodes=[node],
            service_tokens={"gmail": "token"},
            limit=1,
            include_content=False,
        )

    expected_email = {
        "id": "msg_1",
        "threadId": "thread_1",
        "subject": "Preview",
        "from": "sender@example.com",
        "sender": "sender@example.com",
        "to": [],
        "date": "2026-05-08T10:00:00Z",
        "body": "",
        "bodyPreview": "preview body",
        "labels": ["INBOX"],
        "attachments": [],
    }
    assert response.output_data == {
        "type": "EMAIL_LIST",
        "emails": [expected_email],
        "items": [expected_email],
        "metadata": {
            "count": 1,
            "truncated": True,
            "sourceMode": "label_emails",
        },
        "truncated": True,
    }
    mock_gmail.list_messages.assert_awaited_once_with(
        "token",
        query="label:Label_1",
        max_results=1,
    )


async def test_gmail_single_email_preview_wraps_email_and_preserves_top_level_aliases() -> None:
    executor = WorkflowPreviewExecutor()
    node = _source_node("gmail", "single_email", "msg_1")

    with patch("app.core.engine.preview_executor.GmailService") as mock_gmail_class:
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.get_message = AsyncMock(
            return_value={
                "id": "msg_1",
                "threadId": "thread_1",
                "subject": "Subject",
                "from": "sender@example.com",
                "to": ["me@example.com"],
                "date": "2026-05-08T10:00:00Z",
                "body": "full body",
                "bodyPreview": "preview body",
                "labels": ["INBOX"],
            }
        )

        response = await executor.preview_node(
            workflow_id="wf1",
            node_id="node_source",
            nodes=[node],
            service_tokens={"gmail": "token"},
            limit=5,
            include_content=True,
        )

    assert response.output_data["type"] == "SINGLE_EMAIL"
    assert response.output_data["email"]["body"] == "full body"
    assert response.output_data["email"]["bodyPreview"] == "preview body"
    assert response.output_data["subject"] == "Subject"
    assert response.output_data["from"] == "sender@example.com"
    mock_gmail.get_message.assert_awaited_once_with("token", "msg_1")
