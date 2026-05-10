from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.rss_feed import RssFeedService
from app.services.integrations.seboard import DEFAULT_LIMIT, MAX_LIMIT, SeBoardService


class WebNewsService:
    """Public article source router."""

    def __init__(
        self,
        seboard_service: SeBoardService | None = None,
        rss_feed_service: RssFeedService | None = None,
    ) -> None:
        self._seboard = seboard_service or SeBoardService()
        self._rss_feed = rss_feed_service or RssFeedService()

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

        if mode == "website_feed":
            normalized_limit = self._normalize_limit(limit)
            items, feed_metadata = await self._rss_feed.list_articles(
                target,
                limit=normalized_limit,
                include_content=include_content,
            )
            return {
                "type": "ARTICLE_LIST",
                "items": items,
                "metadata": {
                    "provider": "rss",
                    "count": len(items),
                    "truncated": feed_metadata.get("source_count", len(items)) > len(items),
                    "include_content": include_content,
                    **feed_metadata,
                },
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=web_news, mode={mode} is not supported",
        )

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        return max(1, min(limit, MAX_LIMIT))
