import httpx
import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.naver_news import NAVER_NEWS_SEARCH_URL, NaverNewsService


async def test_naver_news_search_articles_returns_article_list() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert str(request.url.copy_with(query=None)) == NAVER_NEWS_SEARCH_URL
        assert request.url.params["query"] == "인공지능"
        assert request.url.params["display"] == "2"
        assert request.url.params["sort"] == "date"
        assert request.headers["X-Naver-Client-Id"] == "client-id"
        return httpx.Response(
            200,
            json={
                "total": 1,
                "items": [
                    {
                        "title": "<b>AI</b> 뉴스",
                        "originallink": "https://example.com/news/1",
                        "link": "https://n.news.naver.com/article/1",
                        "description": "요약 <b>본문</b>",
                        "pubDate": "Mon, 10 May 2026 09:00:00 +0900",
                    }
                ],
            },
            request=request,
        )

    service = NaverNewsService(
        client_id="client-id",
        client_secret="client-secret",
        transport=httpx.MockTransport(handler),
    )

    result = await service.search_articles("인공지능", limit=2)

    assert len(requests) == 1
    assert result == {
        "type": "ARTICLE_LIST",
        "items": [
            {
                "id": "https://example.com/news/1",
                "title": "AI\n뉴스",
                "url": "https://example.com/news/1",
                "source": "Naver News",
                "author": None,
                "published_at": "Mon, 10 May 2026 09:00:00 +0900",
                "summary": "요약\n본문",
                "content": None,
                "metadata": {
                    "provider": "naver_news",
                    "naver_link": "https://n.news.naver.com/article/1",
                    "query": "인공지능",
                },
            }
        ],
        "metadata": {
            "provider": "naver_news",
            "query": "인공지능",
            "count": 1,
            "total": 1,
            "sort": "date",
        },
    }


async def test_naver_news_search_articles_requires_query() -> None:
    service = NaverNewsService(client_id="client-id", client_secret="client-secret")

    with pytest.raises(FlowifyException) as exc_info:
        await service.search_articles(" ")

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
    assert exc_info.value.detail == "검색어를 입력해 주세요."


async def test_naver_news_search_articles_requires_credentials() -> None:
    service = NaverNewsService(client_id="", client_secret="")

    with pytest.raises(FlowifyException) as exc_info:
        await service.search_articles("인공지능")

    assert exc_info.value.error_code == ErrorCode.EXTERNAL_API_ERROR
    assert exc_info.value.detail == "네이버 뉴스 연결 설정이 필요합니다. 관리자에게 문의해 주세요."


async def test_naver_news_search_articles_maps_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"errorMessage": "rate limited"}, request=request)

    service = NaverNewsService(
        client_id="client-id",
        client_secret="client-secret",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(FlowifyException) as exc_info:
        await service.search_articles("인공지능")

    assert exc_info.value.error_code == ErrorCode.EXTERNAL_RATE_LIMITED
    assert exc_info.value.detail == "네이버 뉴스 API 호출 한도를 초과했습니다. 잠시 후 다시 시도해 주세요."
