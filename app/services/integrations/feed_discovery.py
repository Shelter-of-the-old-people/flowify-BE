from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.safe_http import SafeHttpClient

COMMON_FEED_PATHS = ("/feed", "/rss", "/rss.xml", "/atom.xml", "/feed.xml")
FEED_CONTENT_HINTS = {"rss", "atom", "xml"}


class FeedDiscoveryService:
    """Discover RSS/Atom feed URLs from public websites."""

    def __init__(self, safe_http_client: SafeHttpClient | None = None) -> None:
        self._http = safe_http_client or SafeHttpClient(allow_any_public_host=True)

    async def discover_feed_url(self, source_url: str) -> str:
        normalized_url = self._normalize_source_url(source_url)
        html_or_feed = await self._http.get_text(
            normalized_url,
            allowed_content_types={"html", "xml", "rss", "atom", "text"},
        )
        if self._looks_like_feed(html_or_feed):
            return normalized_url

        discovered = self._find_feed_link(normalized_url, html_or_feed)
        if discovered:
            return discovered

        fallback = await self._find_common_feed_path(normalized_url)
        if fallback:
            return fallback

        raise FlowifyException(
            ErrorCode.INVALID_REQUEST,
            detail="이 사이트에서 자동으로 가져올 글 목록을 찾지 못했습니다.",
            context={"url": normalized_url},
        )

    async def _find_common_feed_path(self, source_url: str) -> str | None:
        parsed = urlparse(source_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        for path in COMMON_FEED_PATHS:
            candidate_url = urljoin(origin, path)
            try:
                candidate_body = await self._http.get_text(
                    candidate_url,
                    allowed_content_types=FEED_CONTENT_HINTS,
                )
            except FlowifyException:
                continue
            if self._looks_like_feed(candidate_body):
                return candidate_url
        return None

    @staticmethod
    def _normalize_source_url(source_url: str) -> str:
        stripped = source_url.strip()
        if not stripped:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="사이트 주소를 입력해주세요.",
            )
        parsed = urlparse(stripped)
        if not parsed.scheme:
            return f"https://{stripped}"
        return stripped

    @staticmethod
    def _find_feed_link(source_url: str, html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("link"):
            rel = link.get("rel") or []
            rel_values = rel if isinstance(rel, list) else [rel]
            if "alternate" not in [str(value).lower() for value in rel_values]:
                continue

            content_type = str(link.get("type") or "").lower()
            if not any(hint in content_type for hint in FEED_CONTENT_HINTS):
                continue

            href = link.get("href")
            if not href:
                continue
            return urljoin(source_url, str(href))
        return None

    @staticmethod
    def _looks_like_feed(body: str) -> bool:
        prefix = body.lstrip()[:500].lower()
        return "<rss" in prefix or "<feed" in prefix
