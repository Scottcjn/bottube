"""Integration test: the server runs locally, its upstream is the LIVE public API at https://bottube.ai.

Skipped unless BOTTUBE_MCP_LIVE=1. Read-only GETs only, about a dozen upstream requests in total.
Uses the official MCP Python client: initialize, tools/list, then one call per tool.
Run:  BOTTUBE_MCP_LIVE=1 python -m pytest bottube_mcp/tests/test_live.py -s
"""

from __future__ import annotations

import json
import os

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from bottube_mcp.app import Settings

pytestmark = pytest.mark.skipif(os.environ.get("BOTTUBE_MCP_LIVE") != "1",
                                reason="live test; set BOTTUBE_MCP_LIVE=1")

LINES: list[str] = []


def say(line: str) -> None:
    LINES.append(line)
    print(line)


def short(obj, n=420) -> str:
    s = json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "...(%d chars)" % len(s)


@pytest.mark.anyio
async def test_live_round_trip(run_server):
    upstream_requests: list[str] = []

    class Counting(httpx.AsyncHTTPTransport):
        async def handle_async_request(self, request):
            upstream_requests.append("%s %s" % (request.method, request.url.raw_path.decode()))
            return await super().handle_async_request(request)

    srv = run_server(Settings(upstream_url="https://bottube.ai", host_header="bottube.ai",
                              transports={"api": Counting()}))
    async with streamable_http_client(srv.url + "/mcp/v1") as (read, write):
        async with ClientSession(read, write) as s:
            init = await s.initialize()
            say("initialize -> protocol %s, server %s %s" % (init.protocol_version, init.server_info.name,
                                                             init.server_info.version))
            tools = (await s.list_tools()).tools
            say("tools/list -> %s" % ", ".join(t.name for t in tools))
            assert {t.name for t in tools} == {"search", "fetch", "list_feed", "get_video", "list_comments",
                                               "get_agent"}

            async def call(name, args):
                res = await s.call_tool(name, args)
                say("tools/call %s %s -> isError=%s %s" % (name, json.dumps(args), res.is_error,
                                                           short(res.structured_content)))
                assert res.is_error is False, res.content
                return res.structured_content

            found = await call("search", {"query": "robot"})
            assert found["results"], "live search returned nothing"
            vid = found["results"][0]["id"]
            assert found["results"][0]["url"] == "https://bottube.ai/watch/%s" % vid
            doc = await call("fetch", {"id": vid})
            assert doc["id"] == vid and doc["text"]
            detail = await call("get_video", {"video_id": vid})
            assert detail["stream_url"] == "https://bottube.ai/api/videos/%s/stream" % vid
            await call("list_comments", {"video_id": vid, "limit": 5})
            feed = await call("list_feed", {"limit": 3})
            assert 1 <= feed["count"] <= 3
            agent = await call("get_agent", {"agent_name": doc["metadata"]["agent"], "per_page": 3})
            assert agent["agent"]["profile_url"].startswith("https://bottube.ai/agent/")

    say("upstream requests made: %d" % len(upstream_requests))
    for u in upstream_requests:
        say("  " + u)
    assert len(upstream_requests) <= 15
    out = os.environ.get("BOTTUBE_MCP_TRANSCRIPT")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(LINES) + "\n")
