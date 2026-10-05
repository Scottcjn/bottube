"""ASGI front for https://bottube.ai/mcp.

nginx sends `location = /mcp` and `/mcp/server-card` here. For /mcp:

  * A JSON-RPC 2.0 POST goes to the official MCP SDK's Streamable HTTP app (stateless mode,
    JSON responses, so no session affinity is needed behind nginx).
  * A GET asking only for text/event-stream, and DELETE, get 405: a stateless server has no
    standalone SSE stream and no sessions (the spec allows 405 for both).
  * OPTIONS is answered here (CORS preflight, same {"ok": true} body as before).
  * Everything else -- the legacy `{tool, args}` / `{method, params}` POST format, a plain
    browser GET, HEAD -- is proxied unchanged to the old Flask handler at
    http://127.0.0.1:8097/mcp, so existing callers keep getting the old responses.

The real client IP (from nginx's X-Real-IP / X-Forwarded-For, trusted only from loopback)
is forwarded upstream as X-Forwarded-For, so BoTTube's per-IP rate limits count the client.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import __version__
from .tools import CLIENT_IP_HEADER, SITE, build_server
from .upstream import USER_AGENT, Upstream

log = logging.getLogger("bottube_mcp")

MAX_POST_BYTES = 1024 * 1024
LEGACY_TOOL_NAMES = frozenset({"feed.get", "video.get", "video.similar", "video.provenance", "video.keyframes"})
TRUSTED_PROXIES = frozenset({"127.0.0.1", "::1"})
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "trailers",
    "transfer-encoding", "upgrade", "content-length", "host",
})
LEGACY_FORWARD_HEADERS = ("content-type", "accept", "accept-language", "user-agent", "cookie", "origin",
                          "referer", "x-api-key", "authorization")
CORS_HEADERS = [
    (b"access-control-allow-origin", b"*"),
    (b"access-control-expose-headers", b"Mcp-Session-Id, MCP-Protocol-Version, Retry-After"),
]


@dataclass
class Settings:
    upstream_url: str = "http://127.0.0.1:8097"
    host_header: str = "bottube.ai"
    public_url: str = SITE + "/mcp"
    allowed_hosts: tuple[str, ...] = ("bottube.ai", "www.bottube.ai", "127.0.0.1", "localhost", "[::1]")
    upstream_timeout: float = 10.0
    legacy_timeout: float = 30.0
    transports: dict[str, Any] = field(default_factory=dict)  # tests: {"api": ..., "legacy": ...}

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls()
        s.upstream_url = os.environ.get("BOTTUBE_MCP_UPSTREAM", s.upstream_url)
        s.host_header = os.environ.get("BOTTUBE_MCP_UPSTREAM_HOST", s.host_header)
        s.public_url = os.environ.get("BOTTUBE_MCP_PUBLIC_URL", s.public_url)
        hosts = os.environ.get("BOTTUBE_MCP_ALLOWED_HOSTS")
        if hosts:
            s.allowed_hosts = tuple(h.strip().lower() for h in hosts.split(",") if h.strip())
        return s


# --------------------------------------------------------------------------- request helpers

def _header(scope: Scope, name: bytes) -> str:
    for k, v in scope.get("headers") or []:
        if k.lower() == name:
            return v.decode("latin-1")
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
    """The TCP peer, unless the peer is local nginx: then X-Real-IP, else the first X-Forwarded-For hop."""
    peer = (scope.get("client") or ("", 0))[0] or ""
    if peer in TRUSTED_PROXIES:
        for raw in (_header(scope, b"x-real-ip"), _header(scope, b"x-forwarded-for").split(",")[0]):
            ip = _valid_ip(raw)
            if ip:
                return ip
    return _valid_ip(peer) or "127.0.0.1"


def is_mcp_message(body: bytes) -> bool:
    """JSON-RPC 2.0 request/notification/response (or a batch of them) that is not a legacy tool call."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return False
    items = data if isinstance(data, list) and data else [data]
    for item in items:
        if not isinstance(item, dict) or item.get("jsonrpc") != "2.0":
            return False
        # A legacy client that adds "jsonrpc": "2.0" to {method: "feed.get"} still gets the legacy handler.
        if item.get("method") in LEGACY_TOOL_NAMES:
            return False
    return True


async def _send_simple(send: Send, status: int, body: bytes, headers: list[tuple[bytes, bytes]]) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": headers + [(b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


async def _json_error(send: Send, status: int, message: str) -> None:
    body = json.dumps({"ok": False, "error": message}).encode()
    await _send_simple(send, status, body, [(b"content-type", b"application/json")] + CORS_HEADERS)


async def read_body(receive: Receive, limit: int) -> bytes | None:
    """Whole request body, or None if it exceeds `limit` bytes."""
    chunks, size = [], 0
    while True:
        msg = await receive()
        if msg["type"] == "http.disconnect":
            return b"".join(chunks)
        chunk = msg.get("body", b"")
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
        if not msg.get("more_body"):
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


# --------------------------------------------------------------------------- the /mcp endpoint

