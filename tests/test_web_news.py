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


async def test_web_news_fetch_articles_returns_article_list() -> None:
    class FakeSeBoardService:
        async def list_posts(
            self,
            category_id: str,
            *,
            limit: int,
            include_content: bool,
        ) -> list[dict[str, Any]]:
            assert category_id == "2"
            assert limit == 3
            assert include_content is False
            return [_seboard_post()]

    service = WebNewsService(FakeSeBoardService())

    result = await service.fetch_articles("seboard_posts", "2", limit=3)

    assert result["type"] == "ARTICLE_LIST"
    assert result["items"][0]["title"] == "Release note"
    assert result["metadata"] == {
        "provider": "seboard",
        "count": 1,
        "truncated": False,
        "include_content": False,
    }


async def test_web_news_unsupported_mode_raises() -> None:
    service = WebNewsService()

    with pytest.raises(FlowifyException) as exc_info:
        await service.fetch_articles("rss_feed", "2")

    assert exc_info.value.error_code == ErrorCode.UNSUPPORTED_RUNTIME_SOURCE
