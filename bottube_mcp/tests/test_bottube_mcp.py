"""Unit tests against a mocked BoTTube API (no network). The MCP side uses the official client."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
from jsonschema import FormatChecker, validate
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from bottube_mcp.app import Settings, is_mcp_message

VIDEO = {
    "video_id": "abcDEF12345", "title": "Robots dancing", "description": "Two robots dance.",
    "tags": ["robots", "dance"], "category": "music", "category_name": "Music", "duration_sec": 7.5,
    "width": 720, "height": 720, "views": 120, "likes": 9, "dislikes": 1, "created_at": 1759600000.0,
    "agent_name": "robo-agent", "display_name": "Robo Agent", "avatar_url": "/avatars/robo.png",
    "thumbnail_url": "/thumbnails/abcDEF12345.jpg", "url": "/api/videos/abcDEF12345/stream",
    "watch_url": "/watch/abcDEF12345", "api_key": "MUST-NOT-LEAK",
}
LEGACY_DESCRIPTOR = {"schema_version": "1.0", "name": "bottube", "tools": [{"name": "feed.get"}]}
TOOL_NAMES = {"search", "fetch", "list_feed", "get_video", "list_comments", "get_agent"}
BANNED = re.compile(r"(?i)\bexchange\b|\bprice\b|liquidity|\bearn|cash[ -]?out|withdraw")
REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeBoTTube:
    """Records every upstream request; routes by path."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.override: dict[str, httpx.Response] = {}

    def api(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        p = request.url.path
        if p in self.override:
            return self.override[p]
        if p == "/api/search":
            return httpx.Response(200, json={"query": request.url.params["q"], "videos": [VIDEO], "total": 1})
        if p == "/api/videos/abcDEF12345":
            return httpx.Response(200, json=VIDEO)
        if p == "/api/videos/abcDEF12345/transcript":
            return httpx.Response(200, json={"plain_text": "Beep boop, we dance."})
        if p == "/api/videos/abcDEF12345/captions":
            return httpx.Response(200, text="WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\nCaption line\n")
        if p == "/api/videos/abcDEF12345/provenance":
            return httpx.Response(200, json={"ok": True, "state": "verified", "canonical_sha256": "ab" * 32})
        if p == "/api/videos/abcDEF12345/comments":
            rows = [{"id": i, "agent_name": "c%d" % i, "content": "comment %d" % i, "created_at": 1759600000 + i,
                     "likes": i, "parent_id": None, "is_human": i == 1} for i in range(1, 8)]
            return httpx.Response(200, json={"comments": rows, "count": len(rows)})
        if p in ("/api/feed", "/api/trending"):
            return httpx.Response(200, json={"videos": [VIDEO, dict(VIDEO, video_id="zzzZZZ99999")]})
        if p == "/api/agents/robo-agent":
            return httpx.Response(200, json={
                "agent": {"agent_name": "robo-agent", "display_name": "Robo Agent", "avatar_url": "/avatars/r.png",
                          "is_human": 0, "created_at": 1750000000, "id": 7, "rtc_balance": 99},
                "videos": [VIDEO], "video_count": 41, "page": 2, "per_page": 20, "total": 41, "pages": 3,
                "has_more": True})
        return httpx.Response(404, json={"error": "Video not found"})

    def legacy(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=LEGACY_DESCRIPTOR, headers={"x-legacy": "1"})
        body = json.loads(request.content or b"{}")
        return httpx.Response(200, json={"ok": True, "tool": body.get("tool") or body.get("method"),
                                         "result": {"echo": body}}, headers={"x-legacy": "1"})


@pytest.fixture
def fake():
    return FakeBoTTube()


@pytest.fixture
def server(run_server, fake):
    return run_server(Settings(transports={"api": httpx.MockTransport(fake.api),
                                           "legacy": httpx.MockTransport(fake.legacy)}))


async def _session_call(url, fn):
    async with streamable_http_client(url + "/mcp") as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            return await fn(s)


def rpc(server, method, params=None, *, headers=None, rid=1):
    h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
         "MCP-Protocol-Version": "2025-06-18"}
    h.update(headers or {})
    body = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
    return httpx.post(server.url + "/mcp", json=body, headers=h, timeout=10)


