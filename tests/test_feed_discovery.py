import socket

import httpx
import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.feed_discovery import FeedDiscoveryService
from app.services.integrations.safe_http import SafeHttpClient


def _public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


async def test_discover_feed_url_returns_direct_feed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text="<rss><channel><title>Feed</title></channel></rss>",
            headers={"content-type": "application/rss+xml"},
            request=request,
        )
    )
    service = FeedDiscoveryService(
        SafeHttpClient(allow_any_public_host=True, transport=transport)
    )

    feed_url = await service.discover_feed_url("https://example.com/rss.xml")

    assert feed_url == "https://example.com/rss.xml"


async def test_discover_feed_url_finds_alternate_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text="""
            <html>
              <head>
                <link rel="alternate" type="application/rss+xml" href="/feed.xml" />
              </head>
            </html>
            """,
            headers={"content-type": "text/html"},
            request=request,
        )
    )
    service = FeedDiscoveryService(
        SafeHttpClient(allow_any_public_host=True, transport=transport)
    )

    feed_url = await service.discover_feed_url("https://example.com")

    assert feed_url == "https://example.com/feed.xml"


async def test_discover_feed_url_tries_common_feed_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200,
                text="<html><head></head><body>site</body></html>",
                headers={"content-type": "text/html"},
                request=request,
            )
        if request.url.path == "/rss.xml":
            return httpx.Response(
                200,
                text="<rss><channel><title>Feed</title></channel></rss>",
                headers={"content-type": "application/rss+xml"},
                request=request,
            )
        return httpx.Response(404, request=request)

    service = FeedDiscoveryService(
        SafeHttpClient(
            allow_any_public_host=True,
            transport=httpx.MockTransport(handler),
        )
    )

    feed_url = await service.discover_feed_url("https://example.com")

    assert feed_url == "https://example.com/rss.xml"


async def test_discover_feed_url_raises_when_feed_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text="<html><head></head><body>site</body></html>",
            headers={"content-type": "text/html"},
            request=request,
        )
    )
    service = FeedDiscoveryService(
        SafeHttpClient(allow_any_public_host=True, transport=transport)
    )

    with pytest.raises(FlowifyException) as exc_info:
        await service.discover_feed_url("https://example.com")

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
