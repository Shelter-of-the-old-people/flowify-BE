import asyncio
import logging

import httpx

from app.common.errors import ErrorCode, FlowifyException

logger = logging.getLogger(__name__)


class BaseIntegrationService:
    """외부 서비스 연동 공통 베이스 클래스.

    재시도 로직 (EXR-01):
        외부 API 호출 실패 시 최대 3회, 지수 백오프 (1s → 2s → 4s).
    에러 래핑:
        OAuth 401 → OAUTH_TOKEN_INVALID
        기타 실패 → EXTERNAL_API_ERROR
    """

    MAX_RETRIES = 3
    BASE_BACKOFF = 1.0  # seconds

    @staticmethod
    async def _request(
        method: str,
        url: str,
        token: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: float = 30.0,
    ) -> dict:
        """인증 헤더 포함 HTTP 요청 + 재시도 + 에러 래핑."""
        req_headers = {}
        if token:
            req_headers["Authorization"] = f"Bearer {token}"
        if headers:
            req_headers.update(headers)

        last_exc: Exception | None = None

        for attempt in range(BaseIntegrationService.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.request(
                        method=method,
                        url=url,
                        headers=req_headers,
                        json=json,
                        params=params,
                    )

                if resp.status_code == 401:
                    raise FlowifyException(
                        ErrorCode.OAUTH_TOKEN_INVALID,
                        detail=f"OAuth 토큰이 만료되었거나 유효하지 않습니다.",
                        context={"url": url, "status": 401},
                    )

                resp.raise_for_status()

                if resp.headers.get("content-type", "").startswith("application/json"):
                    return resp.json()
                return {"status_code": resp.status_code, "text": resp.text}

            except FlowifyException:
                raise
            except httpx.HTTPStatusError as e:
                last_exc = e
                if e.response.status_code < 500:
                    break  # 4xx는 재시도하지 않음
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_exc = e

            # 지수 백오프 대기
            if attempt < BaseIntegrationService.MAX_RETRIES - 1:
                wait = BaseIntegrationService.BASE_BACKOFF * (2 ** attempt)
                logger.warning(f"외부 API 재시도 {attempt + 1}/{BaseIntegrationService.MAX_RETRIES}: {url} ({wait}s 대기)")
                await asyncio.sleep(wait)

        raise FlowifyException(
            ErrorCode.EXTERNAL_API_ERROR,
            detail=f"외부 서비스 호출 실패: {url}",
            context={"url": url, "error": str(last_exc)},
        )
