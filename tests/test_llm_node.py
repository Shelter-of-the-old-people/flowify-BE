import io
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

import pytest

from app.common.errors import ErrorCode, FlowifyException

# v2 테스트 헬퍼: node dict와 canonical payload 사용
_DEFAULT_NODE = {
    "id": "n1",
    "type": "llm",
    "runtime_type": "llm",
    "runtime_config": {},
    "config": {},
}


def _node(**overrides):
    n = {**_DEFAULT_NODE, **overrides}
    if "action" in overrides and "runtime_config" not in overrides:
        n["runtime_config"] = {"action": overrides.pop("action")}
    return n


def _zip_bytes(entries: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            raw = content.encode() if isinstance(content, str) else content
            archive.writestr(name, raw)
    return buffer.getvalue()


# ── execute (action routing) ──


async def test_llm_node_summarize():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="요약 결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        result = await node.execute(
            node=_node(runtime_config={"action": "summarize", "output_data_type": "TEXT"}),
            input_data={"type": "TEXT", "content": "긴 텍스트"},
            service_tokens={},
        )

    assert result["type"] == "TEXT"
    assert result["content"] == "요약 결과"
    mock_instance.summarize.assert_called_once_with("긴 텍스트")


async def test_github_summarize_without_custom_prompt_uses_plain_text_default_prompt():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process = AsyncMock(return_value="?? ??")
        mock_instance.summarize = AsyncMock(return_value="generic summary")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        result = await node.execute(
            node=_node(runtime_config={"action": "summarize", "output_data_type": "TEXT"}),
            input_data={
                "type": "API_RESPONSE",
                "source_service": "github",
                "event": "new_pr",
                "repository": "openai/openai-python",
                "pr_number": 780,
                "title": "Make the trailing / optional at openai.base_url setting",
                "author": "kylehh",
                "url": "https://github.com/openai/openai-python/pull/780",
                "body": "Update base_url handling for module client usage.",
                "base_branch": "main",
                "head_branch": "base_url",
                "changed_files_count": 1,
            },
            service_tokens={},
        )

    assert result["type"] == "TEXT"
    assert result["content"] == "?? ??"
    mock_instance.summarize.assert_not_called()
    mock_instance.process.assert_awaited_once()
    prompt = mock_instance.process.await_args.args[0]
    context = mock_instance.process.await_args.kwargs["context"]
    assert "기본 정보" in prompt
    assert "Do not use markdown headings, bold markers like **" in prompt
    assert "Repository: openai/openai-python" in context
    assert "Title: Make the trailing / optional at openai.base_url setting" in context


async def test_github_process_without_custom_prompt_uses_plain_text_default_prompt():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process = AsyncMock(return_value="?? ??")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "process"})
        node._llm_service = mock_instance

        result = await node.execute(
            node=_node(runtime_config={"action": "process", "output_data_type": "TEXT"}),
            input_data={
                "type": "API_RESPONSE",
                "source_service": "github",
                "event": "new_pr",
                "repository": "openai/openai-python",
                "pr_number": 780,
                "title": "Make the trailing / optional at openai.base_url setting",
                "author": "kylehh",
                "url": "https://github.com/openai/openai-python/pull/780",
                "body": "Update base_url handling for module client usage.",
                "base_branch": "main",
                "head_branch": "base_url",
                "changed_files_count": 1,
            },
            service_tokens={},
        )

    assert result["type"] == "TEXT"
    assert result["content"] == "?? ??"
    mock_instance.process.assert_awaited_once()
    prompt = mock_instance.process.await_args.args[0]
    assert "기본 정보" in prompt


async def test_llm_node_classify():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.classify = AsyncMock(return_value="긍정")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "classify", "categories": ["긍정", "부정"]})
        node._llm_service = mock_instance

        result = await node.execute(
            node=_node(runtime_config={"action": "classify", "categories": ["긍정", "부정"]}),
            input_data={"type": "TEXT", "content": "좋은 제품"},
            service_tokens={},
        )

    assert result["content"] == "긍정"
    mock_instance.classify.assert_called_once_with("좋은 제품", ["긍정", "부정"])


