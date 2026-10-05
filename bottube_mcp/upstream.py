"""HTTP client for BoTTube's public REST API (the Flask app on 127.0.0.1:8097).

Every call forwards the MCP client's IP as X-Forwarded-For, so BoTTube's per-IP
rate limits count the real client and not this service. Upstream failures are
turned into typed exceptions that the tool layer maps to MCP tool errors.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

import httpx

from . import __version__

USER_AGENT = "bottube-mcp/%s (+https://bottube.ai/mcp)" % __version__
MAX_BODY_BYTES = 4 * 1024 * 1024  # largest upstream body we will parse


class UpstreamError(Exception):
    """Base class. `code` is a stable machine-readable string."""

    code = "upstream_error"

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


class RateLimited(UpstreamError):
    code = "rate_limited"

    def __init__(self, message: str, retry_after: int):
        super().__init__(message, status=429)
        self.retry_after = retry_after


class NotFound(UpstreamError):
    code = "not_found"


class BadRequest(UpstreamError):
    code = "bad_request"


class Forbidden(UpstreamError):
    code = "forbidden"


class Unavailable(UpstreamError):
    code = "upstream_unavailable"


def _retry_after(resp: httpx.Response, body: Any) -> int:
    """Seconds to wait: Retry-After header, else body.retry_after, else 60. Clamped to 1..3600."""
    for raw in (resp.headers.get("Retry-After"), body.get("retry_after") if isinstance(body, dict) else None):
        try:
            secs = int(float(raw))
        except (TypeError, ValueError):
            continue
        return max(1, min(3600, secs))
    return 60


def _error_message(body: Any, fallback: str) -> str:
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, str) and err.strip():
            return err.strip()[:300]
        if isinstance(err, dict) and isinstance(err.get("message"), str):
            return err["message"][:300]
    return fallback


class Upstream:
    """Thin async wrapper around one shared httpx.AsyncClient."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8097",
        *,
        host_header: str = "bottube.ai",
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.host_header = host_header
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=3.0),
            follow_redirects=False,
            transport=transport,
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=8),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self, client_ip: str | None, accept: str = "application/json") -> dict[str, str]:
        h = {
            "Host": self.host_header,
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "X-Forwarded-Proto": "https",
        }
        if client_ip:
            h["X-Forwarded-For"] = client_ip
            h["X-Real-IP"] = client_ip
        return h

    async def _get(self, path: str, params: Mapping[str, Any] | None, client_ip: str | None,
                   accept: str) -> httpx.Response:
        clean = {k: str(v) for k, v in (params or {}).items() if v is not None and v != ""}
        try:
            resp = await self._client.get(path, params=clean, headers=self._headers(client_ip, accept))
        except httpx.TimeoutException as exc:
            raise Unavailable("BoTTube API timed out") from exc
        except httpx.HTTPError as exc:
            raise Unavailable("BoTTube API unreachable") from exc
        if len(resp.content) > MAX_BODY_BYTES:
            raise Unavailable("BoTTube API response too large")
        return resp

    @staticmethod
    def _raise_for(resp: httpx.Response, body: Any) -> None:
        s = resp.status_code
        if s < 400:
            return
        if s == 429:
            secs = _retry_after(resp, body)
            raise RateLimited(_error_message(body, "Rate limited") + "; retry after %d s" % secs, secs)
        if s == 404:
            raise NotFound(_error_message(body, "Not found"), status=s)
        if s == 403:
            raise Forbidden(_error_message(body, "Request refused by BoTTube"), status=s)
        if 400 <= s < 500:
            raise BadRequest(_error_message(body, "Bad request (HTTP %d)" % s), status=s)
        raise Unavailable("BoTTube API error (HTTP %d)" % s, status=s)

    async def get_json(self, path: str, params: Mapping[str, Any] | None = None, *,
                       client_ip: str | None = None) -> dict[str, Any]:
        resp = await self._get(path, params, client_ip, "application/json")
        try:
            body = resp.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            body = None
        self._raise_for(resp, body)
        if not isinstance(body, dict):
            raise Unavailable("BoTTube API returned a non-JSON body (HTTP %d)" % resp.status_code)
        return body

    async def get_text(self, path: str, params: Mapping[str, Any] | None = None, *,
                       client_ip: str | None = None) -> str:
        resp = await self._get(path, params, client_ip, "text/plain, text/vtt, */*")
        self._raise_for(resp, None)
        return resp.text
