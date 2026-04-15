import asyncio
import logging

import httpx

from app.common.errors import ErrorCode, FlowifyException

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
BASE_BACKOFF = 1.0


class WebCrawlerService:
    """웹 크롤링 서비스 (DC-F0404).

    httpx로 HTML을 가져오고, 셀렉터 기반으로 텍스트를 추출합니다.
    BeautifulSoup이 설치되어 있으면 사용하고, 없으면 원본 HTML을 반환합니다.

    재시도 정책 (EXR-07): 최대 2회, 지수 백오프 (1s → 2s).
    """

    async def crawl(self, url: str, selectors: dict | None = None) -> dict:
        """단일 URL을 크롤링합니다.

        Args:
            url: 크롤링 대상 URL
            selectors: CSS 셀렉터 맵. 예: {"title": "h1", "content": "article"}
        """
        html = await self._fetch_with_retry(url)
        extracted = self._parse_html(html, selectors or {})

        return {
            "url": url,
            "data": extracted,
        }

    async def crawl_multiple(
        self, urls: list[str], selectors: dict | None = None
    ) -> list[dict]:
        """복수 URL을 병렬 크롤링합니다."""
        tasks = [self.crawl(url, selectors) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = []
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                logger.warning(f"크롤링 실패: {url} - {result}")
                output.append({"url": url, "data": {}, "error": str(result)})
            else:
                output.append(result)
        return output

    @staticmethod
    async def _fetch_with_retry(url: str) -> str:
        """재시도 포함 HTML 페치."""
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    resp = await client.get(
                        url,
                        headers={"User-Agent": "Flowify-Crawler/1.0"},
                    )
                    resp.raise_for_status()
                    return resp.text
            except (httpx.HTTPError, httpx.ConnectError, httpx.ReadTimeout) as e:
                last_exc = e
                if attempt < MAX_RETRIES:
                    wait = BASE_BACKOFF * (2 ** attempt)
                    logger.warning(f"크롤링 재시도 {attempt + 1}/{MAX_RETRIES}: {url} ({wait}s 대기)")
                    await asyncio.sleep(wait)

        raise FlowifyException(
            ErrorCode.CRAWL_FAILED,
            detail=f"웹 수집 실패: {url}",
            context={"url": url, "error": str(last_exc)},
        )

    @staticmethod
    def _parse_html(html: str, selectors: dict) -> dict:
        """HTML에서 셀렉터 기반으로 텍스트를 추출합니다."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return {"raw_html": html[:5000]}

        soup = BeautifulSoup(html, "html.parser")

        if not selectors:
            # 셀렉터 없으면 전체 텍스트 추출
            return {"text": soup.get_text(separator="\n", strip=True)[:5000]}

        result = {}
        for key, selector in selectors.items():
            elements = soup.select(selector)
            if len(elements) == 1:
                result[key] = elements[0].get_text(strip=True)
            else:
                result[key] = [el.get_text(strip=True) for el in elements]
        return result
