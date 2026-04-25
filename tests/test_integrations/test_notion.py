from unittest.mock import AsyncMock, patch

import pytest

from app.services.integrations.notion import NotionService


@pytest.fixture()
def notion():
    return NotionService()


class TestNotionService:
    @pytest.mark.asyncio
    async def test_create_page(self, notion):
        with patch.object(notion, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"id": "page_1", "object": "page"}
            result = await notion.create_page("token", "parent_1", "New Page", "Content")
            assert result["id"] == "page_1"
            # Notion-Version 헤더가 포함되었는지 확인
            call_kwargs = mock_req.call_args
            assert "Notion-Version" in call_kwargs.kwargs.get("headers", {})

    @pytest.mark.asyncio
    async def test_get_page(self, notion):
        with patch.object(notion, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"id": "page_1", "object": "page", "properties": {}}
            result = await notion.get_page("token", "page_1")
            assert result["object"] == "page"

    @pytest.mark.asyncio
    async def test_update_page(self, notion):
        with patch.object(notion, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"object": "list", "results": []}
            await notion.update_page("token", "page_1", "Updated content")
            assert mock_req.called
