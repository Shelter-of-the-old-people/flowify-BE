from app.services.integrations.base import BaseIntegrationService

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionService(BaseIntegrationService):
    """Notion API 연동 서비스 (DC-F0403)."""

    async def _notion_request(
        self, method: str, path: str, token: str, **kwargs
    ) -> dict:
        """Notion API 공통 요청. Notion-Version 헤더를 자동 추가합니다."""
        return await self._request(
            method, f"{NOTION_API}{path}", token,
            headers={"Notion-Version": NOTION_VERSION},
            **kwargs,
        )

    async def create_page(
        self, token: str, parent_id: str, title: str, content: str = ""
    ) -> dict:
        """Notion 페이지를 생성합니다."""
        body: dict = {
            "parent": {"page_id": parent_id},
            "properties": {
                "title": {"title": [{"text": {"content": title}}]}
            },
        }
        if content:
            body["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    },
                }
            ]
        return await self._notion_request("POST", "/pages", token, json=body)

    async def update_page(self, token: str, page_id: str, content: str) -> dict:
        """Notion 페이지에 블록을 추가합니다."""
        body = {
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    },
                }
            ]
        }
        return await self._notion_request(
            "PATCH", f"/blocks/{page_id}/children", token, json=body
        )

    async def get_page(self, token: str, page_id: str) -> dict:
        """Notion 페이지 정보를 조회합니다."""
        return await self._notion_request("GET", f"/pages/{page_id}", token)
