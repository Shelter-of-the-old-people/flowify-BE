from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.seboard import DEFAULT_LIMIT, MAX_LIMIT, SeBoardService


class WebNewsService:
    """Public article source router."""

    def __init__(self, seboard_service: SeBoardService | None = None) -> None:
        self._seboard = seboard_service or SeBoardService()

    async def fetch_articles(
        self,
        mode: str,
        target: str,
        *,
        limit: int = DEFAULT_LIMIT,
        include_content: bool = False,
    ) -> dict[str, Any]:
        if mode == "seboard_posts":
            normalized_limit = self._normalize_limit(limit)
            items = await self._seboard.list_posts(
                target,
                limit=normalized_limit,
                include_content=include_content,
            )
            return {
                "type": "ARTICLE_LIST",
                "items": items,
                "metadata": {
                    "provider": "seboard",
                    "count": len(items),
                    "truncated": len(items) >= normalized_limit,
                    "include_content": include_content,
                },
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=web_news, mode={mode} is not supported",
        )

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        return max(1, min(limit, MAX_LIMIT))
