import re
from typing import Any

from bs4 import BeautifulSoup
import feedparser

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.feed_discovery import FeedDiscoveryService
from app.services.integrations.safe_http import SafeHttpClient

DEFAULT_LIMIT = 10
MAX_LIMIT = 20
ARTICLE_CONTENT_LIMIT = 4_000
FEED_CONTENT_HINTS = {"xml", "rss", "atom", "text"}


class RssFeedService:
    """RSS/Atom adapter that returns Flowify article items."""

    def __init__(
        self,
        safe_http_client: SafeHttpClient | None = None,
        feed_discovery_service: FeedDiscoveryService | None = None,
    ) -> None:
        self._http = safe_http_client or SafeHttpClient(allow_any_public_host=True)
        self._feed_discovery = feed_discovery_service or FeedDiscoveryService(self._http)

    async def list_articles(
        self,
        source_url: str,
        *,
        limit: int = DEFAULT_LIMIT,
        include_content: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        normalized_limit = self._normalize_limit(limit)
        feed_url = await self._feed_discovery.discover_feed_url(source_url)
        feed_body = await self._http.get_text(
            feed_url,
            allowed_content_types=FEED_CONTENT_HINTS,
        )
        parsed_feed = feedparser.parse(feed_body)
        entries = list(parsed_feed.entries or [])
        if not entries:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="이 사이트의 글 목록 형식을 읽을 수 없습니다.",
                context={"url": source_url, "feed_url": feed_url},
            )

        feed_title = self._as_text(parsed_feed.feed.get("title"))
        items = [
            self._to_article_item(entry, feed_title, include_content)
            for entry in entries[:normalized_limit]
        ]
        return items, {
            "feed_url": feed_url,
            "feed_title": feed_title,
            "source_count": len(entries),
        }

    def _to_article_item(
        self,
        entry: Any,
        feed_title: str | None,
        include_content: bool,
    ) -> dict[str, Any]:
        link = self._as_text(entry.get("link"))
        entry_id = self._as_text(entry.get("id") or entry.get("guid") or link)
        summary = self._normalize_html_text(
            self._as_text(entry.get("summary") or entry.get("description"))
        )

        return {
            "id": entry_id,
            "title": self._as_text(entry.get("title")) or "제목 없음",
            "url": link,
            "source": feed_title,
            "author": self._as_text(entry.get("author")),
            "published_at": self._as_text(entry.get("published") or entry.get("updated")),
            "summary": summary,
            "content": self._resolve_content(entry) if include_content else None,
            "metadata": {
                "provider": "rss",
            },
        }

    def _resolve_content(self, entry: Any) -> str | None:
        content = entry.get("content")
        if isinstance(content, list) and content:
            value = content[0].get("value") if isinstance(content[0], dict) else None
            return self._normalize_html_text(self._as_text(value))
        return self._normalize_html_text(
            self._as_text(entry.get("summary") or entry.get("description"))
        )

    @staticmethod
    def _normalize_html_text(value: str | None) -> str | None:
        if not value:
            return None
        soup = BeautifulSoup(value, "html.parser")
        for element in soup(["script", "style"]):
            element.decompose()

        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = text.strip()
        if not text:
            return None
        if len(text) > ARTICLE_CONTENT_LIMIT:
            return text[:ARTICLE_CONTENT_LIMIT]
        return text

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        return max(1, min(limit, MAX_LIMIT))

    @staticmethod
    def _as_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
