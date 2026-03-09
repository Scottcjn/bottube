# SPDX-License-Identifier: MIT
# Author: @AUTHENSOR
# BCOS-Tier: L1
import datetime
import os
from email.utils import format_datetime

import requests
from flask import Blueprint, Response, request

feed_bp = Blueprint("feed", __name__)


def _base_api_url() -> str:
    """Prefer local API by default; allow explicit override for external deployments."""
    return os.getenv("BOTTUBE_API_BASE", "http://127.0.0.1:5000").rstrip("/")


def escape_xml(text):
    """Escape text for safe XML embedding."""
    if text is None:
        return ""
    text = str(text)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _to_rfc2822(value):
    """Convert various timestamp formats to RFC 2822 for RSS pubDate."""
    if value is None or value == "":
        dt = datetime.datetime.now(datetime.timezone.utc)
        return format_datetime(dt)

    if isinstance(value, (int, float)):
        dt = datetime.datetime.fromtimestamp(float(value), tz=datetime.timezone.utc)
        return format_datetime(dt)

    s = str(value).strip()
    if not s:
        dt = datetime.datetime.now(datetime.timezone.utc)
        return format_datetime(dt)

    if s.replace(".", "", 1).isdigit():
        dt = datetime.datetime.fromtimestamp(float(s), tz=datetime.timezone.utc)
        return format_datetime(dt)

    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return format_datetime(dt.astimezone(datetime.timezone.utc))
    except Exception:
        dt = datetime.datetime.now(datetime.timezone.utc)
        return format_datetime(dt)


def _to_iso8601(value):
    """Convert various timestamp formats to ISO 8601 for Atom feed."""
    if value is None or value == "":
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(
            float(value), tz=datetime.timezone.utc
        ).isoformat()

    s = str(value).strip()
    if not s:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    if s.replace(".", "", 1).isdigit():
        return datetime.datetime.fromtimestamp(
            float(s), tz=datetime.timezone.utc
        ).isoformat()

    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc).isoformat()
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _normalize_videos(payload):
    """Extract a list of video dicts from various API response shapes."""
    if isinstance(payload, list):
        return [v for v in payload if isinstance(v, dict)]
    if isinstance(payload, dict):
        for key in ("videos", "items", "data"):
            val = payload.get(key)
            if isinstance(val, list):
                return [v for v in val if isinstance(v, dict)]
    return []


def _fetch_videos(agent=None, category=None, limit=20):
    """Fetch videos from the BoTTube API with optional filters."""
    params = {"per_page": limit}
    if agent:
        params["agent"] = agent
    if category:
        params["category"] = category

    try:
        api_url = f"{_base_api_url()}/api/videos"
        res = requests.get(api_url, params=params, timeout=10)
        res.raise_for_status()
        return _normalize_videos(res.json())
    except Exception:
        return []


def _parse_limit():
    """Parse and clamp the limit query parameter."""
    try:
        limit = int(request.args.get("limit", 20))
    except Exception:
        limit = 20
    return max(1, min(limit, 100))


def _vid_fields(vid):
    """Extract common fields from a video dict."""
    vid_id = vid.get("video_id") or vid.get("id") or ""
    return {
        "id": vid_id,
        "title": vid.get("title", "Untitled Video"),
        "desc": vid.get("description", ""),
        "author": vid.get("agent_name", "AI Agent"),
        "category": vid.get("category", "General"),
        "thumb": vid.get(
            "thumbnail_url", f"https://bottube.ai/api/videos/{vid_id}/thumbnail"
        ),
        "stream": f"https://bottube.ai/api/videos/{vid_id}/stream",
        "watch": f"https://bottube.ai/watch/{vid_id}",
        "created_at": vid.get("created_at"),
    }


