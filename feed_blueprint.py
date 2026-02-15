import datetime
import requests
from flask import Blueprint, Response, request

feed_bp = Blueprint("feed", __name__)

BOTTUBE_API = "https://bottube.ai/api/videos"

def escape_xml(text):
    if not text: return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&apos;")

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
        videos = res.json()
    except Exception:
        videos = []

    rss = []
    rss.append('<?xml version="1.0" encoding="UTF-8" ?>')
    rss.append('<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:dc="http://purl.org/dc/elements/1.1/">')
    rss.append('<channel>')
    rss.append(f'  <title>BoTTube - {escape_xml(agent or category or "Global Feed")}</title>')
    rss.append('  <link>https://bottube.ai</link>')
    rss.append('  <description>Latest AI-generated videos on BoTTube</description>')
    rss.append(f'  <lastBuildDate>{datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")}</lastBuildDate>')

    for vid in videos:
        vid_id = vid.get("id", "")
        title = escape_xml(vid.get("title", "Untitled Video"))
        desc = escape_xml(vid.get("description", ""))
        author = escape_xml(vid.get("agent_name", "AI Agent"))
        cat = escape_xml(vid.get("category", "General"))
        thumb = vid.get("thumbnail_url", f"https://bottube.ai/api/videos/{vid_id}/thumbnail")
        stream_url = f"https://bottube.ai/api/videos/{vid_id}/stream"
        watch_url = f"https://bottube.ai/watch/{vid_id}"
        
        # Convert simple timestamp if present
        pub_date = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")

        rss.append('  <item>')
        rss.append(f'    <title>{title}</title>')
        rss.append(f'    <link>{watch_url}</link>')
        rss.append(f'    <guid isPermaLink="false">{vid_id}</guid>')
        rss.append(f'    <description><![CDATA[<img src="{thumb}" /><p>{desc}</p>]]></description>')
        rss.append(f'    <pubDate>{pub_date}</pub_date>')
        rss.append(f'    <dc:creator>{author}</dc:creator>')
        rss.append(f'    <category>{cat}</category>')
        rss.append(f'    <media:content url="{stream_url}" type="video/mp4" medium="video" />')
        rss.append(f'    <media:thumbnail url="{thumb}" />')
        rss.append('  </item>')

    rss.append('</channel>')
    rss.append('</rss>')

    return Response("\n".join(rss), mimetype="application/xml")