async def test_llm_node_process_default():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process = AsyncMock(return_value="처리 결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "process", "prompt": "분석해줘"})
        node._llm_service = mock_instance

        result = await node.execute(
            node=_node(runtime_config={"action": "process", "prompt": "분석해줘"}),
            input_data={"type": "TEXT", "content": "입력 데이터"},
            service_tokens={},
        )

    assert result["content"] == "처리 결과"
    mock_instance.process.assert_called_once()


async def test_llm_node_process_without_prompt_raises_invalid_request():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process = AsyncMock(return_value="처리 결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "process"})
        node._llm_service = mock_instance

        with pytest.raises(FlowifyException) as exc_info:
            await node.execute(
                node=_node(runtime_config={"action": "process"}),
                input_data={"type": "TEXT", "content": "입력 데이터"},
                service_tokens={},
            )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
    assert "프롬프트" in exc_info.value.detail
    mock_instance.process.assert_not_called()


async def test_llm_node_process_spreadsheet_data_output():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process_json = AsyncMock(
            return_value={
                "headers": ["document_name", "summary", "highlights", "source_url"],
                "rows": [
                    [
                        "report.txt",
                        "핵심 요약",
                        "주요 포인트",
                        "https://drive.google.com/file/d/file_1",
                    ]
                ],
            }
        )

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "process", "prompt": "시트 형식으로 정리해줘"})
        node._llm_service = mock_instance

        result = await node.execute(
            node=_node(
                runtime_config={
                    "action": "process",
                    "prompt": "시트 형식으로 정리해줘",
                    "output_data_type": "SPREADSHEET_DATA",
                }
            ),
            input_data={
                "type": "SINGLE_FILE",
                "content": "문서 본문",
                "filename": "report.txt",
                "mime_type": "text/plain",
                "url": "https://drive.google.com/file/d/file_1",
            },
            service_tokens={},
        )

    assert result == {
        "type": "SPREADSHEET_DATA",
        "headers": ["document_name", "summary", "highlights", "source_url"],
        "rows": [
            [
                "report.txt",
                "핵심 요약",
                "주요 포인트",
                "https://drive.google.com/file/d/file_1",
            ]
        ],
    }
    mock_instance.process_json.assert_called_once_with(
        "시트 형식으로 정리해줘",
        context=(
            "Filename: report.txt\n"
            "MIME Type: text/plain\n"
            "Source URL: https://drive.google.com/file/d/file_1\n\n"
            "문서 본문"
        ),
    )


async def test_llm_node_spreadsheet_output_without_prompt_raises_invalid_request():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process_json = AsyncMock(return_value={"headers": [], "rows": []})

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        with pytest.raises(FlowifyException) as exc_info:
            await node.execute(
                node=_node(
                    runtime_config={
                        "action": "summarize",
                        "output_data_type": "SPREADSHEET_DATA",
                    }
                ),
                input_data={"type": "TEXT", "content": "입력 데이터"},
                service_tokens={},
            )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
    mock_instance.process_json.assert_not_called()


async def test_llm_node_unknown_action_raises_invalid_request():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process = AsyncMock(return_value="처리 결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "unknown", "prompt": "요청"})
        node._llm_service = mock_instance

        with pytest.raises(FlowifyException) as exc_info:
            await node.execute(
                node=_node(runtime_config={"action": "unknown", "prompt": "요청"}),
                input_data={"type": "TEXT", "content": "입력 데이터"},
                service_tokens={},
            )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
    mock_instance.process.assert_not_called()


async def test_llm_node_text_output_preserves_file_metadata():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process = AsyncMock(return_value="공유용 결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "process", "prompt": "정리해줘"})
        node._llm_service = mock_instance

        result = await node.execute(
            node=_node(runtime_config={"action": "process", "prompt": "정리해줘"}),
            input_data={
                "type": "SINGLE_FILE",
                "file_id": "file_latest",
                "filename": "latest.pdf",
                "mime_type": "application/pdf",
                "url": "https://drive.google.com/file/d/file_latest",
                "content": "입력 데이터",
            },
            service_tokens={},
        )

    assert result == {
        "type": "TEXT",
        "content": "공유용 결과",
        "file_id": "file_latest",
        "filename": "latest.pdf",
        "mime_type": "application/pdf",
        "url": "https://drive.google.com/file/d/file_latest",
    }


async def test_llm_node_default_action_is_process():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process = AsyncMock(return_value="결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"prompt": "요청"})
        node._llm_service = mock_instance

        result = await node.execute(
            node=_node(config={"prompt": "요청"}),
            input_data={"type": "TEXT", "content": "value"},
            service_tokens={},
        )

    assert result["content"] == "결과"
    mock_instance.process.assert_called_once()


# ── canonical payload 텍스트 추출 ──


async def test_extract_text_from_single_email():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="요약")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "summarize"}),
            input_data={"type": "SINGLE_EMAIL", "subject": "제목", "body": "본문 내용"},
            service_tokens={},
        )

    call_args = mock_instance.summarize.call_args[0][0]
    assert "제목" in call_args
    assert "본문 내용" in call_args


