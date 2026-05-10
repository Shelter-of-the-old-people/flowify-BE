import socket

import httpx
import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.safe_http import SafeHttpClient


def _public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def _private_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]


async def test_get_json_allows_allowlisted_https_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"ok": True}, request=request)
    )
    client = SafeHttpClient(allowed_hosts={"example.com"}, transport=transport)

    result = await client.get_json("https://example.com/posts", params={"page": 0})

    assert result == {"ok": True}


async def test_get_json_rejects_http_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)
    client = SafeHttpClient(allowed_hosts={"example.com"})

    with pytest.raises(FlowifyException) as exc_info:
        await client.get_json("http://example.com/posts")

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_get_json_rejects_disallowed_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)
    client = SafeHttpClient(allowed_hosts={"example.com"})

    with pytest.raises(FlowifyException) as exc_info:
        await client.get_json("https://localhost/posts")

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_get_json_rejects_private_dns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _private_dns)
    client = SafeHttpClient(allowed_hosts={"example.com"})

    with pytest.raises(FlowifyException) as exc_info:
        await client.get_json("https://example.com/posts")

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_get_json_maps_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    transport = httpx.MockTransport(lambda request: httpx.Response(429, request=request))
    client = SafeHttpClient(allowed_hosts={"example.com"}, transport=transport)

    with pytest.raises(FlowifyException) as exc_info:
        await client.get_json("https://example.com/posts")

    assert exc_info.value.error_code == ErrorCode.EXTERNAL_RATE_LIMITED
