import re
from typing import Any

from bs4 import BeautifulSoup

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.safe_http import SafeHttpClient

SEBOARD_BASE_URL = "https://seboard.site"
SEBOARD_API_BASE_URL = "https://seboard.site/v1"
DEFAULT_LIMIT = 10
MAX_LIMIT = 20
ARTICLE_CONTENT_LIMIT = 4_000


class SeBoardService:
    """SE Board public post adapter."""

    def __init__(self, safe_http_client: SafeHttpClient | None = None) -> None:
        self._http = safe_http_client or SafeHttpClient()

    async def list_posts(
        self,
        category_id: str,
        *,
        limit: int = DEFAULT_LIMIT,
        include_content: bool = False,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        if not category_id:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="SE Board category id is required.",
            )

        normalized_limit = self._normalize_limit(limit)
        response = await self._http.get_json(
            f"{SEBOARD_API_BASE_URL}/posts",
            params={
                "categoryId": category_id,
                "page": 0,
                "perPage": normalized_limit,
            },
        )
        posts = self._extract_posts(response)

        items = [self._to_article_item(post, category_id) for post in posts]
        normalized_keyword = self._normalize_keyword(keyword)
        if normalized_keyword:
            items = [
                item for item in items
                if self._matches_keyword(item, normalized_keyword)
            ]
        if include_content:
            for item in items:
                detail = await self.get_post_detail(item["id"])
                item["content"] = detail.get("content")
                if detail.get("metadata"):
                    item["metadata"].update(detail["metadata"])
        return items

    async def get_post_detail(self, post_id: str) -> dict[str, Any]:
        response = await self._http.get_json(f"{SEBOARD_API_BASE_URL}/posts/{post_id}")
        if not isinstance(response, dict):
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="SE Board post detail response is invalid.",
            )

        html = str(response.get("contents") or "")
        return {
            "content": self._normalize_html_text(html),
            "metadata": {
                "like_count": response.get("likeCount"),
                "dislike_count": response.get("dislikeCount"),
            },
        }

    @staticmethod
    def _extract_posts(response: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
        if isinstance(response, dict) and isinstance(response.get("content"), list):
            return [
                item for item in response["content"]
                if isinstance(item, dict)
            ]
        if isinstance(response, list):
            return [
                item for item in response
                if isinstance(item, dict)
            ]
        raise FlowifyException(
            ErrorCode.EXTERNAL_API_ERROR,
            detail="SE Board post list response is invalid.",
        )

    @staticmethod
    def _to_article_item(post: dict[str, Any], category_id: str) -> dict[str, Any]:
        post_id = str(post.get("postId") or post.get("id") or "")
        category = post.get("category") if isinstance(post.get("category"), dict) else {}
        author = post.get("author") if isinstance(post.get("author"), dict) else {}

        return {
            "id": post_id,
            "title": str(post.get("title") or ""),
            "url": f"{SEBOARD_BASE_URL}/posts/{post_id}" if post_id else SEBOARD_BASE_URL,
            "source": "SE Board",
            "author": author.get("name"),
            "published_at": post.get("createdAt"),
            "summary": None,
            "content": None,
            "metadata": {
                "category_id": str(category.get("categoryId") or category_id),
                "category_name": category.get("name"),
                "views": post.get("views"),
                "comment_size": post.get("commentSize"),
                "has_attachment": post.get("hasAttachment"),
            },
        }

    @staticmethod
    def _normalize_html_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["script", "style"]):
            element.decompose()

        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = text.strip()
        if len(text) > ARTICLE_CONTENT_LIMIT:
            return text[:ARTICLE_CONTENT_LIMIT]
        return text

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        return max(1, min(limit, MAX_LIMIT))

    @staticmethod
    def _normalize_keyword(keyword: str | None) -> str | None:
        if not keyword:
            return None

        normalized_keyword = keyword.strip().casefold()
        return normalized_keyword or None

    @staticmethod
    def _matches_keyword(item: dict[str, Any], keyword: str) -> bool:
        title = item.get("title")
        return isinstance(title, str) and keyword in title.casefold()
