
# RSS/Atom Feed Routes for BoTTube Bounty
# These routes provide RSS and Atom feeds for video content

@app.route("/feed/rss")
def feed_rss():
    """RSS 2.0 feed for all recent videos on BoTTube - bounty milestone 1"""
    # Reuse the global_rss logic but with /feed/rss endpoint
    limit = request.args.get("limit", 50, type=int)
    tag = request.args.get("tag", "")
    category = request.args.get("category", "")
    
    db = get_db()
    
    # Build query based on filters
    query = """SELECT v.video_id, v.title, v.description, v.created_at, v.duration_sec, v.thumbnail, v.tags, v.category,
                      a.agent_name, a.display_name
               FROM videos v JOIN agents a ON v.agent_id = a.id
               WHERE v.status = 'completed'"""
    params = []
    
    if tag:
        query += " AND v.tags LIKE ?"
        params.append(f"%{tag}%")
    if category:
        query += " AND v.category = ?"
        params.append(category)
    
    query += " ORDER BY v.created_at DESC LIMIT ?"
    params.append(limit)
    
    videos = db.execute(query, params).fetchall()

    base = request.url_root.rstrip("/").replace("http://", "https://")
    prefix = app.config.get("APPLICATION_ROOT", "").rstrip("/")

    items = []
    for v in videos:
        pub_date = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime(v["created_at"]))
        link = f"{base}{prefix}/watch/{v['video_id']}"
        author_display = _xml_escape(v["display_name"] or v["agent_name"])
        desc = v["description"] or v["title"]
        thumb_url = f"{base}{prefix}/thumbnails/{v['thumbnail']}" if v["thumbnail"] else ""
        
        thumb_tag = f'<media:thumbnail url="{thumb_url}"/>' if thumb_url else ""
        duration_tag = f'<itunes:duration>{v["duration_sec"]}</itunes:duration>' if v.get("duration_sec") else ""
        
        items.append(f"""    <item>
      <title><![CDATA[{_cdata_safe(v["title"])}]]></title>
      <link>{link}</link>
      <guid isPermaLink="true">{link}</guid>
      <pubDate>{pub_date}</pubDate>
      <description><![CDATA[{_cdata_safe(desc)}]]></description>
      <author>{author_display}</author>
      {thumb_tag}
      {duration_tag}
    </item>""")

    build_date = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
    
    title = "BoTTube - Latest Videos"
    if tag:
        title += f" (tag: {tag})"
    if category:
        title += f" (category: {category})"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{title}</title>
    <link>https://bottube.ai</link>
    <description>AI video platform where agents and humans create</description>
    <language>en-us</language>
    <lastBuildDate>{build_date}</lastBuildDate>
    <atom:link href="{base}{prefix}/feed/rss" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""

    resp = app.response_class(xml, mimetype="application/rss+xml")
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@app.route("/feed/atom")
def feed_atom():
    """Atom 1.0 feed for all recent videos on BoTTube - bounty milestone 1"""
    limit = request.args.get("limit", 50, type=int)
    tag = request.args.get("tag", "")
    category = request.args.get("category", "")
    
    db = get_db()
    
    query = """SELECT v.video_id, v.title, v.description, v.created_at, v.duration_sec, v.thumbnail, v.tags, v.category,
                      a.agent_name, a.display_name
               FROM videos v JOIN agents a ON v.agent_id = a.id
               WHERE v.status = 'completed'"""
    params = []
    
    if tag:
        query += " AND v.tags LIKE ?"
        params.append(f"%{tag}%")
    if category:
        query += " AND v.category = ?"
        params.append(category)
    
    query += " ORDER BY v.created_at DESC LIMIT ?"
    params.append(limit)
    
    videos = db.execute(query, params).fetchall()

    base = request.url_root.rstrip("/").replace("http://", "https://")
    prefix = app.config.get("APPLICATION_ROOT", "").rstrip("/")

    entries = []
    for v in videos:
        updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(v["created_at"]))
        link = f"{base}{prefix}/watch/{v['video_id']}"
        author_display = _xml_escape(v["display_name"] or v["agent_name"])
        
        entries.append(f"""    <entry>
      <title>{_cdata_safe(v["title"])}</title>
      <link href="{link}"/>
      <id>{link}</id>
      <updated>{updated}</updated>
      <summary>{_cdata_safe(v["description"] or v["title"])}</summary>
      <author>
        <name>{author_display}</name>
      </author>
    </entry>""")

    updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>BoTTube - Latest Videos</title>
  <link href="https://bottube.ai"/>
  <link href="{base}{prefix}/feed/atom" rel="self"/>
  <updated>{updated}</updated>
  <subtitle>AI video platform where agents and humans create</subtitle>
{chr(10).join(entries)}
</feed>"""

    resp = app.response_class(xml, mimetype="application/atom+xml")
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@app.route("/feed/rss/<agent_name>")
def feed_rss_agent(agent_name):
    """RSS 2.0 feed for a specific agent's videos - bounty milestone 2"""
    db = get_db()
    agent = db.execute("SELECT * FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
    if not agent:
        abort(404)

    limit = request.args.get("limit", 50, type=int)
    
    videos = db.execute(
        """SELECT video_id, title, description, created_at, duration_sec, thumbnail, tags
           FROM videos WHERE agent_id = ? AND status = 'completed' 
           ORDER BY created_at DESC LIMIT ?""",
        (agent["id"], limit),
    ).fetchall()

    base = request.url_root.rstrip("/").replace("http://", "https://")
    prefix = app.config.get("APPLICATION_ROOT", "").rstrip("/")

    items = []
    for v in videos:
        pub_date = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime(v["created_at"]))
        link = f"{base}{prefix}/watch/{v['video_id']}"
        display = _xml_escape(agent["display_name"] or agent["agent_name"])
        desc = v["description"] or v["title"]
        
        thumb_url = f"{base}{prefix}/thumbnails/{v['thumbnail']}" if v["thumbnail"] else ""
        thumb_tag = f'<media:thumbnail url="{thumb_url}"/>' if thumb_url else ""
        
        items.append(f"""    <item>
      <title><![CDATA[{_cdata_safe(v["title"])}]]></title>
      <link>{link}</link>
      <guid isPermaLink="true">{link}</guid>
      <pubDate>{pub_date}</pubDate>
      <description><![CDATA[{_cdata_safe(desc)}]]></description>
      <author>{display}</author>
      {thumb_tag}
    </item>""")

    channel_link = f"{base}{prefix}/agent/{agent_name}"
    build_date = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{display} - BoTTube</title>
    <link>{channel_link}</link>
    <description><![CDATA[Videos by {display} on BoTTube]]></description>
    <language>en-us</language>
    <lastBuildDate>{build_date}</lastBuildDate>
    <atom:link href="{base}{prefix}/feed/rss/{agent_name}" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""

    resp = app.response_class(xml, mimetype="application/rss+xml")
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp
