import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from app.common.errors import ErrorCode, FlowifyException


class SafeHttpClient:
    """Allowlist-based HTTP client for public content adapters."""

    DEFAULT_ALLOWED_HOSTS = frozenset({"seboard.site"})
    ALLOWED_SCHEMES = frozenset({"https"})
    MAX_RESPONSE_BYTES = 1_000_000
    USER_AGENT = "Flowify-SafeHttp/1.0"

    def __init__(
        self,
        *,
        allowed_hosts: set[str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.allowed_hosts = allowed_hosts or set(self.DEFAULT_ALLOWED_HOSTS)
        self._transport = transport

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any] | list[Any]:
        self._validate_url(url)

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers={"User-Agent": self.USER_AGENT},
                )
        except httpx.HTTPError as exc:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="External content request failed.",
                context={"url": url, "error": str(exc)},
            ) from exc

        if response.status_code == 429:
            raise FlowifyException(
                ErrorCode.EXTERNAL_RATE_LIMITED,
                detail="External content request limit exceeded.",
                context={"url": url, "status_code": response.status_code},
            )
        if 300 <= response.status_code < 400:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="Redirect responses are not allowed for content collection.",
                context={"url": url, "status_code": response.status_code},
            )
        if response.status_code >= 400:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="External content request failed.",
                context={"url": url, "status_code": response.status_code},
            )

        if len(response.content) > self.MAX_RESPONSE_BYTES:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="External content response is too large.",
                context={"url": url, "max_bytes": self.MAX_RESPONSE_BYTES},
            )

        content_type = response.headers.get("content-type", "")
        if content_type and "json" not in content_type.lower():
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="External content response is not JSON.",
                context={"url": url, "content_type": content_type},
            )

        try:
            return response.json()
        except ValueError as exc:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="External content response JSON parsing failed.",
                context={"url": url},
            ) from exc

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").rstrip(".").lower()

        if scheme not in self.ALLOWED_SCHEMES:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="Only HTTPS content sources are allowed.",
                context={"url": url},
            )
        if hostname not in self.allowed_hosts:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="This content source is not allowed.",
                context={"host": hostname},
            )

        self._assert_public_dns(hostname, parsed.port or 443)

    @staticmethod
    def _assert_public_dns(hostname: str, port: int) -> None:
        try:
            addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail="Content source DNS lookup failed.",
                context={"host": hostname},
            ) from exc

        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise FlowifyException(
                    ErrorCode.INVALID_REQUEST,
                    detail="Content source resolved to a blocked network address.",
                    context={"host": hostname, "ip": str(ip)},
                )
