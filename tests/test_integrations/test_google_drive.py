from unittest.mock import AsyncMock, patch

import pytest

from app.services.integrations.google_drive import GoogleDriveService


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
            },
            {"status_code": 200, "text": "hello world"},
        ],
    ):
        result = await service.download_file("token", "file_123")

    assert result == {
        "id": "file_123",
        "name": "doc.txt",
        "mimeType": "text/plain",
        "content": "hello world",
    }