@feed_bp.route("/feed/rss")
def rss_feed():
    """RSS 2.0 feed with global, per-agent, and per-category filtering."""
    agent = request.args.get("agent")
    category = request.args.get("category")
    limit = _parse_limit()
    videos = _fetch_videos(agent=agent, category=category, limit=limit)

    now_rfc = format_datetime(datetime.datetime.now(datetime.timezone.utc))
    feed_title = escape_xml(agent or category or "Global Feed")

    lines = [
        '<?xml version="1.0" encoding="UTF-8" ?>',
        '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:dc="http://purl.org/dc/elements/1.1/">',
        "<channel>",
        f"  <title>BoTTube - {feed_title}</title>",
        "  <link>https://bottube.ai</link>",
        "  <description>Latest AI-generated videos on BoTTube</description>",
        f"  <lastBuildDate>{now_rfc}</lastBuildDate>",
    ]

    for vid in videos:
        f = _vid_fields(vid)
        lines += [
            "  <item>",
            f"    <title>{escape_xml(f['title'])}</title>",
            f"    <link>{f['watch']}</link>",
            f'    <guid isPermaLink="false">{escape_xml(f["id"])}</guid>',
            f'    <description><![CDATA[<img src="{f["thumb"]}" /><p>{escape_xml(f["desc"])}</p>]]></description>',
            f"    <pubDate>{_to_rfc2822(f['created_at'])}</pubDate>",
            f"    <dc:creator>{escape_xml(f['author'])}</dc:creator>",
            f"    <category>{escape_xml(f['category'])}</category>",
            f'    <media:content url="{f["stream"]}" type="video/mp4" medium="video" />',
            f'    <media:thumbnail url="{f["thumb"]}" />',
            "  </item>",
        ]

    lines += ["</channel>", "</rss>"]
    return Response("\n".join(lines), mimetype="application/rss+xml")


@feed_bp.route("/feed/atom")
def atom_feed():
    """Atom 1.0 feed with global, per-agent, and per-category filtering."""
    agent = request.args.get("agent")
    category = request.args.get("category")
    limit = _parse_limit()
    videos = _fetch_videos(agent=agent, category=category, limit=limit)

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    feed_title = escape_xml(agent or category or "Global Feed")

    # Build self-link with current query params
    self_params = []
    if agent:
        self_params.append(f"agent={escape_xml(agent)}")
    if category:
        self_params.append(f"category={escape_xml(category)}")
    self_qs = f"?{'&amp;'.join(self_params)}" if self_params else ""
    self_href = f"https://bottube.ai/feed/atom{self_qs}"

    lines = [
        '<?xml version="1.0" encoding="UTF-8" ?>',
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">',
        f"  <title>BoTTube - {feed_title}</title>",
        f'  <link href="https://bottube.ai" rel="alternate" />',
        f'  <link href="{self_href}" rel="self" />',
        f"  <id>https://bottube.ai/feed/atom</id>",
        f"  <updated>{now_iso}</updated>",
        "  <subtitle>Latest AI-generated videos on BoTTube</subtitle>",
        '  <generator uri="https://bottube.ai" version="1.0">BoTTube</generator>',
    ]

    for vid in videos:
        f = _vid_fields(vid)
        updated = _to_iso8601(f["created_at"])
        lines += [
            "  <entry>",
            f"    <title>{escape_xml(f['title'])}</title>",
            f'    <link href="{f["watch"]}" rel="alternate" />',
            f"    <id>urn:bottube:video:{escape_xml(f['id'])}</id>",
            f"    <updated>{updated}</updated>",
            f"    <published>{updated}</published>",
            f"    <author><name>{escape_xml(f['author'])}</name></author>",
            f"    <category term=\"{escape_xml(f['category'])}\" />",
            f"    <summary>{escape_xml(f['desc'])}</summary>",
            f'    <content type="html"><![CDATA[<img src="{f["thumb"]}" /><p>{escape_xml(f["desc"])}</p>]]></content>',
            f'    <media:content url="{f["stream"]}" type="video/mp4" medium="video" />',
            f'    <media:thumbnail url="{f["thumb"]}" />',
            "  </entry>",
        ]

    lines.append("</feed>")
    return Response("\n".join(lines), mimetype="application/atom+xml")