async def test_extract_text_from_spreadsheet():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="요약")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "summarize"}),
            input_data={
                "type": "SPREADSHEET_DATA",
                "headers": ["이름", "점수"],
                "rows": [["홍길동", "95"]],
            },
            service_tokens={},
        )

    call_args = mock_instance.summarize.call_args[0][0]
    assert "홍길동" in call_args


async def test_extract_text_from_single_file_includes_metadata():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="요약")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "summarize"}),
            input_data={
                "type": "SINGLE_FILE",
                "filename": "latest.pdf",
                "mime_type": "application/pdf",
                "created_time": "2026-05-04T12:00:00Z",
                "url": "https://drive.google.com/file/d/file_latest",
                "content": "문서 본문",
            },
            service_tokens={},
        )

    call_args = mock_instance.summarize.call_args[0][0]
    assert "Filename: latest.pdf" in call_args
    assert "Created Time: 2026-05-04T12:00:00Z" in call_args
    assert "Source URL: https://drive.google.com/file/d/file_latest" in call_args
    assert "문서 본문" in call_args


async def test_extract_text_from_google_drive_file_uses_lazy_extraction():
    with (
        patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls,
        patch("app.core.nodes.llm_node.GoogleDriveService") as mock_drive_cls,
    ):
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="요약")
        mock_drive = mock_drive_cls.return_value
        mock_drive.extract_file_text = AsyncMock(
            return_value={
                "text": "드라이브 파일 본문",
                "status": "success",
                "truncated": False,
                "error": None,
            }
        )

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "summarize"}),
            input_data={
                "type": "SINGLE_FILE",
                "source_service": "google_drive",
                "file_id": "file_latest",
                "filename": "latest.pdf",
                "mime_type": "application/pdf",
                "content": None,
            },
            service_tokens={"google_drive": "token"},
        )

    call_args = mock_instance.summarize.call_args[0][0]
    assert "Filename: latest.pdf" in call_args
    assert "드라이브 파일 본문" in call_args
    mock_drive.extract_file_text.assert_awaited_once_with(
        "token",
        "file_latest",
        "application/pdf",
        "latest.pdf",
        None,
    )


async def test_extract_text_from_google_drive_file_uses_failure_message():
    with (
        patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls,
        patch("app.core.nodes.llm_node.GoogleDriveService") as mock_drive_cls,
    ):
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="요약")
        mock_drive = mock_drive_cls.return_value
        mock_drive.extract_file_text = AsyncMock(
            return_value={
                "text": "",
                "status": "unsupported",
                "truncated": False,
                "error": None,
            }
        )

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        with pytest.raises(FlowifyException) as exc_info:
            await node.execute(
                node=_node(runtime_config={"action": "summarize"}),
                input_data={
                    "type": "SINGLE_FILE",
                    "source_service": "google_drive",
                    "file_id": "file_latest",
                    "filename": "latest.bin",
                    "mime_type": "application/octet-stream",
                    "content": None,
                },
                service_tokens={"google_drive": "token"},
            )

    assert exc_info.value.error_code == ErrorCode.DOCUMENT_CONTENT_UNSUPPORTED


