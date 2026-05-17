import socket
from typing import Any

import httpx
import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.safe_http import SafeHttpClient
from app.services.integrations.seboard import SeBoardService
from app.services.integrations.web_news import WebNewsService


def _public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def _seboard_post() -> dict[str, Any]:
    return {
        "postId": 123,
        "title": "Release note",
        "category": {"categoryId": 2, "name": "Notice"},
        "author": {"name": "Admin"},
        "views": 7,
        "createdAt": "2026-05-10T10:00:00",
        "hasAttachment": False,
        "commentSize": 1,
    }


async def test_seboard_list_posts_returns_article_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/v1/posts"
        assert request.url.params["categoryId"] == "2"
        assert request.url.params["perPage"] == "5"
        return httpx.Response(200, json={"content": [_seboard_post()]}, request=request)

    client = SafeHttpClient(transport=httpx.MockTransport(handler))
    service = SeBoardService(client)

    result = await service.list_posts("2", limit=5)

    assert len(requests) == 1
    assert result == [
        {
            "id": "123",
            "title": "Release note",
            "url": "https://seboard.site/posts/123",
            "source": "SE Board",
            "author": "Admin",
            "published_at": "2026-05-10T10:00:00",
            "summary": None,
            "content": None,
            "metadata": {
                "category_id": "2",
                "category_name": "Notice",
                "views": 7,
                "comment_size": 1,
                "has_attachment": False,
            },
        }
    ]


async def test_seboard_include_content_fetches_post_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/v1/posts":
            return httpx.Response(200, json={"content": [_seboard_post()]}, request=request)
        if request.url.path == "/v1/posts/123":
            return httpx.Response(
                200,
                json={
                    "contents": "<p>Hello&nbsp;<strong>world</strong></p><script>bad()</script>",
                    "likeCount": 3,
                    "dislikeCount": 0,
                },
                request=request,
            )
        return httpx.Response(404, request=request)

    client = SafeHttpClient(transport=httpx.MockTransport(handler))
    service = SeBoardService(client)

    result = await service.list_posts("2", limit=5, include_content=True)

    assert requested_paths == ["/v1/posts", "/v1/posts/123"]
    assert result[0]["content"] == "Hello\nworld"
    assert result[0]["metadata"]["like_count"] == 3
    assert result[0]["metadata"]["dislike_count"] == 0


async def test_seboard_list_posts_filters_by_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)
    matching_post = _seboard_post()
    matching_post["title"] = "장학 공지"
    other_post = _seboard_post()
    other_post["postId"] = 124
    other_post["title"] = "수강 신청 안내"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"content": [matching_post, other_post]},
            request=request,
        )

    client = SafeHttpClient(transport=httpx.MockTransport(handler))
    service = SeBoardService(client)

    result = await service.list_posts("2", limit=5, keyword=" 장학 ")

    assert [item["title"] for item in result] == ["장학 공지"]


async def test_web_news_fetch_articles_returns_article_list() -> None:
    class FakeSeBoardService:
        async def list_posts(
            self,
            category_id: str,
            *,
            limit: int,
            include_content: bool,
            keyword: str | None = None,
        ) -> list[dict[str, Any]]:
            assert category_id == "2"
            assert limit == 3
            assert include_content is False
            assert keyword == "장학"
            return [_seboard_post()]

    service = WebNewsService(FakeSeBoardService())

    result = await service.fetch_articles(
        "seboard_posts",
        "2",
        limit=3,
        keyword="장학",
    )

    assert result["type"] == "ARTICLE_LIST"
    assert result["items"][0]["title"] == "Release note"
    assert result["metadata"] == {
        "provider": "seboard",
        "count": 1,
        "truncated": False,
        "include_content": False,
    }


