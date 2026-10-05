"""Pure Streamable HTTP MCP app for https://bottube.ai/mcp/v1."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import __version__
from .tools import CLIENT_IP_HEADER, SITE, build_server
from .upstream import Upstream

MAX_POST_BYTES = 1024 * 1024
MAX_CONCURRENT_REQUESTS = 32
TRUSTED_PROXY = "127.0.0.1"
CORS_HEADERS = [
    (b"access-control-allow-origin", b"*"),
    (b"access-control-expose-headers", b"Mcp-Session-Id, MCP-Protocol-Version, Retry-After"),
]


@dataclass
class Settings:
    upstream_url: str = "http://127.0.0.1:8097"
    host_header: str = "bottube.ai"
    public_url: str = SITE + "/mcp/v1"
    allowed_hosts: tuple[str, ...] = ("bottube.ai", "www.bottube.ai", "127.0.0.1", "localhost", "[::1]")
    upstream_timeout: float = 10.0
    transports: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls()
        settings.upstream_url = os.environ.get("BOTTUBE_MCP_UPSTREAM", settings.upstream_url)
        settings.host_header = os.environ.get("BOTTUBE_MCP_UPSTREAM_HOST", settings.host_header)
        settings.public_url = os.environ.get("BOTTUBE_MCP_PUBLIC_URL", settings.public_url)
        hosts = os.environ.get("BOTTUBE_MCP_ALLOWED_HOSTS")
        if hosts:
            settings.allowed_hosts = tuple(host.strip().lower() for host in hosts.split(",") if host.strip())
        return settings


def _header(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value.decode("latin-1")
    return ""


def _valid_ip(raw: str) -> str | None:
    raw = (raw or "").strip()
    if raw.startswith("[") and "]" in raw:
        raw = raw[1:raw.index("]")]
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def client_ip(scope: Scope) -> str:
    """Trust nginx's overwritten X-Forwarded-For only from the IPv4 loopback peer."""
    peer = (scope.get("client") or ("", 0))[0] or ""
    if peer == TRUSTED_PROXY:
        forwarded = _valid_ip(_header(scope, b"x-forwarded-for"))
        if forwarded:
            return forwarded
    return _valid_ip(peer) or TRUSTED_PROXY


async def _send_json(send: Send, status: int, payload: dict[str, Any], *, allow: bytes | None = None) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if allow is not None:
        headers.append((b"allow", allow))
    await send({"type": "http.response.start", "status": status, "headers": headers + CORS_HEADERS})
    await send({"type": "http.response.body", "body": body})


async def read_body(receive: Receive, limit: int = MAX_POST_BYTES) -> bytes | None:
    """Read at most ``limit`` bytes, stopping before parsing if the limit is exceeded."""
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return b"".join(chunks)
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
        if not message.get("more_body"):
            return b"".join(chunks)


def replay_receive(body: bytes, receive: Receive) -> Receive:
    sent = False

    async def _receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return _receive


class McpEndpoint:
    """Bounded front end for the SDK's stateless Streamable HTTP transport."""

    def __init__(self, mcp_app: ASGIApp, concurrency: int = MAX_CONCURRENT_REQUESTS):
        self.mcp_app = mcp_app
        self.semaphore = asyncio.Semaphore(concurrency)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["method"] == "GET" and "text/event-stream" in _header(scope, b"accept").lower():
            await _send_json(send, 405, {"error": "SSE stream not offered; use POST"}, allow=b"POST")
            return
        async with self.semaphore:
            await self._bounded_call(scope, receive, send)

    async def _bounded_call(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["method"] == "POST":
            body = await read_body(receive)
            if body is None:
                await _send_json(send, 413, {"error": "request body too large"})
                return
            receive = replay_receive(body, receive)

        headers = [(key, value) for key, value in scope["headers"] if key.lower() != CLIENT_IP_HEADER.encode()]
        headers.append((CLIENT_IP_HEADER.encode(), client_ip(scope).encode()))
        inner_scope = dict(scope, headers=headers)

        async def add_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = {key.lower() for key, _ in message.get("headers", [])}
                extra = [(key, value) for key, value in CORS_HEADERS if key not in existing]
                message = dict(message, headers=list(message.get("headers", [])) + extra)
            await send(message)

        await self.mcp_app(inner_scope, receive, add_cors)


class HostCheck:
    """Reject requests whose Host is not BoTTube or loopback."""

    def __init__(self, app: ASGIApp, allowed: tuple[str, ...]):
        self.app = app
        self.allowed = {host.lower() for host in allowed}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            host = _header(scope, b"host").lower()
            name = host.rsplit(":", 1)[0] if not host.endswith("]") else host
            if name not in self.allowed:
                await _send_json(send, 421, {"error": "misdirected request"})
                return
        await self.app(scope, receive, send)


def server_card(tools: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    return {
        "$schema": "https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json",
        "name": "ai.bottube/bottube",
        "title": "BoTTube",
        "version": __version__,
        "protocolVersion": "2025-06-18",
        "serverInfo": {"name": "bottube", "title": "BoTTube", "version": __version__},
        "description": "Read-only tools to search videos and read feeds, details, comments, and creator profiles.",
        "websiteUrl": SITE,
        "documentationUrl": "https://github.com/Scottcjn/bottube/tree/main/bottube_mcp",
        "iconUrl": SITE + "/static/bottube-logo.png",
        "transport": {"type": "streamable-http", "endpoint": settings.public_url},
        "remotes": [{"type": "streamable-http", "url": settings.public_url}],
        "capabilities": {"tools": {"listChanged": False}},
        "authentication": {"required": False, "schemes": []},
        "tools": tools,
    }


def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings.from_env()
    upstream = Upstream(
        settings.upstream_url,
        host_header=settings.host_header,
        timeout=settings.upstream_timeout,
        transport=settings.transports.get("api"),
    )
    mcp = build_server(upstream)
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/mcp/v1",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    endpoint = McpEndpoint(mcp_app)
    card_cache: dict[str, Any] = {}

    async def card(_request: Request) -> Response:
        if "card" not in card_cache:
            tools = [tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in await mcp.list_tools()]
            card_cache["card"] = server_card(tools, settings)
        return JSONResponse(card_cache["card"], headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Content-Type, If-None-Match",
            "Access-Control-Expose-Headers": "ETag",
            "Cache-Control": "public, max-age=3600",
        })

    async def not_found(_request: Request) -> Response:
        return JSONResponse({"error": "not found"}, status_code=404)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            try:
                yield
            finally:
                await upstream.aclose()

    app = Starlette(
        routes=[
            Route("/mcp/v1", endpoint=endpoint),
            Route("/mcp/server-card", card, methods=["GET", "HEAD"]),
            Route(
                "/{path:path}",
                not_found,
                methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
            ),
        ],
        lifespan=lifespan,
    )
    app.add_middleware(HostCheck, allowed=settings.allowed_hosts)
    app.state.mcp = mcp
    return app
