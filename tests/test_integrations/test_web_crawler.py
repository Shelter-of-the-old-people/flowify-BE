from unittest.mock import AsyncMock, patch

import pytest

from app.common.errors import FlowifyException
from app.services.integrations.web_crawler import WebCrawlerService


@pytest.fixture()
def crawler():
    return WebCrawlerService()


class TestWebCrawlerService:
    @pytest.mark.asyncio
    async def test_crawl_success(self, crawler):
        html = "<html><body><h1>Title</h1><p>Content</p></body></html>"

        with patch.object(crawler, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = html
            result = await crawler.crawl("https://example.com", {"title": "h1"})
            assert result["url"] == "https://example.com"
            assert result["data"]["title"] == "Title"

    @pytest.mark.asyncio
    async def test_crawl_no_selectors(self, crawler):
        html = "<html><body><p>Hello World</p></body></html>"

        with patch.object(crawler, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = html
            result = await crawler.crawl("https://example.com")
            assert "text" in result["data"] or "raw_html" in result["data"]

    @pytest.mark.asyncio
    async def test_crawl_multiple(self, crawler):
        html = "<html><body><h1>Test</h1></body></html>"

        with patch.object(crawler, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = html
            results = await crawler.crawl_multiple(
                ["https://a.com", "https://b.com"],
                {"title": "h1"},
            )
            assert len(results) == 2
            assert results[0]["url"] == "https://a.com"

    @pytest.mark.asyncio
    async def test_crawl_multiple_partial_failure(self, crawler):
        async def side_effect(url):
            if "fail" in url:
                raise FlowifyException.__new__(FlowifyException)
            return "<html><body>OK</body></html>"

        with patch.object(crawler, "_fetch_with_retry", new_callable=AsyncMock, side_effect=side_effect):
            results = await crawler.crawl_multiple(
                ["https://ok.com", "https://fail.com"],
            )
            assert len(results) == 2
            assert "error" in results[1]
