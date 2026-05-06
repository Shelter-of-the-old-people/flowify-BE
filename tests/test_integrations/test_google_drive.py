from unittest.mock import AsyncMock, patch

import pytest

from app.services.integrations.google_drive import DRIVE_API, DRIVE_FOLDER_MIME_TYPE
from app.services.integrations.google_drive import GoogleDriveService


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

    assert result == {
        "text": "본문",
        "status": "success",
        "truncated": False,
        "error": None,
    }


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

    assert result == {
        "text": "",
        "status": "unsupported",
        "truncated": False,
        "error": None,
    }
