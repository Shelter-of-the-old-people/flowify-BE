from email.utils import parsedate_to_datetime
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
        keyword: str | None = None,
    ) -> dict[str, Any]:
        if mode == "seboard_posts":
            normalized_limit = self._normalize_limit(limit)
            items = await self._seboard.list_posts(
                target,
                limit=normalized_limit,
                include_content=include_content,
                keyword=keyword,
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
            unfiltered_count = len(items)
            items = self._filter_items_by_keyword(items, keyword)
            return {
                "type": "ARTICLE_LIST",
                "items": items,
                "metadata": {
                    "provider": "rss",
                    "count": len(items),
                    "truncated": feed_metadata.get("source_count", len(items)) > len(items),
                    "include_content": include_content,
                    "keyword": keyword,
                    "unfiltered_count": unfiltered_count,
                    "filtered_count": len(items),
                    **feed_metadata,
                },
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=web_news, mode={mode} is not supported",
        )

    async def fetch_articles_from_sources(
        self,
        mode: str,
        targets: list[str],
        *,
        limit: int = DEFAULT_LIMIT,
        include_content: bool = False,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        if mode != "website_feed":
            raise FlowifyException(
                ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
                detail=f"service=web_news, mode={mode} does not support multiple sources",
            )

        source_urls = self._normalize_targets(targets)
        if not source_urls:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="뉴스/글 출처를 하나 이상 선택해 주세요.",
            )

        normalized_limit = self._normalize_limit(limit)
        all_items: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        failed_sources: list[dict[str, Any]] = []

        for source_url in source_urls:
            try:
                items, feed_metadata = await self._rss_feed.list_articles(
                    source_url,
                    limit=normalized_limit,
                    include_content=include_content,
                )
            except Exception as exc:
                failed_sources.append({
                    "url": source_url,
                    "status": "failed",
                    "error": str(exc),
                })
                continue

            sources.append({
                "url": source_url,
                "feed_url": feed_metadata.get("feed_url"),
                "title": feed_metadata.get("feed_title"),
                "status": "success",
                "source_count": feed_metadata.get("source_count", len(items)),
            })
            all_items.extend(
                self._with_source_metadata(item, source_url, feed_metadata)
                for item in items
            )

        if not sources:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="선택한 출처에서 글을 가져오지 못했습니다.",
                context={"failed_sources": failed_sources},
            )

        unfiltered_count = len(all_items)
        filtered_items = self._filter_items_by_keyword(all_items, keyword)
        deduped_items, deduped_count = self._dedupe_items(filtered_items)
        sorted_items = self._sort_items(deduped_items)
        limited_items = sorted_items[:normalized_limit]

        return {
            "type": "ARTICLE_LIST",
            "items": limited_items,
            "metadata": {
                "provider": "rss",
                "count": len(limited_items),
                "source_count": len(sources),
                "requested_source_count": len(source_urls),
                "sources": sources,
                "failed_sources": failed_sources,
                "deduped_count": deduped_count,
                "truncated": len(sorted_items) > len(limited_items),
                "include_content": include_content,
                "keyword": keyword,
                "unfiltered_count": unfiltered_count,
                "filtered_count": len(filtered_items),
            },
        }

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        return max(1, min(limit, MAX_LIMIT))

    @staticmethod
    def _normalize_targets(targets: list[str]) -> list[str]:
        normalized = [
            str(target).strip()
            for target in targets
            if str(target).strip()
        ]
        return list(dict.fromkeys(normalized))

    @classmethod
    def _filter_items_by_keyword(
        cls,
        items: list[dict[str, Any]],
        keyword: str | None,
    ) -> list[dict[str, Any]]:
        tokens = cls._keyword_tokens(keyword)
        if not tokens:
            return items

        return [item for item in items if cls._matches_any_keyword(item, tokens)]

    @staticmethod
    def _keyword_tokens(keyword: str | None) -> list[str]:
        if not keyword:
            return []

        return [token.strip().casefold() for token in keyword.split(",") if token.strip()]

    @staticmethod
    def _matches_any_keyword(item: dict[str, Any], tokens: list[str]) -> bool:
        haystack = " ".join(
            str(item.get(key) or "") for key in ("title", "summary", "content")
        ).casefold()
        return any(token in haystack for token in tokens)

    @staticmethod
    def _with_source_metadata(
        item: dict[str, Any],
        source_url: str,
        feed_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        item_metadata = item.get("metadata")
        metadata = item_metadata if isinstance(item_metadata, dict) else {}
        return {
            **item,
            "metadata": {
                **metadata,
                "source_url": source_url,
                "feed_url": feed_metadata.get("feed_url"),
                "feed_title": feed_metadata.get("feed_title"),
            },
        }

    @staticmethod
    def _dedupe_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        seen_keys = set()
        deduped = []
        duplicate_count = 0

        for item in items:
            key = WebNewsService._dedupe_key(item)
            if key in seen_keys:
                duplicate_count += 1
                continue

            seen_keys.add(key)
            deduped.append(item)

        return deduped, duplicate_count

    @staticmethod
    def _dedupe_key(item: dict[str, Any]) -> str:
        for key in ("url", "id", "title"):
            value = item.get(key)
            if value:
                return f"{key}:{str(value).strip().lower()}"
        return f"object:{id(item)}"

    @staticmethod
    def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            items,
            key=WebNewsService._published_sort_key,
            reverse=True,
        )

    @staticmethod
    def _published_sort_key(item: dict[str, Any]) -> float:
        value = item.get("published_at")
        if not value:
            return 0
        try:
            return parsedate_to_datetime(str(value)).timestamp()
        except (TypeError, ValueError, OverflowError):
            return 0
