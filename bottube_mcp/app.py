"""ASGI front for https://bottube.ai/mcp.

nginx sends `location = /mcp` and `/mcp/server-card` here. For /mcp:

  * A JSON-RPC 2.0 POST goes to the official MCP SDK's Streamable HTTP app (stateless mode,
    JSON responses, so no session affinity is needed behind nginx).
  * A GET accepting text/event-stream gets 405 (stateless server, no standalone SSE stream).
  * Everything else -- all non-JSON-RPC POSTs and every other HTTP method -- is proxied to Flask at
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
MAX_LEGACY_REQUEST_BYTES = 550 * 1024 * 1024
MAX_LEGACY_RESPONSE_BYTES = 4 * 1024 * 1024
TRUSTED_PROXY = "127.0.0.1"
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "trailers",
    "transfer-encoding", "upgrade", "host",
})
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
    """Trust nginx's overwritten XFF only for an IPv4-loopback TCP peer."""
    peer = (scope.get("client") or ("", 0))[0] or ""
    if peer == TRUSTED_PROXY:
        ip = _valid_ip(_header(scope, b"x-forwarded-for"))
        if ip:
            return ip
    return _valid_ip(peer) or "127.0.0.1"


def is_mcp_message(body: bytes) -> bool:
    """Whether a JSON object (or every item in a non-empty batch) has a jsonrpc field."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return False
    items = data if isinstance(data, list) and data else [data]
    return bool(items) and all(isinstance(item, dict) and "jsonrpc" in item for item in items)


def _is_json_content_type(scope: Scope) -> bool:
    return _header(scope, b"content-type").partition(";")[0].strip().lower() == "application/json"


def _connection_tokens(headers: list[tuple[bytes, bytes]]) -> set[str]:
    tokens: set[str] = set()
    for name, value in headers:
        if name.lower() == b"connection":
            tokens.update(token.strip().lower() for token in value.decode("latin-1").split(",") if token.strip())
    return tokens


async def _send_simple(send: Send, status: int, body: bytes, headers: list[tuple[bytes, bytes]]) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": headers + [(b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


async def _json_error(send: Send, status: int, message: str) -> None:
    body = json.dumps({"ok": False, "error": message}).encode()
    await _send_simple(send, status, body, [(b"content-type", b"application/json")] + CORS_HEADERS)


async def _invalid_jsonrpc(send: Send, body: bytes) -> bool:
    """Return a JSON-RPC Invalid Request response for shapes known to crash some SDK versions."""
    data = json.loads(body)
    items = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict):
            continue
        method = item.get("method")
        if "method" in item and not isinstance(method, str):
            request_id = item.get("id")
            if not isinstance(request_id, (str, int, float)) or isinstance(request_id, bool):
                request_id = None
            payload = json.dumps({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32600, "message": "Invalid Request"},
            }).encode()
            await _send_simple(send, 400, payload, [(b"content-type", b"application/json")] + CORS_HEADERS)
            return True
    return False


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
        if method == "POST":
            body = await read_body(receive, MAX_LEGACY_REQUEST_BYTES)
            if body is None:
                await _json_error(send, 413, "request body too large")
                return
            if _is_json_content_type(scope) and is_mcp_message(body):
                if len(body) > MAX_POST_BYTES:
                    await _json_error(send, 413, "request body too large")
                    return
                if await _invalid_jsonrpc(send, body):
                    return
                await self._to_mcp(scope, replay_receive(body, receive), send, ip)
            else:
                await self._to_legacy(scope, body, send, ip)
            return
        accept = _header(scope, b"accept").lower()
        if method == "GET" and "text/event-stream" in accept:
            # Stateless server: no standalone server-to-client SSE stream (MCP spec allows 405 here).
            # Answer directly instead of handing the request to the SDK, which can hold it open.
            body405 = b'{"error":"SSE stream not offered; use POST (stateless MCP)"}'
            await send({"type": "http.response.start", "status": 405,
                        "headers": [(b"allow", b"POST"), (b"content-type", b"application/json"),
                                    (b"content-length", str(len(body405)).encode())]})
            await send({"type": "http.response.body", "body": body405})
            return
        body = await read_body(receive, MAX_LEGACY_REQUEST_BYTES)
        if body is None:
            await _json_error(send, 413, "request body too large")
            return
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
        incoming = list(scope.get("headers") or [])
        connection_tokens = _connection_tokens(incoming)
        fwd: list[tuple[str, str]] = []
        for raw_name, raw_value in incoming:
            name = raw_name.decode("latin-1").lower()
            if name not in HOP_BY_HOP and name not in connection_tokens and name not in {
                "x-forwarded-for", "x-real-ip", "x-forwarded-proto", "content-length", "accept-encoding"
            }:
                fwd.append((name, raw_value.decode("latin-1")))
        fwd.extend([
            ("host", self.settings.host_header),
            ("x-forwarded-for", ip),
            ("x-real-ip", ip),
            ("x-forwarded-proto", "https"),
            ("accept-encoding", "identity"),
        ])
        qs = scope.get("query_string", b"").decode("latin-1")
        url = "/mcp" + ("?" + qs if qs else "")
        try:
            request = self.legacy.build_request(scope["method"], url, content=body, headers=fwd)
            resp = await self.legacy.send(request, stream=True)
            try:
                chunks: list[bytes] = []
                size = 0
                decoded_response = resp.is_stream_consumed
                if decoded_response:
                    # MockTransport may provide an already-decoded, in-memory response.
                    chunks.append(resp.content)
                    size = len(resp.content)
                else:
                    async for chunk in resp.aiter_raw():
                        size += len(chunk)
                        if size > MAX_LEGACY_RESPONSE_BYTES:
                            await _json_error(send, 502, "upstream response too large")
                            return
                        chunks.append(chunk)
                if size > MAX_LEGACY_RESPONSE_BYTES:
                    await _json_error(send, 502, "upstream response too large")
                    return
                payload = b"".join(chunks)
            finally:
                await resp.aclose()
        except httpx.HTTPError as exc:
            log.warning("legacy /mcp proxy failed: %r", exc)
            await _json_error(send, 502, "upstream unavailable")
            return
        response_headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in resp.headers.multi_items()]
        connection_tokens = _connection_tokens(response_headers)
        out = [(k.lower(), v) for k, v in response_headers
               if k.decode("latin-1").lower() not in HOP_BY_HOP
               and k.decode("latin-1").lower() not in connection_tokens
               and not (decoded_response and scope["method"] != "HEAD"
                        and k.decode("latin-1").lower() in {"content-encoding", "content-length"})]
        if decoded_response and scope["method"] != "HEAD":
            out.append((b"content-length", str(len(payload)).encode()))
        await send({"type": "http.response.start", "status": resp.status_code,
                    "headers": out})
        await send({"type": "http.response.body", "body": b"" if scope["method"] == "HEAD" else payload})


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
                               trust_env=False,
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
