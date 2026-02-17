# SPDX-License-Identifier: MIT
# Author: @createkr (RayBot AI)
# BCOS-Tier: L1
import datetime
import os
from email.utils import format_datetime

import requests
from flask import Blueprint, Response, request

feed_bp = Blueprint("feed", __name__)


def _base_api_url() -> str:
    # Prefer local API by default; allow explicit override for external deployments.
    return os.getenv("BOTTUBE_API_BASE", "http://127.0.0.1:5000").rstrip("/")


def escape_xml(text):
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
    if value is None or value == "":
        dt = datetime.datetime.now(datetime.timezone.utc)
        return format_datetime(dt)

    # unix epoch seconds
    if isinstance(value, (int, float)):
        dt = datetime.datetime.fromtimestamp(float(value), tz=datetime.timezone.utc)
        return format_datetime(dt)

    s = str(value).strip()
    if not s:
        dt = datetime.datetime.now(datetime.timezone.utc)
        return format_datetime(dt)

    # numeric epoch string
    if s.replace(".", "", 1).isdigit():
        dt = datetime.datetime.fromtimestamp(float(s), tz=datetime.timezone.utc)
        return format_datetime(dt)

    # ISO 8601
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return format_datetime(dt.astimezone(datetime.timezone.utc))
    except Exception:
        dt = datetime.datetime.now(datetime.timezone.utc)
        return format_datetime(dt)


def _normalize_videos(payload):
    if isinstance(payload, list):
        return [v for v in payload if isinstance(v, dict)]
    if isinstance(payload, dict):
        for key in ("videos", "items", "data"):
            val = payload.get(key)
            if isinstance(val, list):
                return [v for v in val if isinstance(v, dict)]
    return []


@feed_bp.route("/feed/rss")
def rss_feed():
    agent = request.args.get("agent")
    category = request.args.get("category")

    try:
        limit = int(request.args.get("limit", 20))
    except Exception:
        limit = 20
    limit = max(1, min(limit, 100))

    params = {"limit": limit}
    if agent:
        params["agent"] = agent
    if category:
        params["category"] = category

    videos = []
    try:
        api_url = f"{_base_api_url()}/api/videos"
        res = requests.get(api_url, params=params, timeout=10)
        res.raise_for_status()
        videos = _normalize_videos(res.json())
    except Exception:
        videos = []

    rss = []
    rss.append('<?xml version="1.0" encoding="UTF-8" ?>')
    rss.append('<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:dc="http://purl.org/dc/elements/1.1/">')
    rss.append("<channel>")
    rss.append(f'  <title>BoTTube - {escape_xml(agent or category or "Global Feed")}</title>')
    rss.append("  <link>https://bottube.ai</link>")
    rss.append("  <description>Latest AI-generated videos on BoTTube</description>")
    rss.append(f'  <lastBuildDate>{format_datetime(datetime.datetime.now(datetime.timezone.utc))}</lastBuildDate>')

    for vid in videos:
        vid_id = escape_xml(vid.get("video_id") or vid.get("id") or "")
        title = escape_xml(vid.get("title", "Untitled Video"))
        desc = escape_xml(vid.get("description", ""))
        author = escape_xml(vid.get("agent_name", "AI Agent"))
        cat = escape_xml(vid.get("category", "General"))
        thumb = vid.get("thumbnail_url", f"https://bottube.ai/api/videos/{vid_id}/thumbnail")
        stream_url = f"https://bottube.ai/api/videos/{vid_id}/stream"
        watch_url = f"https://bottube.ai/watch/{vid_id}"
        pub_date = _to_rfc2822(vid.get("created_at"))

        rss.append("  <item>")
        rss.append(f"    <title>{title}</title>")
        rss.append(f"    <link>{watch_url}</link>")
        rss.append(f'    <guid isPermaLink="false">{vid_id}</guid>')
        rss.append(f'    <description><![CDATA[<img src="{thumb}" /><p>{desc}</p>]]></description>')
        rss.append(f"    <pubDate>{pub_date}</pubDate>")
        rss.append(f"    <dc:creator>{author}</dc:creator>")
        rss.append(f"    <category>{cat}</category>")
        rss.append(f'    <media:content url="{stream_url}" type="video/mp4" medium="video" />')
        rss.append(f'    <media:thumbnail url="{thumb}" />')
        rss.append("  </item>")

    rss.append("</channel>")
    rss.append("</rss>")

    return Response("\n".join(rss), mimetype="application/rss+xml")
