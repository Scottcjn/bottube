
# ---------------------------------------------------------------------------
# SEO & Crawler Support (Flask Blueprint)
# ---------------------------------------------------------------------------

import html
from flask import Blueprint, current_app
from datetime import datetime, timezone

seo_bp = Blueprint("seo", __name__)


@seo_bp.route("/robots.txt")
def robots_txt():
    """Serve robots.txt for search engine crawlers."""
    content = "User-agent: *\nAllow: /\nAllow: /watch/\nAllow: /agent/\nAllow: /agents\nAllow: /search\nAllow: /categories\nAllow: /category/\nDisallow: /api/\nDisallow: /login\nDisallow: /signup\nDisallow: /logout\n\nSitemap: https://bottube.ai/sitemap.xml\n"
    return current_app.response_class(content, mimetype="text/plain")


def _esc(text):
    """Escape text for XML content."""
    if not text:
        return ""
    return html.escape(str(text), quote=True)


def _iso_duration(seconds):
    """Convert seconds to ISO 8601 duration (PT#M#S)."""
    try:
        s = int(float(seconds or 0))
    except (ValueError, TypeError):
        return ""
    if s <= 0:
        return ""
    m, s = divmod(s, 60)
    return f"PT{m}M{s}S"


@seo_bp.route("/sitemap.xml")
def sitemap_xml():
    """Dynamic video sitemap with Google video extensions."""
    from bottube_server import get_db

    db = get_db()
    # Fetch full video data for video:video extensions
    videos = db.execute(
        "SELECT v.video_id, v.title, v.description, v.thumbnail, v.duration_sec, "
        "v.created_at, v.views, a.agent_name, a.display_name "
        "FROM videos v LEFT JOIN agents a ON v.agent_id = a.id "
        "ORDER BY v.created_at DESC LIMIT 5000"
    ).fetchall()
    agents = db.execute(
        "SELECT agent_name, created_at FROM agents ORDER BY created_at DESC"
    ).fetchall()

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">'
    )

    # Static pages
    lines.append("  <url><loc>https://bottube.ai/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>")
    lines.append("  <url><loc>https://bottube.ai/agents</loc><changefreq>daily</changefreq><priority>0.8</priority></url>")
    lines.append("  <url><loc>https://bottube.ai/search</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")
    lines.append("  <url><loc>https://bottube.ai/categories</loc><changefreq>weekly</changefreq><priority>0.7</priority></url>")
    lines.append("  <url><loc>https://bottube.ai/blog</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>")

    from bottube_server import BLOG_POSTS
    for post in BLOG_POSTS:
        lines.append(
            f'  <url><loc>https://bottube.ai/blog/{post["slug"]}</loc>'
            f'<lastmod>{post["date"]}</lastmod><changefreq>monthly</changefreq>'
            f'<priority>0.9</priority></url>'
        )

    from bottube_server import VIDEO_CATEGORIES
    for cat in VIDEO_CATEGORIES:
        lines.append(
            f'  <url><loc>https://bottube.ai/category/{cat["id"]}</loc>'
            f'<changefreq>daily</changefreq><priority>0.6</priority></url>'
        )

    # Video pages with full video:video extensions
    for v in videos:
        vid = v["video_id"]
        ts = datetime.fromtimestamp(float(v["created_at"]), tz=timezone.utc)
        iso_date = ts.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        short_date = ts.strftime("%Y-%m-%d")
        title = _esc(v["title"] or vid)
        desc = _esc((v["description"] or "")[:2048])
        if not desc:
            desc = _esc(f"Watch {v['title'] or 'this video'} on BoTTube")
        thumb = v["thumbnail"]
        thumb_url = f"https://bottube.ai/thumbnails/{thumb}" if thumb else "https://bottube.ai/static/og-banner.png"
        duration = _iso_duration(v["duration_sec"])
        uploader = _esc(v["display_name"] or v["agent_name"] or "BoTTube Creator")

        lines.append("  <url>")
        lines.append(f"    <loc>https://bottube.ai/watch/{vid}</loc>")
        lines.append(f"    <lastmod>{short_date}</lastmod>")
        lines.append("    <priority>0.7</priority>")
        lines.append("    <video:video>")
        lines.append(f"      <video:thumbnail_loc>{thumb_url}</video:thumbnail_loc>")
        lines.append(f"      <video:title>{title}</video:title>")
        lines.append(f"      <video:description>{desc}</video:description>")
        lines.append(f"      <video:content_loc>https://bottube.ai/api/videos/{vid}/stream</video:content_loc>")
        lines.append(f"      <video:player_loc>https://bottube.ai/embed/{vid}</video:player_loc>")
        if duration:
            lines.append(f"      <video:duration>{int(float(v['duration_sec'] or 0))}</video:duration>")
        lines.append(f"      <video:view_count>{int(v['views'] or 0)}</video:view_count>")
        lines.append(f"      <video:publication_date>{iso_date}</video:publication_date>")
        lines.append("      <video:family_friendly>yes</video:family_friendly>")
        lines.append(f"      <video:uploader info=\"https://bottube.ai/agent/{_esc(v['agent_name'] or '')}\">{uploader}</video:uploader>")
        lines.append("      <video:live>no</video:live>")
        lines.append("    </video:video>")
        lines.append("  </url>")

    # Agent profile pages
    for a in agents:
        lines.append(f'  <url><loc>https://bottube.ai/agent/{a["agent_name"]}</loc><priority>0.6</priority></url>')

    lines.append("</urlset>")
    return current_app.response_class("\n".join(lines), mimetype="application/xml")
