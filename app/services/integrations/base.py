import asyncio
import logging
from typing import Any

import httpx

from app.common.errors import ErrorCode, FlowifyException

logger = logging.getLogger(__name__)


class BaseIntegrationService:
    """Shared base for external integration services.

    Retry policy (EXR-01):
        Retry up to three times with exponential backoff (1s, 2s, 4s).
    Error mapping:
        OAuth 401 -> OAUTH_TOKEN_INVALID
        OAuth 403 insufficient scope -> OAUTH_SCOPE_INSUFFICIENT
        Rate limit 429 -> EXTERNAL_RATE_LIMITED
        Other failures -> EXTERNAL_API_ERROR
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
        content: bytes | str | None = None,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: float = 30.0,
    ) -> dict:
        """Send an authenticated HTTP request with retry/error handling."""
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
                        content=content,
                        params=params,
                    )

                if resp.status_code == 401:
                    raise FlowifyException(
                        ErrorCode.OAUTH_TOKEN_INVALID,
                        detail="OAuth 토큰이 만료되었거나 유효하지 않습니다.",
                        context={"url": url, "status": 401},
                    )
                if resp.status_code == 403 and BaseIntegrationService._is_scope_error(resp):
                    raise FlowifyException(
                        ErrorCode.OAUTH_SCOPE_INSUFFICIENT,
                        detail="OAuth 권한 범위가 부족합니다.",
                        context={
                            "url": url,
                            "status": 403,
                            "provider_error": BaseIntegrationService._extract_error_payload(resp),
                        },
                    )
                if resp.status_code == 429:
                    raise FlowifyException(
                        ErrorCode.EXTERNAL_RATE_LIMITED,
                        detail="외부 서비스 요청 한도를 초과했습니다.",
                        context={
                            "url": url,
                            "status": 429,
                            "provider_error": BaseIntegrationService._extract_error_payload(resp),
                        },
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
                    break  # Do not retry client errors.
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_exc = e

            # Exponential backoff between retry attempts.
            if attempt < BaseIntegrationService.MAX_RETRIES - 1:
                wait = BaseIntegrationService.BASE_BACKOFF * (2**attempt)
                logger.warning(
                    "External API retry %s/%s: %s (waiting %ss)",
                    attempt + 1,
                    BaseIntegrationService.MAX_RETRIES,
                    url,
                    wait,
                )
                await asyncio.sleep(wait)

        raise FlowifyException(
            ErrorCode.EXTERNAL_API_ERROR,
            detail=f"외부 서비스 호출 실패: {url}",
            context={"url": url, "error": str(last_exc)},
        )

    @staticmethod
    def _extract_error_payload(resp: httpx.Response) -> Any:
        content_type = resp.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            try:
                return resp.json()
            except ValueError:
                return resp.text
        return resp.text

    @staticmethod
    def _is_scope_error(resp: httpx.Response) -> bool:
        payload = BaseIntegrationService._extract_error_payload(resp)
        haystack = BaseIntegrationService._stringify_error_payload(payload).lower()
        scope_markers = (
            "insufficient authentication scopes",
            "insufficient_scope",
            "access_token_scope_insufficient",
            "oauth_scope_insufficient",
            "scope insufficient",
            "insufficient permissions",
        )
        return any(marker in haystack for marker in scope_markers)

    @staticmethod
    def _stringify_error_payload(payload: Any) -> str:
        if isinstance(payload, dict):
            return " ".join(
                BaseIntegrationService._stringify_error_payload(value)
                for value in payload.values()
            )
        if isinstance(payload, list):
            return " ".join(
                BaseIntegrationService._stringify_error_payload(value) for value in payload
            )
        return str(payload)