# --------------------------------------------------------------------------- protocol

def test_initialize_raw_2025_06_18(server):
    r = rpc(server, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                   "clientInfo": {"name": "raw", "version": "0"}})
    assert r.status_code == 200
    res = r.json()["result"]
    assert res["serverInfo"]["name"] == "bottube"
    assert res["protocolVersion"] == "2025-06-18"
    assert "tools" in res["capabilities"]
    assert r.headers["access-control-allow-origin"] == "*"
    assert "mcp-session-id" not in r.headers  # stateless


def test_tools_list_raw_without_initialize(server):
    # Stateless: every POST is independent, so tools/list works on its own (no session affinity needed).
    r = rpc(server, "tools/list")
    assert r.status_code == 200
    tools = r.json()["result"]["tools"]
    assert {t["name"] for t in tools} == TOOL_NAMES
    for t in tools:
        assert t["annotations"]["readOnlyHint"] is True
        assert t["outputSchema"]["type"] == "object"


@pytest.mark.anyio
async def test_official_client_lists_and_calls(server):
    async def go(s):
        names = {t.name for t in (await s.list_tools()).tools}
        res = await s.call_tool("search", {"query": "robots"})
        return names, res

    names, res = await _session_call(server.url, go)
    assert names == TOOL_NAMES
    assert res.is_error is False
    assert res.structured_content == {"results": [
        {"id": "abcDEF12345", "title": "Robots dancing", "url": "https://bottube.ai/watch/abcDEF12345"}]}
    # deep research shape: exactly one text item holding the JSON
    assert len(res.content) == 1 and json.loads(res.content[0].text) == res.structured_content


# --------------------------------------------------------------------------- tools

@pytest.mark.anyio
async def test_fetch_document(server, fake):
    res = await _session_call(server.url, lambda s: s.call_tool("fetch", {"id": "abcDEF12345"}))
    d = res.structured_content
    assert set(d) == {"id", "title", "text", "url", "metadata"}
    assert d["url"] == "https://bottube.ai/watch/abcDEF12345"
    assert "Two robots dance." in d["text"] and "Beep boop, we dance." in d["text"]
    m = d["metadata"]
    assert (m["agent"], m["views"], m["likes"], m["duration_sec"], m["category"]) == ("robo-agent", 120, 9, 7.5, "music")
    assert m["created_at"] == "2025-10-04T17:46:40Z" and m["transcript_source"] == "transcript"
    assert len(res.content) == 1 and json.loads(res.content[0].text) == d
    assert "MUST-NOT-LEAK" not in json.dumps(d)


@pytest.mark.anyio
async def test_fetch_falls_back_to_captions(server, fake):
    fake.override["/api/videos/abcDEF12345/transcript"] = httpx.Response(404, json={"error": "Transcript not found"})
    res = await _session_call(server.url, lambda s: s.call_tool("fetch", {"id": "abcDEF12345"}))
    assert "Caption line" in res.structured_content["text"]
    assert "-->" not in res.structured_content["text"]
    assert res.structured_content["metadata"]["transcript_source"] == "captions"


@pytest.mark.anyio
async def test_list_feed_buckets(server, fake):
    res = await _session_call(server.url, lambda s: s.call_tool("list_feed", {"limit": 1}))
    assert res.structured_content["count"] == 1
    v = res.structured_content["videos"][0]
    assert v["watch_url"] == "https://bottube.ai/watch/abcDEF12345"
    assert v["stream_url"] == "https://bottube.ai/api/videos/abcDEF12345/stream"
    assert v["thumbnail_url"] == "https://bottube.ai/thumbnails/abcDEF12345.jpg"
    feed = [c for c in fake.calls if c.url.path == "/api/feed"][-1]
    assert feed.url.params["per_page"] == "1" and feed.url.params["bucket"] == "latest"
    assert feed.url.params["surface"] == "mcp"
    assert len(res.content) == 2 and res.content[0].text.startswith("1 latest videos")

    args = {"bucket": "trending", "category": "music"}
    res = await _session_call(server.url, lambda s: s.call_tool("list_feed", args))
    tr = [c for c in fake.calls if c.url.path == "/api/trending"][-1]
    assert tr.url.params["category"] == "music" and res.structured_content["bucket"] == "trending"


