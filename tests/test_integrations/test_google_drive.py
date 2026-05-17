import io
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

import pytest

from app.config import settings
from app.services.integrations.google_drive import (
    DRIVE_API,
    DRIVE_FOLDER_MIME_TYPE,
    MAX_DOWNLOAD_BYTES,
    GoogleDriveService,
)


def _zip_bytes(entries: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            raw = content.encode() if isinstance(content, str) else content
            archive.writestr(name, raw)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_list_files_excludes_folders_by_default() -> None:
    service = GoogleDriveService()

    with patch.object(
        service,
        "_request",
        new_callable=AsyncMock,
        return_value={"files": [{"id": "file_1", "name": "a.txt"}]},
    ) as mock_request:
        result = await service.list_files("token", folder_id="folder_1")

    assert result == [{"id": "file_1", "name": "a.txt"}]
    params = mock_request.await_args.kwargs["params"]
    assert f"mimeType != '{DRIVE_FOLDER_MIME_TYPE}'" in params["q"]
    assert "'folder_1' in parents" in params["q"]


@pytest.mark.asyncio
async def test_list_files_can_include_folders() -> None:
    service = GoogleDriveService()

    with patch.object(
        service,
        "_request",
        new_callable=AsyncMock,
        return_value={"files": []},
    ) as mock_request:
        await service.list_files("token", include_folders=True)

    params = mock_request.await_args.kwargs["params"]
    assert DRIVE_FOLDER_MIME_TYPE not in params["q"]


@pytest.mark.asyncio
async def test_download_file_unwraps_text_response() -> None:
    service = GoogleDriveService()

    with patch.object(
        service,
        "_request",
        new_callable=AsyncMock,
        side_effect=[
            {
                "id": "file_123",
                "name": "doc.txt",
                "mimeType": "text/plain",
                "size": "10",
                "createdTime": "2026-05-04T12:00:00Z",
                "modifiedTime": "2026-05-04T12:10:00Z",
            },
            {"status_code": 200, "text": "hello world"},
        ],
    ):
        result = await service.download_file("token", "file_123")

    assert result == {
        "id": "file_123",
        "name": "doc.txt",
        "mimeType": "text/plain",
        "createdTime": "2026-05-04T12:00:00Z",
        "modifiedTime": "2026-05-04T12:10:00Z",
        "content": "hello world",
    }


@pytest.mark.asyncio
async def test_download_file_bytes_requests_media_content() -> None:
    service = GoogleDriveService()

    with patch.object(
        service,
        "_request_bytes",
        new_callable=AsyncMock,
        return_value=b"%PDF-1.7 bytes",
    ) as mock_request_bytes:
        result = await service.download_file_bytes("token", "file_123")

    assert result == b"%PDF-1.7 bytes"
    mock_request_bytes.assert_awaited_once_with(
        "token",
        f"{DRIVE_API}/files/file_123",
        params={"alt": "media"},
    )


@pytest.mark.asyncio
async def test_extract_file_text_decodes_text_file() -> None:
    service = GoogleDriveService()

    with patch.object(
        service,
        "download_file_bytes",
        new_callable=AsyncMock,
        return_value="본문".encode(),
    ):
        result = await service.extract_file_text("token", "file_123", "text/plain")

    assert result["text"] == "본문"
    assert result["content"] == "본문"
    assert result["status"] == "success"
    assert result["content_status"] == "available"
    assert result["content_metadata"]["extraction_method"] == "plain_text"
    assert result["content_metadata"]["limits"]["max_download_bytes"] == MAX_DOWNLOAD_BYTES


@pytest.mark.asyncio
async def test_extract_file_text_uses_google_export() -> None:
    service = GoogleDriveService()

    with patch.object(
        service,
        "_request_bytes",
        new_callable=AsyncMock,
        return_value="문서 본문".encode(),
    ) as mock_request_bytes:
        result = await service.extract_file_text(
            "token",
            "file_123",
            "application/vnd.google-apps.document",
        )

    assert result["text"] == "문서 본문"
    mock_request_bytes.assert_awaited_once_with(
        "token",
        f"{DRIVE_API}/files/file_123/export",
        params={"mimeType": "text/plain"},
    )


@pytest.mark.asyncio
async def test_extract_file_text_returns_unsupported_for_binary() -> None:
    service = GoogleDriveService()

    with patch.object(
        service,
        "download_file_bytes",
        new_callable=AsyncMock,
        return_value=b"\x00\x01",
    ):
        result = await service.extract_file_text(
            "token",
            "file_123",
            "application/octet-stream",
        )

    assert result["text"] == ""
    assert result["status"] == "unsupported"
    assert result["content_status"] == "unsupported"
    assert result["content_error"] == "이 파일 형식은 아직 본문 읽기를 지원하지 않습니다."


@pytest.mark.asyncio
async def test_extract_file_text_returns_unsupported_for_scanned_pdf_without_text() -> None:
    service = GoogleDriveService()

    with (
        patch.object(
            service,
            "download_file_bytes",
            new_callable=AsyncMock,
            return_value=b"%PDF-1.7 scanned",
        ),
        patch.object(GoogleDriveService, "_extract_pdf_text", return_value=""),
    ):
        result = await service.extract_file_text(
            "token",
            "file_pdf",
            "application/pdf",
            "scan.pdf",
        )

    assert result["content_status"] == "unsupported"
    assert result["content_error"] == "이 파일 형식은 아직 본문 읽기를 지원하지 않습니다."


@pytest.mark.asyncio
async def test_extract_file_text_returns_unsupported_for_image_when_provider_disabled() -> None:
    service = GoogleDriveService()
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (10).to_bytes(4, "big") + (20).to_bytes(4, "big")

    with patch.object(
        service,
        "download_file_bytes",
        new_callable=AsyncMock,
        return_value=png_header,
    ):
        result = await service.extract_file_text(
            "token",
            "file_image",
            "image/png",
            "capture.png",
        )

    assert result["content_status"] == "unsupported"
    assert result["content_metadata"]["image_width"] == 10
    assert result["content_metadata"]["image_height"] == 20
    assert result["content_metadata"]["languages"] == ["ko", "en"]


@pytest.mark.asyncio
async def test_extract_file_text_uses_vision_provider_for_ocr_action(monkeypatch) -> None:
    service = GoogleDriveService()
    monkeypatch.setattr(settings, "ENABLE_IMAGE_OCR", True)
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (10).to_bytes(4, "big") + (20).to_bytes(4, "big")

    with (
        patch.object(
            service,
            "download_file_bytes",
            new_callable=AsyncMock,
            return_value=png_header,
        ),
        patch("app.services.llm_service.LLMService") as mock_llm_class,
    ):
        mock_llm = mock_llm_class.return_value
        mock_llm.analyze_image = AsyncMock(return_value="이미지 글자")

        result = await service.extract_file_text(
            "token",
            "file_image",
            "image/png",
            "capture.png",
            extraction_action="ocr",
        )

    assert result["content_status"] == "available"
    assert result["content"] == "이미지 글자"
    assert result["content_metadata"]["extraction_method"] == "ocr"
    assert result["content_metadata"]["content_kind"] == "ocr_text"
    assert result["content_metadata"]["provider"] == "openai_vision"


@pytest.mark.asyncio
async def test_scan_pdf_ocr_page_limit_returns_too_large(monkeypatch) -> None:
    service = GoogleDriveService()
    monkeypatch.setattr(settings, "ENABLE_PDF_OCR", True)
    monkeypatch.setattr(settings, "MAX_OCR_PAGES", 10)

    with (
        patch.object(service, "download_file_bytes", new_callable=AsyncMock, return_value=b"%PDF"),
        patch.object(GoogleDriveService, "_extract_pdf_text", return_value=""),
        patch.object(GoogleDriveService, "_pdf_page_count", return_value=11),
    ):
        result = await service.extract_file_text(
            "token",
            "file_pdf",
            "application/pdf",
            "scan.pdf",
        )

    assert result["content_status"] == "too_large"
    assert result["content_metadata"]["page_count"] == 11
    assert result["content_metadata"]["limits"]["max_ocr_pages"] == 10
    assert result["content_metadata"]["limits"]["observed_page_count"] == 11


@pytest.mark.asyncio
async def test_scan_pdf_ocr_returns_unsupported_when_image_ocr_disabled(monkeypatch) -> None:
    service = GoogleDriveService()
    monkeypatch.setattr(settings, "ENABLE_PDF_OCR", True)
    monkeypatch.setattr(settings, "ENABLE_IMAGE_OCR", False)

    with (
        patch.object(service, "download_file_bytes", new_callable=AsyncMock, return_value=b"%PDF"),
        patch.object(GoogleDriveService, "_extract_pdf_text", return_value=""),
        patch.object(GoogleDriveService, "_pdf_page_count", return_value=1),
        patch.object(GoogleDriveService, "_render_pdf_pages_to_images", return_value=[b"image"]),
    ):
        result = await service.extract_file_text(
            "token",
            "file_pdf",
            "application/pdf",
            "scan.pdf",
        )

    assert result["content_status"] == "unsupported"
    assert result["content_metadata"]["page_count"] == 1
    assert result["content_metadata"]["ocr_page_count"] == 0


@pytest.mark.asyncio
async def test_extract_file_text_returns_too_large_from_known_size() -> None:
    service = GoogleDriveService()

    with patch.object(
        service,
        "download_file_bytes",
        new_callable=AsyncMock,
    ) as mock_download:
        result = await service.extract_file_text(
            "token",
            "file_123",
            "text/plain",
            file_size=MAX_DOWNLOAD_BYTES + 1,
        )

    assert result["content_status"] == "too_large"
    assert result["content_error"] == "파일이 현재 처리 가능한 크기를 초과했습니다."
    assert result["content_metadata"]["limits"]["max_download_bytes"] == MAX_DOWNLOAD_BYTES
    assert result["content_metadata"]["limits"]["observed_size_bytes"] == MAX_DOWNLOAD_BYTES + 1
    mock_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_file_text_returns_too_large_from_downloaded_bytes() -> None:
    service = GoogleDriveService()

    with patch.object(
        service,
        "download_file_bytes",
        new_callable=AsyncMock,
        return_value=b"x" * (MAX_DOWNLOAD_BYTES + 1),
    ):
        result = await service.extract_file_text("token", "file_123", "text/plain")

    assert result["content_status"] == "too_large"
    assert result["content"] is None
    assert result["content_metadata"]["limits"]["observed_size_bytes"] == MAX_DOWNLOAD_BYTES + 1


@pytest.mark.asyncio
async def test_extract_file_text_hides_raw_parser_exception_from_content_error() -> None:
    service = GoogleDriveService()

    with patch.object(
        service,
        "download_file_bytes",
        new_callable=AsyncMock,
        side_effect=ValueError("raw parser exception\nwith details"),
    ):
        result = await service.extract_file_text("token", "file_123", "text/plain")

    assert result["content_status"] == "failed"
    assert result["content_error"] == "파일 본문을 읽는 중 오류가 발생했습니다."
    assert "raw parser exception" not in result["content_error"]


@pytest.mark.asyncio
async def test_extract_file_text_reads_docx_paragraphs_and_tables() -> None:
    service = GoogleDriveService()
    docx_bytes = _zip_bytes(
        {
            "word/document.xml": """
                <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                  <w:body>
                    <w:p><w:r><w:t>첫 번째 문단</w:t></w:r></w:p>
                    <w:tbl>
                      <w:tr>
                        <w:tc><w:p><w:r><w:t>이름</w:t></w:r></w:p></w:tc>
                        <w:tc><w:p><w:r><w:t>상태</w:t></w:r></w:p></w:tc>
                      </w:tr>
                      <w:tr>
                        <w:tc><w:p><w:r><w:t>문서</w:t></w:r></w:p></w:tc>
                        <w:tc><w:p><w:r><w:t>완료</w:t></w:r></w:p></w:tc>
                      </w:tr>
                    </w:tbl>
                  </w:body>
                </w:document>
            """,
        }
    )

    with patch.object(
        service,
        "download_file_bytes",
        new_callable=AsyncMock,
        return_value=docx_bytes,
    ):
        result = await service.extract_file_text(
            "token",
            "file_docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "report.docx",
        )

    assert result["content_status"] == "available"
    assert result["content_metadata"]["extraction_method"] == "docx_xml"
    assert "첫 번째 문단" in result["content"]
    assert "이름 | 상태" in result["content"]
    assert "문서 | 완료" in result["content"]


@pytest.mark.asyncio
async def test_extract_file_text_reads_pptx_in_slide_order_with_notes() -> None:
    service = GoogleDriveService()
    pptx_bytes = _zip_bytes(
        {
            "ppt/slides/slide2.xml": """
                <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
                  <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>두 번째 슬라이드</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>
                </p:sld>
            """,
            "ppt/slides/slide1.xml": """
                <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
                  <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>제목</a:t></a:r><a:r><a:t>본문</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>
                </p:sld>
            """,
            "ppt/notesSlides/notesSlide1.xml": """
                <p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                         xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
                  <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>발표자 노트</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>
                </p:notes>
            """,
        }
    )

    with patch.object(
        service,
        "download_file_bytes",
        new_callable=AsyncMock,
        return_value=pptx_bytes,
    ):
        result = await service.extract_file_text(
            "token",
            "file_pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "deck.pptx",
        )

    assert result["content_status"] == "available"
    assert result["content_metadata"]["extraction_method"] == "pptx_xml"
    assert result["content_metadata"]["content_kind"] == "slide_text"
    assert result["content"].index("Slide 1:") < result["content"].index("Slide 2:")
    assert "제목 본문" in result["content"]
    assert "Notes: 발표자 노트" in result["content"]
    assert "두 번째 슬라이드" in result["content"]


@pytest.mark.asyncio
async def test_extract_file_text_reads_hwpx_section_xml_body() -> None:
    service = GoogleDriveService()
    hwpx_bytes = _zip_bytes(
        {
            "Contents/section0.xml": """
                <hp:section xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
                  <hp:p><hp:run><hp:t>한글 문서 본문</hp:t></hp:run></hp:p>
                </hp:section>
            """,
            "Contents/section1.xml": """
                <hp:section xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
                  <hp:p><hp:run><hp:t>두 번째 구역</hp:t></hp:run></hp:p>
                </hp:section>
            """,
        }
    )

    with patch.object(
        service,
        "download_file_bytes",
        new_callable=AsyncMock,
        return_value=hwpx_bytes,
    ):
        result = await service.extract_file_text(
            "token",
            "file_hwpx",
            "application/vnd.hancom.hwpx",
            "contract.hwpx",
        )

    assert result["content_status"] == "available"
    assert result["content_metadata"]["extraction_method"] == "hwpx_xml"
    assert "한글 문서 본문" in result["content"]
    assert "두 번째 구역" in result["content"]


@pytest.mark.asyncio
async def test_extract_file_text_returns_failed_for_broken_hwpx() -> None:
    service = GoogleDriveService()

    with patch.object(
        service,
        "download_file_bytes",
        new_callable=AsyncMock,
        return_value=b"not a valid zip",
    ):
        result = await service.extract_file_text(
            "token",
            "file_hwpx",
            "application/vnd.hancom.hwpx",
            "broken.hwpx",
        )

    assert result["content_status"] == "failed"
    assert result["content_error"] == "파일 본문을 읽는 중 오류가 발생했습니다."