async def test_extract_text_from_gmail_attachment_uses_lazy_extraction():
    with (
        patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls,
        patch("app.core.nodes.llm_node.GmailService") as mock_gmail_cls,
    ):
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="요약")
        mock_gmail = mock_gmail_cls.return_value
        mock_gmail.extract_attachment_text = AsyncMock(
            return_value={
                "text": "첨부 본문",
                "content": "첨부 본문",
                "status": "success",
                "content_status": "available",
                "content_error": None,
                "content_metadata": {
                    "extraction_method": "plain_text",
                    "content_kind": "plain_text",
                    "truncated": False,
                },
            }
        )

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "summarize"}),
            input_data={
                "type": "FILE_LIST",
                "items": [
                    {
                        "source_service": "gmail",
                        "message_id": "msg_1",
                        "attachment_id": "att_1",
                        "filename": "note.txt",
                        "mime_type": "text/plain",
                        "content": None,
                        "content_status": "not_requested",
                    }
                ],
            },
            service_tokens={"gmail": "token"},
        )

    call_args = mock_instance.summarize.call_args[0][0]
    assert "note.txt" in call_args
    assert "첨부 본문" in call_args
    mock_gmail.extract_attachment_text.assert_awaited_once_with(
        "token",
        message_id="msg_1",
        attachment_id="att_1",
        mime_type="text/plain",
        filename="note.txt",
        file_size=None,
        inline=False,
    )


@pytest.mark.parametrize(
    ("filename", "mime_type", "archive_entries", "expected_text"),
    [
        (
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            {
                "word/document.xml": """
                    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                      <w:body><w:p><w:r><w:t>DOCX 본문</w:t></w:r></w:p></w:body>
                    </w:document>
                """,
            },
            "DOCX 본문",
        ),
        (
            "deck.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            {
                "ppt/slides/slide1.xml": """
                    <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                           xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
                      <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>PPTX 본문</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>
                    </p:sld>
                """,
            },
            "PPTX 본문",
        ),
        (
            "contract.hwpx",
            "application/vnd.hancom.hwpx",
            {
                "Contents/section0.xml": """
                    <hp:section xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
                      <hp:p><hp:run><hp:t>HWPX 본문</hp:t></hp:run></hp:p>
                    </hp:section>
                """,
            },
            "HWPX 본문",
        ),
    ],
)
async def test_google_drive_document_extractors_feed_single_file_llm_summarize(
    filename: str,
    mime_type: str,
    archive_entries: dict[str, str | bytes],
    expected_text: str,
):
    from app.services.integrations.google_drive import GoogleDriveService

    drive_service = GoogleDriveService()
    with (
        patch.object(
            drive_service,
            "download_file_bytes",
            new_callable=AsyncMock,
            return_value=_zip_bytes(archive_entries),
        ),
        patch("app.core.nodes.llm_node.GoogleDriveService", return_value=drive_service),
        patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls,
    ):
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="요약")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "summarize"}),
            input_data={
                "type": "SINGLE_FILE",
                "source_service": "google_drive",
                "file_id": "file_document",
                "filename": filename,
                "mime_type": mime_type,
                "content": None,
            },
            service_tokens={"google_drive": "token"},
        )

    call_args = mock_instance.summarize.call_args[0][0]
    assert f"Filename: {filename}" in call_args
    assert expected_text in call_args


async def test_extract_text_from_file_list_includes_metadata():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="요약")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "summarize"}),
            input_data={
                "type": "FILE_LIST",
                "items": [
                    {
                        "filename": "latest.pdf",
                        "mime_type": "application/pdf",
                        "size": 128,
                        "created_time": "2026-05-04T12:00:00Z",
                        "url": "https://drive.google.com/file/d/file_latest",
                        "content": "파일 본문",
                        "content_status": "available",
                    }
                ],
            },
            service_tokens={},
        )

    call_args = mock_instance.summarize.call_args[0][0]
    assert "- Filename: latest.pdf" in call_args
    assert "MIME Type: application/pdf" in call_args
    assert "Source URL: https://drive.google.com/file/d/file_latest" in call_args
    assert "파일 본문" in call_args


# ── validate ──


async def test_extract_text_from_article_list_includes_article_fields():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="summary")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "summarize"}),
            input_data={
                "type": "ARTICLE_LIST",
                "items": [
                    {
                        "title": "Release note",
                        "source": "SE Board",
                        "author": "Admin",
                        "published_at": "2026-05-10T10:00:00",
                        "url": "https://seboard.site/posts/123",
                        "summary": "Short summary",
                        "content": "Full content",
                    }
                ],
            },
            service_tokens={},
        )

    call_args = mock_instance.summarize.call_args[0][0]
    assert "[Article 1]" in call_args
    assert "Title: Release note" in call_args
    assert "Source: SE Board" in call_args
    assert "URL: https://seboard.site/posts/123" in call_args
    assert "Summary:" in call_args
    assert "Full content" in call_args


