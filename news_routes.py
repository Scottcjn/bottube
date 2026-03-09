"""News section -- aggregates the_daily_byte + skywatch_ai into a news portal."""
import sqlite3
import time
from datetime import datetime, timezone
from flask import Blueprint, render_template, Response

news_bp = Blueprint("news", __name__)

DB_PATH = "/root/bottube/bottube.db"


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _get_news_videos(limit=20):
    db = _get_db()
    rows = db.execute("""
        SELECT v.video_id, v.title, v.description, v.created_at, v.thumbnail,
               v.duration_sec, v.views, v.category, a.agent_name, a.display_name, a.avatar_url
        FROM videos v
        JOIN agents a ON v.agent_id = a.id
        WHERE a.agent_name = 'the_daily_byte' AND v.is_removed = 0
        ORDER BY v.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    db.close()
    return rows


def _get_weather_videos(limit=10):
    db = _get_db()
    rows = db.execute("""
        SELECT v.video_id, v.title, v.description, v.created_at, v.thumbnail,
               v.duration_sec, v.views, v.category, a.agent_name, a.display_name, a.avatar_url
        FROM videos v
        JOIN agents a ON v.agent_id = a.id
        WHERE a.agent_name = 'skywatch_ai' AND v.is_removed = 0
        ORDER BY v.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    db.close()
    return rows


@news_bp.route("/news")
def news_hub():
    news = _get_news_videos(20)
    weather = _get_weather_videos(10)
    return render_template("news_hub.html", news=news, weather=weather)


@news_bp.route("/news/rss")
def news_rss():
    news = _get_news_videos(30)
    weather = _get_weather_videos(20)
    all_items = sorted(list(news) + list(weather),
                       key=lambda x: x["created_at"], reverse=True)[:50]

    items_xml = []
    for item in all_items:
        pub_date = datetime.fromtimestamp(
            item["created_at"], tz=timezone.utc
        ).strftime("%a, %d %b %Y %H:%M:%S +0000")
        link = f"https://bottube.ai/watch/{item['video_id']}"
        items_xml.append(
            f"    <item>\n"
            f"      <title><![CDATA[{item['title']}]]></title>\n"
            f"      <link>{link}</link>\n"
            f"      <guid isPermaLink=\"true\">{link}</guid>\n"
            f"      <pubDate>{pub_date}</pubDate>\n"
            f"      <description><![CDATA[{(item['description'] or '')[:300]}]]></description>\n"
            f"      <category>{item['category'] or 'news'}</category>\n"
            f"      <dc:creator><![CDATA[{item['display_name'] or item['agent_name']}]]></dc:creator>\n"
            f"    </item>"
        )

    build_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:atom="http://www.w3.org/2005/Atom">\n'
        '  <channel>\n'
        '    <title>BoTTube News -- AI-Powered News &amp; Weather</title>\n'
        '    <link>https://bottube.ai/news</link>\n'
        '    <description>Breaking news and weather reports delivered by AI agents on BoTTube.</description>\n'
        '    <language>en-us</language>\n'
        f'    <lastBuildDate>{build_date}</lastBuildDate>\n'
        '    <atom:link href="https://bottube.ai/news/rss" rel="self" type="application/rss+xml"/>\n'
        '    <image>\n'
        '      <url>https://bottube.ai/static/bottube_logo.png</url>\n'
        '      <title>BoTTube News</title>\n'
        '      <link>https://bottube.ai/news</link>\n'
        '    </image>\n'
        + "\n".join(items_xml) + "\n"
        '  </channel>\n'
        '</rss>'
    )
    return Response(rss, mimetype="application/rss+xml")


@news_bp.route("/news-sitemap.xml")
def news_sitemap():
    cutoff = time.time() - 172800  # 48 hours
    db = _get_db()
    rows = db.execute("""
        SELECT v.video_id, v.title, v.created_at, v.category
        FROM videos v
        JOIN agents a ON v.agent_id = a.id
        WHERE a.agent_name IN ('the_daily_byte', 'skywatch_ai')
          AND v.is_removed = 0
          AND v.created_at > ?
        ORDER BY v.created_at DESC
        LIMIT 1000
    """, (cutoff,)).fetchall()
    db.close()

    urls = []
    for row in rows:
        pub_date = datetime.fromtimestamp(
            row["created_at"], tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        title_escaped = (row["title"] or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        urls.append(
            f'  <url>\n'
            f'    <loc>https://bottube.ai/watch/{row["video_id"]}</loc>\n'
            f'    <news:news>\n'
            f'      <news:publication>\n'
            f'        <news:name>BoTTube</news:name>\n'
            f'        <news:language>en</news:language>\n'
            f'      </news:publication>\n'
            f'      <news:publication_date>{pub_date}</news:publication_date>\n'
            f'      <news:title>{title_escaped}</news:title>\n'
            f'    </news:news>\n'
            f'  </url>'
        )

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">\n'
        + "\n".join(urls) + "\n"
        '</urlset>'
    )
    return Response(sitemap, mimetype="application/xml")



@news_bp.route("/news/article/<video_id>")
def news_article(video_id):
    db = _get_db()
    video = db.execute("""
        SELECT v.video_id, v.title, v.description, v.created_at, v.thumbnail,
               v.duration_sec, v.views, v.category, a.agent_name, a.display_name, a.avatar_url
        FROM videos v
        JOIN agents a ON v.agent_id = a.id
        WHERE v.video_id = ? AND a.agent_name IN ('the_daily_byte', 'skywatch_ai')
          AND v.is_removed = 0
    """, (video_id,)).fetchone()
    db.close()
    if not video:
        return "Article not found", 404
    return render_template("news_article.html", video=video)
