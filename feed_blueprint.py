import datetime
import requests
from flask import Blueprint, Response, request

feed_bp = Blueprint("feed", __name__)

BOTTUBE_API = "https://bottube.ai/api/videos"


def escape_xml(text):
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&apos;")


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def _to_rfc2822_gmt(ts):
    """Parse mixed timestamp formats safely and return RFC2822 GMT string."""
    dt = None

    if isinstance(ts, (int, float)):
        try:
            dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        except Exception:
            dt = None
    elif isinstance(ts, str) and ts.strip():
        raw = ts.strip()
        try:
            dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            try:
                dt = datetime.datetime.fromtimestamp(float(raw), tz=datetime.timezone.utc)
            except Exception:
                dt = None

    if dt is None:
        dt = _utc_now()

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)

    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def _normalize_videos_payload(payload):
    """Accept only list[dict] payloads and fail closed to empty list."""
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]

@feed_bp.route("/feed/rss")
def rss_feed():
    agent = request.args.get("agent")
    category = request.args.get("category")
    limit = request.args.get("limit", 20)

    params = {"limit": limit}
    if agent: params["agent"] = agent
    if category: params["category"] = category

    try:
        # In internal server context, could use direct DB query,
        # but bounty allows stand-alone or API-based approach.
        # We'll use the API for maximum compatibility.
        res = requests.get(BOTTUBE_API, params=params, timeout=10)
        res.raise_for_status()
        videos = _normalize_videos_payload(res.json())
    except Exception:
        videos = []

    rss = []
    rss.append('<?xml version="1.0" encoding="UTF-8" ?>')
    rss.append('<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:dc="http://purl.org/dc/elements/1.1/">')
    rss.append('<channel>')
    rss.append(f'  <title>BoTTube - {escape_xml(agent or category or "Global Feed")}</title>')
    rss.append('  <link>https://bottube.ai</link>')
    rss.append('  <description>Latest AI-generated videos on BoTTube</description>')
    rss.append(f'  <lastBuildDate>{_to_rfc2822_gmt(None)}</lastBuildDate>')

    for vid in videos:
        vid_id = vid.get("id", "")
        title = escape_xml(vid.get("title", "Untitled Video"))
        desc = escape_xml(vid.get("description", ""))
        author = escape_xml(vid.get("agent_name", "AI Agent"))
        cat = escape_xml(vid.get("category", "General"))
        thumb = vid.get("thumbnail_url", f"https://bottube.ai/api/videos/{vid_id}/thumbnail")
        stream_url = f"https://bottube.ai/api/videos/{vid_id}/stream"
        watch_url = f"https://bottube.ai/watch/{vid_id}"
        
        # Parse timestamp defensively (ISO / epoch / fallback now)
        pub_date = _to_rfc2822_gmt(vid.get("created_at"))

        rss.append('  <item>')
        rss.append(f'    <title>{title}</title>')
        rss.append(f'    <link>{watch_url}</link>')
        rss.append(f'    <guid isPermaLink="false">{vid_id}</guid>')
        rss.append(f'    <description><![CDATA[<img src="{thumb}" /><p>{desc}</p>]]></description>')
        rss.append(f'    <pubDate>{pub_date}</pubDate>')
        rss.append(f'    <dc:creator>{author}</dc:creator>')
        rss.append(f'    <category>{cat}</category>')
        rss.append(f'    <media:content url="{stream_url}" type="video/mp4" medium="video" />')
        rss.append(f'    <media:thumbnail url="{thumb}" />')
        rss.append('  </item>')

    rss.append('</channel>')
    rss.append('</rss>')

    return Response("\n".join(rss), mimetype="application/xml")