async def test_extract_text_from_github_api_response_formats_pull_request_context():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process = AsyncMock(return_value="?? ??")
        mock_instance.summarize = AsyncMock(return_value="generic summary")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "summarize", "output_data_type": "TEXT"}),
            input_data={
                "type": "API_RESPONSE",
                "source_service": "github",
                "event": "new_pr",
                "repository": "openai/openai-python",
                "pr_number": 780,
                "title": "Make the trailing / optional at openai.base_url setting",
                "author": "kylehh",
                "url": "https://github.com/openai/openai-python/pull/780",
                "body": "Update base_url handling for module client usage.",
                "base_branch": "main",
                "head_branch": "base_url-fix",
                "labels": ["bug"],
                "requested_reviewers": ["reviewer1"],
                "changed_files_count": 1,
                "changed_files": [
                    {
                        "filename": "src/openai/_base_client.py",
                        "status": "modified",
                        "additions": 1,
                        "deletions": 1,
                        "changes": 2,
                    }
                ],
            },
            service_tokens={},
        )

    call_args = mock_instance.process.await_args.kwargs["context"]
    assert "Repository: openai/openai-python" in call_args
    assert "PR Number: 780" in call_args
    assert "Title: Make the trailing / optional at openai.base_url setting" in call_args
    assert "Author: kylehh" in call_args
    assert "PR Body:" in call_args
    assert "Update base_url handling for module client usage." in call_args
    assert "Changed Files:" in call_args
    assert "src/openai/_base_client.py" in call_args


def test_validate_process_requires_prompt():
    with patch("app.core.nodes.llm_node.LLMService"):
        from app.core.nodes.llm_node import LLMNodeStrategy

        node_dict = _node()
        assert (
            LLMNodeStrategy(config={"action": "process", "prompt": "test"}).validate(
                {**node_dict, "runtime_config": {"action": "process", "prompt": "test"}}
            )
            is True
        )
        assert (
            LLMNodeStrategy(config={"action": "process"}).validate(
                {**node_dict, "runtime_config": {"action": "process"}}
            )
            is False
        )
        assert (
            LLMNodeStrategy(config={"prompt": "test"}).validate(
                {**node_dict, "runtime_config": {"prompt": "test"}}
            )
            is True
        )
        assert LLMNodeStrategy(config={}).validate(node_dict) is False
        assert (
            LLMNodeStrategy(config={"action": "summarize"}).validate(
                {
                    **node_dict,
                    "runtime_config": {
                        "action": "summarize",
                        "output_data_type": "SPREADSHEET_DATA",
                    },
                }
            )
            is False
        )


def test_validate_summarize_classify_no_prompt_needed():
    with patch("app.core.nodes.llm_node.LLMService"):
        from app.core.nodes.llm_node import LLMNodeStrategy

        assert (
            LLMNodeStrategy(config={"action": "summarize"}).validate(
                _node(runtime_config={"action": "summarize"})
            )
            is True
        )
        assert (
            LLMNodeStrategy(config={"action": "classify"}).validate(
                _node(runtime_config={"action": "classify"})
            )
            is True
        )


def test_validate_unknown_action():
    with patch("app.core.nodes.llm_node.LLMService"):
        from app.core.nodes.llm_node import LLMNodeStrategy

        assert (
            LLMNodeStrategy(config={"action": "unknown"}).validate(
                _node(runtime_config={"action": "unknown"})
            )
            is False
        )


async def test_extract_text_from_email_list_includes_mail_metadata():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process = AsyncMock(return_value="정리 결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "process", "prompt": "정리해줘"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "process", "prompt": "정리해줘"}),
            input_data={
                "type": "EMAIL_LIST",
                "items": [
                    {
                        "from": "sender@example.com",
                        "date": "2026-05-04",
                        "subject": "메일 제목",
                        "body": "메일 본문",
                    }
                ],
            },
            service_tokens={},
        )

    call_args = mock_instance.process.await_args.kwargs["context"]
    assert "[Email 1]" in call_args
    assert "From: sender@example.com" in call_args
    assert "Date: 2026-05-04" in call_args
    assert "Subject: 메일 제목" in call_args
    assert "Body:" in call_args
    assert "메일 본문" in call_args