class McpEndpoint:
    """Raw ASGI app mounted at /mcp: routes each request to the MCP SDK or the legacy Flask handler."""

    def __init__(self, mcp_app: ASGIApp, legacy: httpx.AsyncClient, settings: Settings):
        self.mcp_app = mcp_app
        self.legacy = legacy
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        method = scope["method"]
        ip = client_ip(scope)
        if method == "OPTIONS":
            await _send_simple(send, 200, b'{"ok": true}', [
                (b"content-type", b"application/json"),
                (b"access-control-allow-methods", b"GET, POST, DELETE, OPTIONS"),
                (b"access-control-allow-headers",
                 b"Content-Type, Accept, Authorization, Mcp-Session-Id, MCP-Protocol-Version, Last-Event-ID"),
                (b"access-control-max-age", b"600"),
            ] + CORS_HEADERS)
            return
        if method == "POST":
            body = await read_body(receive, MAX_POST_BYTES)
            if body is None:
                await _json_error(send, 413, "request body too large")
                return
            if is_mcp_message(body):
                await self._to_mcp(scope, replay_receive(body, receive), send, ip)
            else:
                await self._to_legacy(scope, body, send, ip)
            return
        accept = _header(scope, b"accept").lower()
        if (method == "GET" and "text/event-stream" in accept and "text/html" not in accept) or method == "DELETE":
            # Stateless server: no standalone SSE stream and no sessions to delete. The spec allows 405 for both.
            await _send_simple(send, 405, json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32000, "message": "Method not allowed: this server is stateless; use POST"},
            }).encode(), [(b"content-type", b"application/json"), (b"allow", b"GET, POST, OPTIONS")] + CORS_HEADERS)
            return
        body = await read_body(receive, MAX_POST_BYTES) or b""
        await self._to_legacy(scope, body, send, ip)

    async def _to_mcp(self, scope: Scope, receive: Receive, send: Send, ip: str) -> None:
        headers = [(k, v) for k, v in scope["headers"] if k.lower() != CLIENT_IP_HEADER.encode()]
        headers.append((CLIENT_IP_HEADER.encode(), ip.encode()))
        inner = dict(scope, headers=headers)

        async def _send(msg: Message) -> None:
            if msg["type"] == "http.response.start":
                existing = {k.lower() for k, _ in msg.get("headers", [])}
                extra = [(k, v) for k, v in CORS_HEADERS if k not in existing]
                msg = dict(msg, headers=list(msg.get("headers", [])) + extra)
            await send(msg)

        await self.mcp_app(inner, receive, _send)

    async def _to_legacy(self, scope: Scope, body: bytes, send: Send, ip: str) -> None:
        fwd = {}
        for name in LEGACY_FORWARD_HEADERS:
            v = _header(scope, name.encode())
            if v:
                fwd[name] = v
        fwd.update({
            "host": self.settings.host_header,
            "x-forwarded-for": ip,
            "x-real-ip": ip,
            "x-forwarded-proto": "https",
        })
        qs = scope.get("query_string", b"").decode("latin-1")
        url = "/mcp" + ("?" + qs if qs else "")
        try:
            resp = await self.legacy.request(scope["method"], url, content=body or None, headers=fwd)
        except httpx.HTTPError as exc:
            log.warning("legacy /mcp proxy failed: %r", exc)
            await _json_error(send, 502, "upstream unavailable")
            return
        out = [(k.lower().encode("latin-1"), v.encode("latin-1"))
               for k, v in resp.headers.multi_items() if k.lower() not in HOP_BY_HOP]
        payload = b"" if scope["method"] == "HEAD" else resp.content
        await send({"type": "http.response.start", "status": resp.status_code,
                    "headers": out + [(b"content-length", str(len(resp.content)).encode())]})
        await send({"type": "http.response.body", "body": payload})


# --------------------------------------------------------------------------- host check

class HostCheck:
    """Reject requests whose Host is not BoTTube or loopback (DNS-rebinding guard)."""

    def __init__(self, app: ASGIApp, allowed: tuple[str, ...]):
        self.app = app
        self.allowed = {h.lower() for h in allowed}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            host = _header(scope, b"host").lower()
            name = host.rsplit(":", 1)[0] if not host.endswith("]") else host
            if name not in self.allowed:
                await _send_simple(send, 421, b"misdirected request", [(b"content-type", b"text/plain")])
                return
        await self.app(scope, receive, send)


# --------------------------------------------------------------------------- server card

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
    upstream = Upstream(settings.upstream_url, host_header=settings.host_header,
                        timeout=settings.upstream_timeout, transport=settings.transports.get("api"))
    legacy = httpx.AsyncClient(base_url=settings.upstream_url.rstrip("/"),
                               timeout=httpx.Timeout(settings.legacy_timeout, connect=3.0),
                               follow_redirects=False, transport=settings.transports.get("legacy"),
                               headers={"user-agent": USER_AGENT})
    mcp = build_server(upstream)
    # Host checking is done once, by HostCheck, for every route; the SDK's own check is off.
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/mcp", stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    endpoint = McpEndpoint(mcp_app, legacy, settings)
    card_cache: dict[str, Any] = {}

    async def card(request: Request) -> Response:
        if "card" not in card_cache:
            tools = [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in await mcp.list_tools()]
            card_cache["card"] = server_card(tools, settings)
        return JSONResponse(card_cache["card"], headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Content-Type, If-None-Match",
            "Access-Control-Expose-Headers": "ETag",
            "Cache-Control": "public, max-age=3600",
        })

    async def health(request: Request) -> Response:
        return JSONResponse({"ok": True, "service": "bottube-mcp", "version": __version__})

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            try:
                yield
            finally:
                await upstream.aclose()
                await legacy.aclose()

    app = Starlette(
        routes=[
            Route("/mcp", endpoint=endpoint),
            Route("/mcp/server-card", card, methods=["GET", "HEAD"]),
            # Kept for clients configured against the pre-SEP-2127 preview location.
            Route("/.well-known/mcp/server-card.json", card, methods=["GET", "HEAD"]),
            Route("/healthz", health, methods=["GET"]),
        ],
        lifespan=lifespan,
    )
    app.add_middleware(HostCheck, allowed=settings.allowed_hosts)
    app.state.mcp = mcp
    return app
