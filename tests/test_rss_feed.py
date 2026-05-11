import socket

import httpx
import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.rss_feed import RssFeedService
from app.services.integrations.safe_http import SafeHttpClient


def _public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def _rss_feed_body() -> str:
    return """
    <rss version="2.0">
      <channel>
        <title>Example Feed</title>
        <item>
          <guid>post-1</guid>
          <title>첫 번째 글</title>
          <link>https://example.com/posts/1</link>
          <author>author@example.com</author>
          <pubDate>Sun, 10 May 2026 10:00:00 GMT</pubDate>
          <description><![CDATA[<p>요약 <strong>본문</strong></p>]]></description>
        </item>
        <item>
          <guid>post-2</guid>
          <title>두 번째 글</title>
          <link>https://example.com/posts/2</link>
          <description>두 번째 요약</description>
        </item>
      </channel>
    </rss>
    """


async def test_rss_feed_list_articles_from_website_feed_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200,
                text="""
                <html>
                  <head>
                    <link rel="alternate" type="application/rss+xml" href="/rss.xml" />
                  </head>
                </html>
                """,
                headers={"content-type": "text/html"},
                request=request,
            )
        return httpx.Response(
            200,
            text=_rss_feed_body(),
            headers={"content-type": "application/rss+xml"},
            request=request,
        )

    service = RssFeedService(
        SafeHttpClient(
            allow_any_public_host=True,
            transport=httpx.MockTransport(handler),
        )
    )

    items, metadata = await service.list_articles("https://example.com", limit=1)

    assert metadata["feed_url"] == "https://example.com/rss.xml"
    assert metadata["feed_title"] == "Example Feed"
    assert metadata["source_count"] == 2
    assert len(items) == 1
    assert items[0]["id"] == "post-1"
    assert items[0]["title"] == "첫 번째 글"
    assert items[0]["source"] == "Example Feed"
    assert items[0]["summary"] == "요약\n본문"
    assert items[0]["content"] is None


async def test_rss_feed_include_content_uses_feed_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    atom_body = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Atom Feed</title>
      <entry>
        <id>tag:example.com,2026:1</id>
        <title>Atom 글</title>
        <link href="https://example.com/posts/atom-1" />
        <updated>2026-05-10T10:00:00Z</updated>
        <content type="html"><![CDATA[<p>긴 본문</p>]]></content>
      </entry>
    </feed>
    """
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=atom_body,
            headers={"content-type": "application/atom+xml"},
            request=request,
        )
    )
    service = RssFeedService(
        SafeHttpClient(allow_any_public_host=True, transport=transport)
    )

    items, metadata = await service.list_articles(
        "https://example.com/atom.xml",
        include_content=True,
    )

    assert metadata["feed_title"] == "Atom Feed"
    assert items[0]["content"] == "긴 본문"


async def test_rss_feed_raises_when_feed_has_no_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text="<rss><channel><title>Empty Feed</title></channel></rss>",
            headers={"content-type": "application/rss+xml"},
            request=request,
        )
    )
    service = RssFeedService(
        SafeHttpClient(allow_any_public_host=True, transport=transport)
    )

    with pytest.raises(FlowifyException) as exc_info:
        await service.list_articles("https://example.com/rss.xml")

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