@pytest.mark.anyio
async def test_list_feed_rejects_bad_input(server, fake):
    res = await _session_call(server.url, lambda s: s.call_tool("list_feed", {"bucket": "everything"}))
    assert res.is_error
    res = await _session_call(server.url, lambda s: s.call_tool("list_feed", {"limit": 500}))
    assert res.is_error
    res = await _session_call(server.url, lambda s: s.call_tool("list_feed", {"category": "../x"}))
    assert res.is_error
    assert not [c for c in fake.calls if c.url.path == "/api/feed"]


@pytest.mark.anyio
async def test_get_video_with_provenance(server, fake):
    res = await _session_call(server.url, lambda s: s.call_tool("get_video", {"video_id": "abcDEF12345"}))
    d = res.structured_content
    assert d["provenance"]["state"] == "verified"
    assert d["watch_url"].startswith("https://bottube.ai/") and d["stream_url"].endswith("/stream")
    assert d["agent_url"] == "https://bottube.ai/agent/robo-agent"
    assert d["tags"] == ["robots", "dance"] and d["width"] == 720


@pytest.mark.anyio
async def test_get_video_without_provenance(server, fake):
    fake.override["/api/videos/abcDEF12345/provenance"] = httpx.Response(500, text="boom")
    res = await _session_call(server.url, lambda s: s.call_tool("get_video", {"video_id": "abcDEF12345"}))
    assert res.is_error is False and res.structured_content["provenance"] is None


@pytest.mark.anyio
async def test_list_comments_limit(server):
    args = {"video_id": "abcDEF12345", "limit": 3}
    res = await _session_call(server.url, lambda s: s.call_tool("list_comments", args))
    d = res.structured_content
    assert (d["total"], d["returned"]) == (7, 3)
    assert [c["agent"] for c in d["comments"]] == ["c1", "c2", "c3"] and d["comments"][0]["is_human"] is True


@pytest.mark.anyio
async def test_get_agent_paged(server, fake):
    args = {"agent_name": "robo-agent", "page": 2, "per_page": 20}
    res = await _session_call(server.url, lambda s: s.call_tool("get_agent", args))
    d = res.structured_content
    call = [c for c in fake.calls if c.url.path == "/api/agents/robo-agent"][-1]
    assert call.url.params["page"] == "2" and call.url.params["per_page"] == "20"
    assert (d["total"], d["pages"], d["has_more"]) == (41, 3, True)
    assert d["agent"]["avatar_url"] == "https://bottube.ai/avatars/r.png"
    assert d["agent"]["profile_url"] == "https://bottube.ai/agent/robo-agent"
    assert "rtc_balance" not in json.dumps(d) and '"id": 7' not in json.dumps(d)


# --------------------------------------------------------------------------- errors

@pytest.mark.anyio
async def test_rate_limit_maps_to_tool_error(server, fake):
    fake.override["/api/search"] = httpx.Response(
        429, json={"error": "Search rate limit exceeded", "code": "rate_limited", "retry_after": 42},
        headers={"Retry-After": "42"})
    res = await _session_call(server.url, lambda s: s.call_tool("search", {"query": "x"}))
    assert res.is_error is True
    assert res.structured_content["error"]["code"] == "rate_limited"
    assert res.structured_content["error"]["retry_after"] == 42
    assert "retry after 42 s" in res.content[0].text


@pytest.mark.anyio
async def test_not_found_and_invalid_id(server, fake):
    res = await _session_call(server.url, lambda s: s.call_tool("get_video", {"video_id": "nopeNOPE123"}))
    assert res.is_error and res.structured_content["error"]["code"] == "not_found"
    before = len(fake.calls)
    res = await _session_call(server.url, lambda s: s.call_tool("fetch", {"id": "../../etc"}))
    assert res.is_error and len(fake.calls) == before  # rejected before any upstream call


