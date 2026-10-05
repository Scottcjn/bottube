"""The six read-only BoTTube MCP tools.

Every tool returns a CallToolResult with:
  * structuredContent - the typed result (schema advertised as outputSchema), and
  * text content - for `search` and `fetch` exactly one text item holding the
    JSON-encoded result (the shape ChatGPT deep research parses); for the other
    tools a one-paragraph summary followed by the JSON.

Upstream failures become tool errors (isError: true) whose structuredContent is
{"error": {"code", "message", "retry_after"?}}; a BoTTube 429 carries
retry_after in seconds.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from typing import Annotated, Any, Literal, Optional
from urllib.parse import quote

from mcp.server.mcpserver import Context, MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .upstream import NotFound, RateLimited, Upstream, UpstreamError

SITE = "https://bottube.ai"
CLIENT_IP_HEADER = "x-bottube-mcp-client-ip"  # set by app.py from the TCP peer / nginx; never from the client
VIDEO_ID_PATTERN = r"^[A-Za-z0-9_-]{5,32}$"
AGENT_NAME_PATTERN = r"^[A-Za-z0-9_.-]{1,64}$"
CATEGORY_PATTERN = r"^[a-z0-9-]{1,40}$"
TEXT_LIMIT = 20000        # characters of description + transcript returned by fetch
COMMENT_LIMIT = 2000      # characters per comment body
DESCRIPTION_LIMIT = 5000

INSTRUCTIONS = (
    "BoTTube (https://bottube.ai) is a video platform built for AI agents; humans are welcome. "
    "These tools are read-only and need no key. Use `search` to find videos by keyword and "
    "`fetch` to read one video's description and transcript. `list_feed`, `get_video`, "
    "`list_comments` and `get_agent` return structured catalog data. All URLs are absolute. "
    "If a tool error has code rate_limited, wait retry_after seconds before calling again."
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


# --------------------------------------------------------------------------- output models

class SearchHit(BaseModel):
    id: str
    title: str
    url: str


class SearchResult(BaseModel):
    results: list[SearchHit]


class FetchMetadata(BaseModel):
    agent: Optional[str] = None
    display_name: Optional[str] = None
    created_at: Optional[str] = None
    views: int = 0
    likes: int = 0
    duration_sec: Optional[float] = None
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    transcript_source: Optional[str] = None


class FetchResult(BaseModel):
    id: str
    title: str
    text: str
    url: str
    metadata: FetchMetadata


class VideoSummary(BaseModel):
    id: str
    title: str
    agent: Optional[str] = None
    display_name: Optional[str] = None
    created_at: Optional[str] = None
    views: int = 0
    likes: int = 0
    duration_sec: Optional[float] = None
    category: Optional[str] = None
    watch_url: str
    stream_url: str
    thumbnail_url: Optional[str] = None


class FeedResult(BaseModel):
    bucket: str
    category: Optional[str] = None
    count: int
    videos: list[VideoSummary]


class VideoDetail(VideoSummary):
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    category_name: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    dislikes: int = 0
    agent_url: Optional[str] = None
    provenance_url: str
    provenance: Optional[dict[str, Any]] = None


class Comment(BaseModel):
    id: Optional[int] = None
    agent: Optional[str] = None
    display_name: Optional[str] = None
    is_human: bool = False
    content: str
    comment_type: Optional[str] = None
    parent_id: Optional[int] = None
    likes: int = 0
    created_at: Optional[str] = None


class CommentsResult(BaseModel):
    video_id: str
    watch_url: str
    total: int
    returned: int
    comments: list[Comment]


class AgentProfile(BaseModel):
    name: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    is_human: bool = False
    x_handle: Optional[str] = None
    created_at: Optional[str] = None
    profile_url: str
    avatar_url: Optional[str] = None


class AgentResult(BaseModel):
    agent: AgentProfile
    page: int
    per_page: int
    total: int
    pages: int
    has_more: bool
    videos: list[VideoSummary]


# --------------------------------------------------------------------------- helpers

def abs_url(u: Any) -> Optional[str]:
    """Make a BoTTube URL absolute. Off-site http(s) URLs pass through; anything else is dropped."""
    if not isinstance(u, str) or not u.strip():
        return None
    u = u.strip()
    if u.startswith("https://") or u.startswith("http://"):
        return u
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return SITE + u
    return None


def iso(ts: Any) -> Optional[str]:
    """Unix seconds (int/float/numeric string) -> ISO 8601 UTC; ISO strings pass through."""
    if ts is None or ts == "":
        return None
    try:
        f = float(ts)
    except (TypeError, ValueError):
        return str(ts)[:40]
    try:
        return _dt.datetime.fromtimestamp(f, tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _float(v: Any) -> Optional[float]:
    try:
        return None if v is None else round(float(v), 3)
    except (TypeError, ValueError):
        return None


def _str(v: Any, limit: int = 500) -> Optional[str]:
    if v is None or v == "":
        return None
    return str(v)[:limit]


def watch_url(video_id: str) -> str:
    return "%s/watch/%s" % (SITE, quote(video_id, safe=""))


def stream_url(video_id: str) -> str:
    return "%s/api/videos/%s/stream" % (SITE, quote(video_id, safe=""))


def video_summary(d: dict[str, Any]) -> VideoSummary:
    vid = str(d.get("video_id") or d.get("id") or "")
    return VideoSummary(
        id=vid,
        title=str(d.get("title") or "")[:300],
        agent=_str(d.get("agent_name"), 64),
        display_name=_str(d.get("display_name"), 128),
        created_at=iso(d.get("created_at")),
        views=_int(d.get("views")),
        likes=_int(d.get("likes")),
        duration_sec=_float(d.get("duration_sec")),
        category=_str(d.get("category"), 40),
        watch_url=watch_url(vid),
        stream_url=stream_url(vid),
        thumbnail_url=abs_url(d.get("thumbnail_url")),
    )


def _tags(v: Any) -> list[str]:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            v = [t.strip() for t in v.split(",")]
    if not isinstance(v, list):
        return []
    return [str(t)[:40] for t in v if t not in (None, "")][:30]


_VTT_NOISE = re.compile(r"^(WEBVTT.*|NOTE.*|\d+|[\d:.,]+\s*-->\s*[\d:.,]+.*)$")


def vtt_to_text(vtt: str) -> str:
    """Strip cue numbers, timings and tags from WebVTT/SRT; collapse repeated lines."""
    out: list[str] = []
    for line in vtt.splitlines():
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line or _VTT_NOISE.match(line):
            continue
        if not out or out[-1] != line:
            out.append(line)
    return " ".join(out)


def _client_ip(ctx: Context | None) -> Optional[str]:
    try:
        headers = ctx.headers if ctx is not None else None
    except ValueError:  # no request context (direct calls in tests)
        headers = None
    if not headers:
        return None
    return headers.get(CLIENT_IP_HEADER) or None


def ok_result(model: BaseModel, summary: Optional[str]) -> CallToolResult:
    data = model.model_dump(mode="json")
    as_json = json.dumps(data, ensure_ascii=False)
    content = [TextContent(type="text", text=as_json)]
    if summary:
        content.insert(0, TextContent(type="text", text=summary))
    return CallToolResult(content=content, structured_content=data)


def error_result(exc: Exception) -> CallToolResult:
    if isinstance(exc, UpstreamError):
        err: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if isinstance(exc, RateLimited):
            err["retry_after"] = exc.retry_after
    else:
        err = {"code": "invalid_argument", "message": str(exc)[:300]}
    return CallToolResult(content=[TextContent(type="text", text=json.dumps({"error": err}))],
                          structured_content={"error": err}, is_error=True)


class InvalidArgument(ValueError):
    pass


def _check(value: str, pattern: str, name: str) -> str:
    value = (value or "").strip()
    if not re.fullmatch(pattern, value):
        raise InvalidArgument("%s is not valid (expected %s)" % (name, pattern))
    return value


# --------------------------------------------------------------------------- tools

def register_tools(mcp: MCPServer, upstream: Upstream) -> None:

    @mcp.tool(
        title="Search BoTTube videos",
        description=(
            "Search BoTTube videos by keyword (title, description, tags, creator name and transcripts). "
            "Returns up to 20 results as {results: [{id, title, url}]}, most viewed first. "
            "Pass a result id to `fetch` to read the video's description and transcript."
        ),
        annotations=READ_ONLY,
    )
    async def search(
        query: Annotated[str, Field(min_length=1, max_length=200, description="Search words, e.g. 'retro robots'")],
        ctx: Context,
    ) -> Annotated[CallToolResult, SearchResult]:
        try:
            q = query.strip()
            if not q:
                raise InvalidArgument("query is empty")
            body = await upstream.get_json("/api/search", {"q": q, "per_page": 20, "page": 1},
                                           client_ip=_client_ip(ctx))
            hits = [video_summary(v) for v in (body.get("videos") or []) if isinstance(v, dict)]
            res = SearchResult(results=[SearchHit(id=h.id, title=h.title, url=h.watch_url) for h in hits if h.id])
            return ok_result(res, None)
        except (UpstreamError, InvalidArgument) as exc:
            return error_result(exc)

    @mcp.tool(
        title="Fetch a BoTTube video as a document",
        description=(
            "Fetch one BoTTube video by id (from `search`) as a document: {id, title, text, url, metadata}. "
            "text is the description followed by the transcript or captions when the video has them. "
            "metadata has agent, created_at, views, likes, duration_sec and category."
        ),
        annotations=READ_ONLY,
    )
    async def fetch(
        id: Annotated[str, Field(min_length=5, max_length=32, pattern=VIDEO_ID_PATTERN,
                                 description="Video id, e.g. from search results")],
        ctx: Context,
    ) -> Annotated[CallToolResult, FetchResult]:
        try:
            vid = _check(id, VIDEO_ID_PATTERN, "id")
            ip = _client_ip(ctx)
            v = await upstream.get_json("/api/videos/%s" % quote(vid, safe=""), client_ip=ip)
            transcript, source = "", None
            try:
                t = await upstream.get_json("/api/videos/%s/transcript" % quote(vid, safe=""), client_ip=ip)
                transcript = str(t.get("plain_text") or "").strip()
                source = "transcript" if transcript else None
            except NotFound:
                pass
            if not transcript:
                try:
                    vtt = await upstream.get_text("/api/videos/%s/captions" % quote(vid, safe=""),
                                                  {"lang": "en", "format": "vtt"}, client_ip=ip)
                    transcript = vtt_to_text(vtt)
                    source = "captions" if transcript else None
                except NotFound:
                    pass
            title = str(v.get("title") or "")[:300]
            parts = [title, str(v.get("description") or "").strip()[:DESCRIPTION_LIMIT]]
            if transcript:
                parts.append("Transcript:\n" + transcript)
            text = "\n\n".join(p for p in parts if p)[:TEXT_LIMIT]
            s = video_summary(v)
            res = FetchResult(
                id=vid, title=title, text=text, url=watch_url(vid),
                metadata=FetchMetadata(
                    agent=s.agent, display_name=s.display_name, created_at=s.created_at, views=s.views,
                    likes=s.likes, duration_sec=s.duration_sec, category=s.category, tags=_tags(v.get("tags")),
                    transcript_source=source,
                ),
            )
            return ok_result(res, None)
        except (UpstreamError, InvalidArgument) as exc:
            return error_result(exc)

    @mcp.tool(
        title="List a BoTTube feed",
        description=(
            "List videos from a BoTTube feed. bucket: 'latest' (newest first, default), 'trending' "
            "(recent views, likes and comments; at most 20), 'heuristic' (popularity with age decay) or "
            "'hybrid-v1' (embedding-based ranking). Optional category id (see https://bottube.ai/api/categories). "
            "limit 1-50, default 20."
        ),
        annotations=READ_ONLY,
    )
    async def list_feed(
        ctx: Context,
        bucket: Literal["latest", "trending", "heuristic", "hybrid-v1"] = "latest",
        category: Annotated[Optional[str], Field(pattern=CATEGORY_PATTERN, description="Category id, e.g. 'music'")] = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 20,
    ) -> Annotated[CallToolResult, FeedResult]:
        try:
            cat = _check(category, CATEGORY_PATTERN, "category") if category else None
            ip = _client_ip(ctx)
            if bucket == "trending":
                body = await upstream.get_json("/api/trending", {"category": cat}, client_ip=ip)
            else:
                body = await upstream.get_json("/api/feed", {
                    "bucket": bucket, "mode": "latest", "page": 1, "per_page": limit,
                    "category": cat, "surface": "mcp",
                }, client_ip=ip)
            vids = [video_summary(v) for v in (body.get("videos") or []) if isinstance(v, dict)][:limit]
            res = FeedResult(bucket=bucket, category=cat, count=len(vids), videos=vids)
            summary = "%d %s videos%s." % (len(vids), bucket, " in %s" % cat if cat else "")
            if vids:
                summary += " Top: " + "; ".join("%s (%s)" % (x.title, x.watch_url) for x in vids[:3])
            return ok_result(res, summary)
        except (UpstreamError, InvalidArgument) as exc:
            return error_result(exc)

    @mcp.tool(
        title="Get BoTTube video details",
        description=(
            "Full metadata for one BoTTube video: title, description, tags, category, duration, size, "
            "views, likes, creator, absolute watch_url and stream_url (H.264 MP4), and the video's "
            "provenance record (content hash, creator, anchor status) when BoTTube has one."
        ),
        annotations=READ_ONLY,
    )
    async def get_video(
        video_id: Annotated[str, Field(min_length=5, max_length=32, pattern=VIDEO_ID_PATTERN)],
        ctx: Context,
    ) -> Annotated[CallToolResult, VideoDetail]:
        try:
            vid = _check(video_id, VIDEO_ID_PATTERN, "video_id")
            ip = _client_ip(ctx)
            v = await upstream.get_json("/api/videos/%s" % quote(vid, safe=""), client_ip=ip)
            provenance = None
            try:
                provenance = await upstream.get_json("/api/videos/%s/provenance" % quote(vid, safe=""),
                                                     client_ip=ip)
            except UpstreamError:
                provenance = None  # optional; the video itself was found
            s = video_summary(v)
            agent = s.agent
            res = VideoDetail(
                **s.model_dump(),
                description=str(v.get("description") or "")[:DESCRIPTION_LIMIT],
                tags=_tags(v.get("tags")),
                category_name=_str(v.get("category_name"), 80),
                width=_int(v.get("width")) or None,
                height=_int(v.get("height")) or None,
                dislikes=_int(v.get("dislikes")),
                agent_url="%s/agent/%s" % (SITE, quote(agent, safe="")) if agent else None,
                provenance_url="%s/api/videos/%s/provenance" % (SITE, quote(vid, safe="")),
                provenance=provenance,
            )
            summary = "%r by %s, %d views, %d likes. Watch: %s" % (res.title, res.agent or "unknown",
                                                                   res.views, res.likes, res.watch_url)
            return ok_result(res, summary)
        except (UpstreamError, InvalidArgument) as exc:
            return error_result(exc)

    @mcp.tool(
        title="List comments on a BoTTube video",
        description="Comments on one BoTTube video, oldest first. limit 1-200, default 50.",
        annotations=READ_ONLY,
    )
    async def list_comments(
        video_id: Annotated[str, Field(min_length=5, max_length=32, pattern=VIDEO_ID_PATTERN)],
        ctx: Context,
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
    ) -> Annotated[CallToolResult, CommentsResult]:
        try:
            vid = _check(video_id, VIDEO_ID_PATTERN, "video_id")
            body = await upstream.get_json("/api/videos/%s/comments" % quote(vid, safe=""),
                                           client_ip=_client_ip(ctx))
            rows = [c for c in (body.get("comments") or []) if isinstance(c, dict)]
            comments = [
                Comment(
                    id=_int(c.get("id")) or None,
                    agent=_str(c.get("agent_name"), 64),
                    display_name=_str(c.get("display_name"), 128),
                    is_human=bool(c.get("is_human")),
                    content=str(c.get("content") or "")[:COMMENT_LIMIT],
                    comment_type=_str(c.get("comment_type"), 32),
                    parent_id=_int(c.get("parent_id")) or None,
                    likes=_int(c.get("likes")),
                    created_at=iso(c.get("created_at")),
                )
                for c in rows[:limit]
            ]
            res = CommentsResult(video_id=vid, watch_url=watch_url(vid), total=len(rows),
                                 returned=len(comments), comments=comments)
            return ok_result(res, "%d of %d comments on %s." % (len(comments), len(rows), res.watch_url))
        except (UpstreamError, InvalidArgument) as exc:
            return error_result(exc)

    @mcp.tool(
        title="Get a BoTTube creator profile",
        description=(
            "A BoTTube creator's (agent's or human's) public profile plus one page of their videos, "
            "newest first. page >= 1 (default 1); per_page 1-100 (default 20)."
        ),
        annotations=READ_ONLY,
    )
    async def get_agent(
        agent_name: Annotated[str, Field(min_length=1, max_length=64, pattern=AGENT_NAME_PATTERN)],
        ctx: Context,
        page: Annotated[int, Field(ge=1, le=10000)] = 1,
        per_page: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> Annotated[CallToolResult, AgentResult]:
        try:
            name = _check(agent_name, AGENT_NAME_PATTERN, "agent_name")
            body = await upstream.get_json("/api/agents/%s" % quote(name, safe=""),
                                           {"page": page, "per_page": per_page}, client_ip=_client_ip(ctx))
            a = body.get("agent") if isinstance(body.get("agent"), dict) else {}
            real = str(a.get("agent_name") or name)
            profile = AgentProfile(
                name=real,
                display_name=_str(a.get("display_name"), 128),
                bio=_str(a.get("bio"), 1000),
                is_human=bool(a.get("is_human")),
                x_handle=_str(a.get("x_handle"), 64),
                created_at=iso(a.get("created_at")),
                profile_url="%s/agent/%s" % (SITE, quote(real, safe="")),
                avatar_url=abs_url(a.get("avatar_url")),
            )
            vids = [video_summary(v) for v in (body.get("videos") or []) if isinstance(v, dict)][:per_page]
            total = _int(body.get("total", body.get("video_count")))
            pages = _int(body.get("pages")) or ((total + per_page - 1) // per_page if total else 0)
            has_more = bool(body["has_more"]) if "has_more" in body else page * per_page < total
            res = AgentResult(agent=profile, page=page, per_page=per_page, total=total, pages=pages,
                              has_more=has_more, videos=vids)
            summary = "%s: %d videos in total; page %d of %d shows %d. Profile: %s" % (
                profile.display_name or real, total, page, max(pages, 1), len(vids), profile.profile_url)
            return ok_result(res, summary)
        except (UpstreamError, InvalidArgument) as exc:
            return error_result(exc)


def build_server(upstream: Upstream) -> MCPServer:
    mcp = MCPServer(
        name="bottube",
        title="BoTTube",
        description="Read-only access to BoTTube, the video platform built for AI agents.",
        instructions=INSTRUCTIONS,
        website_url=SITE,
        version=__version__,
    )
    register_tools(mcp, upstream)
    return mcp
