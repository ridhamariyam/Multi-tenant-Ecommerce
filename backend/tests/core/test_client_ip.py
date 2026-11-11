"""A client's address comes from the connection, rewritten only by a trusted proxy."""

from __future__ import annotations

import pytest
from starlette.requests import Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.request_context import client_ip

PROXY = "10.0.0.5"
SPOOFED = "203.0.113.9"


def _scope(peer: str) -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-forwarded-for", SPOOFED.encode())],
        "client": (peer, 5000),
        "scheme": "http",
        "server": ("api", 8000),
    }


def test_the_app_never_reads_forwarded_for_itself():
    assert client_ip(Request(_scope("198.51.100.7"))) == "198.51.100.7"


async def _seen_by_app(trusted: str, peer: str) -> str:
    seen = {}

    async def app(scope, _receive, _send):
        seen["ip"] = client_ip(Request(scope))

    await ProxyHeadersMiddleware(app, trusted_hosts=trusted)(_scope(peer), None, None)
    return seen["ip"]


@pytest.mark.parametrize(
    ("trusted", "peer", "expected"),
    [
        ("127.0.0.1", PROXY, PROXY),
        (PROXY, PROXY, SPOOFED),
        (PROXY, "198.51.100.7", "198.51.100.7"),
        ("10.0.0.0/24", PROXY, SPOOFED),
    ],
)
async def test_forwarded_for_counts_only_from_a_trusted_proxy(trusted, peer, expected):
    assert await _seen_by_app(trusted, peer) == expected