def test_upstream_timeout_is_tool_error(run_server):
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    srv = run_server(Settings(transports={"api": httpx.MockTransport(slow), "legacy": httpx.MockTransport(slow)}))
    r = rpc(srv, "tools/call", {"name": "search", "arguments": {"query": "x"}})
    res = r.json()["result"]
    assert res["isError"] is True and res["structuredContent"]["error"]["code"] == "upstream_unavailable"


# --------------------------------------------------------------------------- client IP forwarding

def test_real_client_ip_forwarded_from_nginx_headers(server, fake):
    r = rpc(server, "tools/call", {"name": "search", "arguments": {"query": "ip"}},
            headers={"X-Real-IP": "203.0.113.9", "X-Forwarded-For": "203.0.113.9",
                     "X-Bottube-Mcp-Client-Ip": "1.2.3.4"})
    assert r.status_code == 200 and r.json()["result"]["isError"] is False
    call = [c for c in fake.calls if c.url.path == "/api/search"][-1]
    assert call.headers["x-forwarded-for"] == "203.0.113.9"
    assert call.headers["host"] == "bottube.ai"
    assert call.headers["user-agent"].startswith("bottube-mcp/")


def test_garbage_forwarded_header_falls_back_to_peer(server, fake):
    rpc(server, "tools/call", {"name": "search", "arguments": {"query": "ip"}},
        headers={"X-Real-IP": "not-an-ip", "X-Forwarded-For": "also bad"})
    call = [c for c in fake.calls if c.url.path == "/api/search"][-1]
    assert call.headers["x-forwarded-for"] == "127.0.0.1"


# --------------------------------------------------------------------------- legacy compatibility

def test_legacy_tool_post_is_proxied_unchanged(server, fake):
    r = httpx.post(server.url + "/mcp", json={"tool": "feed.get", "args": {"per_page": 1}},
                   headers={"X-Real-IP": "198.51.100.7"}, timeout=10)
    assert r.status_code == 200 and r.headers["x-legacy"] == "1"
    assert r.json() == {"ok": True, "tool": "feed.get", "result": {"echo": {"tool": "feed.get",
                                                                            "args": {"per_page": 1}}}}
    call = fake.calls[-1]
    assert call.url.path == "/mcp" and call.headers["x-forwarded-for"] == "198.51.100.7"
    assert call.headers["host"] == "bottube.ai"


def test_legacy_method_params_with_jsonrpc_still_legacy(server, fake):
    r = httpx.post(server.url + "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "video.get",
                                              "params": {"video_id": "abcDEF12345"}}, timeout=10)
    assert r.headers.get("x-legacy") == "1" and r.json()["tool"] == "video.get"


def test_browser_get_goes_to_legacy(server):
    r = httpx.get(server.url + "/mcp", headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}, timeout=10)
    assert r.status_code == 200 and r.json() == LEGACY_DESCRIPTOR and r.headers["x-legacy"] == "1"
    r = httpx.get(server.url + "/mcp", timeout=10)
    assert r.json() == LEGACY_DESCRIPTOR


def test_sse_get_goes_to_mcp(server):
    r = httpx.get(server.url + "/mcp", headers={"Accept": "text/event-stream"}, timeout=10)
    assert "x-legacy" not in r.headers
    assert r.status_code == 405  # stateless server: no standalone SSE stream
    r = httpx.delete(server.url + "/mcp", timeout=10)
    assert r.status_code == 405 and "x-legacy" not in r.headers


def test_options_preflight(server):
    r = httpx.options(server.url + "/mcp", timeout=10)
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert "MCP-Protocol-Version" in r.headers["access-control-allow-headers"]
    assert r.headers["access-control-allow-origin"] == "*"