async def test_web_news_fetch_articles_returns_website_feed_article_list() -> None:
    class FakeRssFeedService:
        async def list_articles(
            self,
            source_url: str,
            *,
            limit: int,
            include_content: bool,
        ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            assert source_url == "https://example.com"
            assert limit == 1
            assert include_content is True
            return (
                [{"id": "post-1", "title": "RSS release"}],
                {"feed_url": "https://example.com/rss.xml", "source_count": 2},
            )

    service = WebNewsService(rss_feed_service=FakeRssFeedService())

    result = await service.fetch_articles(
        "website_feed",
        "https://example.com",
        limit=1,
        include_content=True,
    )

    assert result["type"] == "ARTICLE_LIST"
    assert result["items"][0]["title"] == "RSS release"
    assert result["metadata"] == {
        "provider": "rss",
        "count": 1,
        "truncated": True,
        "include_content": True,
        "keyword": None,
        "unfiltered_count": 1,
        "filtered_count": 1,
        "feed_url": "https://example.com/rss.xml",
        "source_count": 2,
    }


async def test_web_news_fetch_articles_filters_website_feed_by_keyword() -> None:
    class FakeRssFeedService:
        async def list_articles(
            self,
            source_url: str,
            *,
            limit: int,
            include_content: bool,
        ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            return (
                [
                    {
                        "id": "post-1",
                        "title": "AI 정책 발표",
                        "summary": "정부가 새 정책을 발표했습니다.",
                    },
                    {
                        "id": "post-2",
                        "title": "날씨 소식",
                        "summary": "맑은 날씨입니다.",
                    },
                    {
                        "id": "post-3",
                        "title": "교육 뉴스",
                        "content": "교실에서 인공지능을 활용합니다.",
                    },
                ],
                {"feed_url": "https://example.com/rss.xml", "source_count": 3},
            )

    service = WebNewsService(rss_feed_service=FakeRssFeedService())

    result = await service.fetch_articles(
        "website_feed",
        "https://example.com",
        keyword=" 인공지능, 정책 ",
    )

    assert [item["id"] for item in result["items"]] == ["post-1", "post-3"]
    assert result["metadata"]["keyword"] == " 인공지능, 정책 "
    assert result["metadata"]["unfiltered_count"] == 3
    assert result["metadata"]["filtered_count"] == 2


async def test_web_news_fetch_articles_from_sources_merges_feed_items() -> None:
    class FakeRssFeedService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def list_articles(
            self,
            source_url: str,
            *,
            limit: int,
            include_content: bool,
        ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            self.calls.append(source_url)
            return (
                [
                    {
                        "id": f"{source_url}:1",
                        "title": f"{source_url} latest",
                        "url": f"{source_url}/latest",
                        "published_at": "Mon, 11 May 2026 10:00:00 GMT",
                        "metadata": {"provider": "rss"},
                    }
                ],
                {
                    "feed_url": f"{source_url}/rss.xml",
                    "feed_title": source_url,
                    "source_count": 1,
                },
            )

    fake_rss = FakeRssFeedService()
    service = WebNewsService(rss_feed_service=fake_rss)

    result = await service.fetch_articles_from_sources(
        "website_feed",
        ["https://a.example.com", "https://b.example.com"],
        limit=10,
        include_content=True,
    )

    assert fake_rss.calls == ["https://a.example.com", "https://b.example.com"]
    assert result["type"] == "ARTICLE_LIST"
    assert [item["metadata"]["source_url"] for item in result["items"]] == [
        "https://a.example.com",
        "https://b.example.com",
    ]
    assert result["metadata"]["source_count"] == 2
    assert result["metadata"]["requested_source_count"] == 2
    assert result["metadata"]["failed_sources"] == []


async def test_web_news_fetch_articles_from_sources_filters_by_keyword() -> None:
    class FakeRssFeedService:
        async def list_articles(
            self,
            source_url: str,
            *,
            limit: int,
            include_content: bool,
        ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            return (
                [
                    {
                        "id": f"{source_url}:ai",
                        "title": "AI 교육 소식",
                        "url": f"{source_url}/ai",
                        "published_at": "Mon, 11 May 2026 10:00:00 GMT",
                    },
                    {
                        "id": f"{source_url}:sports",
                        "title": "스포츠 소식",
                        "url": f"{source_url}/sports",
                        "published_at": "Mon, 11 May 2026 09:00:00 GMT",
                    },
                ],
                {"feed_url": f"{source_url}/rss.xml", "feed_title": source_url},
            )

    service = WebNewsService(rss_feed_service=FakeRssFeedService())

    result = await service.fetch_articles_from_sources(
        "website_feed",
        ["https://a.example.com", "https://b.example.com"],
        keyword="교육",
    )

    assert [item["title"] for item in result["items"]] == [
        "AI 교육 소식",
        "AI 교육 소식",
    ]
    assert result["metadata"]["keyword"] == "교육"
    assert result["metadata"]["unfiltered_count"] == 4
    assert result["metadata"]["filtered_count"] == 2


async def test_web_news_fetch_articles_from_sources_keeps_empty_keyword_result() -> None:
    class FakeRssFeedService:
        async def list_articles(
            self,
            source_url: str,
            *,
            limit: int,
            include_content: bool,
        ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            return (
                [{"id": "post-1", "title": "날씨 소식", "url": f"{source_url}/1"}],
                {"feed_url": f"{source_url}/rss.xml", "feed_title": source_url},
            )

    service = WebNewsService(rss_feed_service=FakeRssFeedService())

    result = await service.fetch_articles_from_sources(
        "website_feed",
        ["https://a.example.com"],
        keyword="인공지능",
    )

    assert result["type"] == "ARTICLE_LIST"
    assert result["items"] == []
    assert result["metadata"]["unfiltered_count"] == 1
    assert result["metadata"]["filtered_count"] == 0


async def test_web_news_fetch_articles_from_sources_keeps_success_when_one_feed_fails() -> None:
    class FakeRssFeedService:
        async def list_articles(
            self,
            source_url: str,
            *,
            limit: int,
            include_content: bool,
        ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            if source_url == "https://bad.example.com":
                raise RuntimeError("feed failed")

            return (
                [{"id": "post-1", "title": "Good feed", "url": "https://good.example.com/1"}],
                {"feed_url": "https://good.example.com/rss.xml", "feed_title": "Good"},
            )

    service = WebNewsService(rss_feed_service=FakeRssFeedService())

    result = await service.fetch_articles_from_sources(
        "website_feed",
        ["https://bad.example.com", "https://good.example.com"],
    )

    assert result["items"] == [
        {
            "id": "post-1",
            "title": "Good feed",
            "url": "https://good.example.com/1",
            "metadata": {
                "source_url": "https://good.example.com",
                "feed_url": "https://good.example.com/rss.xml",
                "feed_title": "Good",
            },
        }
    ]
    assert result["metadata"]["failed_sources"] == [
        {
            "url": "https://bad.example.com",
            "status": "failed",
            "error": "feed failed",
        }
    ]


async def test_web_news_fetch_articles_from_sources_removes_duplicate_items() -> None:
    class FakeRssFeedService:
        async def list_articles(
            self,
            source_url: str,
            *,
            limit: int,
            include_content: bool,
        ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            return (
                [{"id": source_url, "title": "Same", "url": "https://example.com/same"}],
                {"feed_url": source_url, "feed_title": source_url},
            )

    service = WebNewsService(rss_feed_service=FakeRssFeedService())

    result = await service.fetch_articles_from_sources(
        "website_feed",
        ["https://a.example.com", "https://b.example.com"],
    )

    assert len(result["items"]) == 1
    assert result["metadata"]["deduped_count"] == 1


async def test_web_news_fetch_articles_from_sources_raises_when_all_feeds_fail() -> None:
    class FakeRssFeedService:
        async def list_articles(
            self,
            source_url: str,
            *,
            limit: int,
            include_content: bool,
        ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            raise RuntimeError("feed failed")

    service = WebNewsService(rss_feed_service=FakeRssFeedService())

    with pytest.raises(FlowifyException) as exc_info:
        await service.fetch_articles_from_sources(
            "website_feed",
            ["https://bad.example.com"],
        )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_web_news_unsupported_mode_raises() -> None:
    service = WebNewsService()

    with pytest.raises(FlowifyException) as exc_info:
        await service.fetch_articles("rss_feed", "2")

    assert exc_info.value.error_code == ErrorCode.UNSUPPORTED_RUNTIME_SOURCE
