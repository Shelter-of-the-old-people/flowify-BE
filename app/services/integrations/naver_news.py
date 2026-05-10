import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.common.errors import ErrorCode, FlowifyException
from app.config import settings

NAVER_NEWS_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
DEFAULT_LIMIT = 10
MAX_LIMIT = 20
TEXT_LIMIT = 4_000


class NaverNewsService:
    """Naver News search adapter that returns Flowify article items."""

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client_id = settings.NAVER_CLIENT_ID if client_id is None else client_id
        self._client_secret = (
            settings.NAVER_CLIENT_SECRET if client_secret is None else client_secret
        )
        self._transport = transport

    async def search_articles(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        normalized_query = self._normalize_query(query)
        normalized_limit = self._normalize_limit(limit)
        response_data = await self._request_search(normalized_query, normalized_limit)
        return self._to_article_list(response_data, normalized_query, normalized_limit)

    async def _request_search(self, query: str, display: int) -> dict[str, Any]:
        self._validate_credentials()
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    NAVER_NEWS_SEARCH_URL,
                    params={
                        "query": query,
                        "display": display,
                        "start": 1,
                        "sort": "date",
                    },
                    headers={
                        "X-Naver-Client-Id": self._client_id,
                        "X-Naver-Client-Secret": self._client_secret,
                    },
                )
        except httpx.HTTPError as exc:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="네이버 뉴스 API 호출에 실패했습니다.",
                context={"provider": "naver_news", "query": query, "error": str(exc)},
            ) from exc

        self._validate_response(response, query)
        try:
            data = response.json()
        except ValueError as exc:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="네이버 뉴스 API 응답을 해석하지 못했습니다.",
                context={"provider": "naver_news", "query": query},
            ) from exc

        if not isinstance(data, dict):
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="네이버 뉴스 API 응답 형식이 올바르지 않습니다.",
                context={"provider": "naver_news", "query": query},
            )
        return data

    def _validate_credentials(self) -> None:
        if self._client_id and self._client_secret:
            return
        raise FlowifyException(
            ErrorCode.EXTERNAL_API_ERROR,
            detail="네이버 뉴스 연결 설정이 필요합니다. 관리자에게 문의해 주세요.",
            context={"provider": "naver_news"},
        )

    @staticmethod
    def _validate_response(response: httpx.Response, query: str) -> None:
        if response.status_code in (401, 403):
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="네이버 뉴스 API 인증에 실패했습니다.",
                context={
                    "provider": "naver_news",
                    "query": query,
                    "status_code": response.status_code,
                },
            )
        if response.status_code == 429:
            raise FlowifyException(
                ErrorCode.EXTERNAL_RATE_LIMITED,
                detail="네이버 뉴스 API 호출 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.",
                context={
                    "provider": "naver_news",
                    "query": query,
                    "status_code": response.status_code,
                },
            )
        if response.status_code >= 400:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="네이버 뉴스 API 호출에 실패했습니다.",
                context={
                    "provider": "naver_news",
                    "query": query,
                    "status_code": response.status_code,
                },
            )

    def _to_article_list(
        self,
        response_data: dict[str, Any],
        query: str,
        display: int,
    ) -> dict[str, Any]:
        raw_items = response_data.get("items")
        if not isinstance(raw_items, list):
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="네이버 뉴스 API 응답에 기사 목록이 없습니다.",
                context={"provider": "naver_news", "query": query},
            )

        items = [
            self._to_article_item(item, query)
            for item in raw_items[:display]
            if isinstance(item, dict)
        ]
        if not items:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="검색 결과가 없습니다. 다른 검색어를 입력해 주세요.",
                context={"provider": "naver_news", "query": query},
            )

        return {
            "type": "ARTICLE_LIST",
            "items": items,
            "metadata": {
                "provider": "naver_news",
                "query": query,
                "count": len(items),
                "total": response_data.get("total"),
                "sort": "date",
            },
        }

    def _to_article_item(self, item: dict[str, Any], query: str) -> dict[str, Any]:
        article_url = self._as_text(item.get("originallink")) or self._as_text(item.get("link"))
        naver_link = self._as_text(item.get("link"))
        title = self._normalize_html_text(self._as_text(item.get("title"))) or "제목 없음"
        summary = self._normalize_html_text(self._as_text(item.get("description")))

        return {
            "id": article_url or naver_link or title,
            "title": title,
            "url": article_url,
            "source": "Naver News",
            "author": None,
            "published_at": self._as_text(item.get("pubDate")),
            "summary": summary,
            "content": None,
            "metadata": {
                "provider": "naver_news",
                "naver_link": naver_link,
                "query": query,
            },
        }

    @staticmethod
    def _normalize_query(query: str) -> str:
        normalized_query = str(query or "").strip()
        if normalized_query:
            return normalized_query
        raise FlowifyException(
            ErrorCode.INVALID_REQUEST,
            detail="검색어를 입력해 주세요.",
            context={"provider": "naver_news"},
        )

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        try:
            normalized_limit = int(limit)
        except (TypeError, ValueError):
            normalized_limit = DEFAULT_LIMIT
        return max(1, min(normalized_limit, MAX_LIMIT))

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
        if len(text) > TEXT_LIMIT:
            return text[:TEXT_LIMIT]
        return text

    @staticmethod
    def _as_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