def test_classifier():
    assert is_mcp_message(b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
    assert is_mcp_message(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
    assert is_mcp_message(b'[{"jsonrpc":"2.0","id":1,"method":"tools/list"}]')
    assert not is_mcp_message(b'{"tool":"feed.get","args":{}}')
    assert not is_mcp_message(b'{"method":"feed.get","params":{}}')
    assert not is_mcp_message(b'{"jsonrpc":"2.0","method":"feed.get"}')
    assert not is_mcp_message(b'not json')
    assert not is_mcp_message(b'[]')
    assert not is_mcp_message(b'[{"jsonrpc":"2.0","method":"tools/list"}, {"tool":"x"}]')


def test_body_limit(server):
    r = httpx.post(server.url + "/mcp", content=b"{" + b" " * (1024 * 1024 + 10) + b"}",
                   headers={"Content-Type": "application/json"}, timeout=10)
    assert r.status_code == 413


def test_foreign_host_rejected(server):
    r = httpx.post(server.url + "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                   headers={"Host": "evil.example", "Accept": "application/json, text/event-stream"}, timeout=10)
    assert r.status_code == 421
    r = httpx.get(server.url + "/healthz", headers={"Host": "bottube.ai"}, timeout=10)
    assert r.status_code == 200 and r.json()["ok"] is True


# --------------------------------------------------------------------------- discovery + copy

def test_server_card(server):
    r = httpx.get(server.url + "/mcp/server-card", timeout=10)
    card = r.json()
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "*"
    assert r.headers["content-type"].split(";", 1)[0] == "application/json"
    assert card["name"] == "ai.bottube/bottube"
    assert card["description"] and card["version"] == "0.1.0"
    assert card["remotes"] == [{"type": "streamable-http", "url": "https://bottube.ai/mcp"}]
    assert card["transport"] == {"type": "streamable-http", "endpoint": "https://bottube.ai/mcp"}
    assert {t["name"] for t in card["tools"]} == TOOL_NAMES
    assert all(t.get("description") and "inputSchema" in t for t in card["tools"])
    assert card["authentication"]["required"] is False

    # The compatibility route serves the same generated card.
    old = httpx.get(server.url + "/.well-known/mcp/server-card.json", timeout=10)
    assert old.status_code == 200 and old.json() == card


def test_server_json_matches_registry_schema():
    manifest = json.loads((REPO_ROOT / "bottube_mcp/server.json").read_text(encoding="utf-8"))
    schema = json.loads((REPO_ROOT.parent / "ref/server.schema.json").read_text(encoding="utf-8"))
    validate(instance=manifest, schema=schema, format_checker=FormatChecker())
    assert manifest["name"] == "ai.bottube/bottube"
    assert manifest["remotes"] == [{"type": "streamable-http", "url": "https://bottube.ai/mcp"}]
    assert manifest["repository"]["subfolder"] == "bottube_mcp"


def test_ai_catalog_shape():
    catalog = json.loads((REPO_ROOT / "deploy/ai-catalog.json").read_text(encoding="utf-8"))
    assert catalog["specVersion"] == "1.0"
    assert catalog["entries"] == [
        {
            "identifier": "urn:air:bottube.ai:mcp:bottube",
            "type": "application/mcp-server-card+json",
            "url": "https://bottube.ai/mcp/server-card",
        },
        {
            "identifier": "urn:air:bottube.ai:a2a:bottube",
            "type": "application/a2a-agent-card+json",
            "url": "https://bottube.ai/.well-known/agent-card.json",
        },
    ]
    assert all(set(entry) == {"identifier", "type", "url"} for entry in catalog["entries"])


def test_copy_has_no_money_language(server):
    card = httpx.get(server.url + "/mcp/server-card", timeout=10).text
    init = rpc(server, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "raw", "version": "0"}}).text
    tools = rpc(server, "tools/list").text
    for text in (card, init, tools):
        m = BANNED.search(text)
        assert not m, "banned wording %r" % (m.group(0) if m else "")


@pytest.mark.anyio
async def test_unified_client_auto_mode(server):
    """mcp.Client in its default "auto" mode (newest protocol it can negotiate, else the initialize handshake)."""
    from mcp.client.client import Client

    async with Client(server.url + "/mcp") as c:
        names = {t.name for t in (await c.list_tools()).tools}
        res = await c.call_tool("get_video", {"video_id": "abcDEF12345"})
    assert names == TOOL_NAMES
    assert res.is_error is False and res.structured_content["id"] == "abcDEF12345"
