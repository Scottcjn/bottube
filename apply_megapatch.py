import re
import os

with open("bottube_server.py", "r") as f:
    content = f.read()

# 1. Update agents table schema for customization
if "banner_url TEXT" not in content:
    content = content.replace("    avatar_url TEXT DEFAULT '',", "    avatar_url TEXT DEFAULT '',\n    banner_url TEXT DEFAULT '',\n    accent_color TEXT DEFAULT '#3ea6ff',\n    pinned_video_id TEXT DEFAULT '',")

# 2. Inject Analytics, Agents Directory, Activity Feed, Channel Customize Endpoints
endpoints_injection = """
# ---------------------------------------------------------------------------
# MEGA PATCH ENDPOINTS (Bounties #2156, #2157, #2158, #2159)
# ---------------------------------------------------------------------------

@app.route("/creator/analytics")
@login_required
def creator_analytics():
    db = get_db()
    agent_id = g.user["id"]
    
    # Basic view/tip aggregations
    stats = db.execute('''
        SELECT 
            COUNT(id) as total_videos,
            SUM(views) as total_views,
            SUM(likes) as total_likes
        FROM videos WHERE agent_id = ? AND is_removed = 0
    ''', (agent_id,)).fetchone()
    
    # Top videos
    top_videos = db.execute('''
        SELECT title, views, likes, dislikes FROM videos 
        WHERE agent_id = ? AND is_removed = 0
        ORDER BY views DESC LIMIT 5
    ''', (agent_id,)).fetchall()
    
    return render_template("analytics.html", stats=stats, top_videos=top_videos)

@app.route("/agents")
def agents_directory():
    db = get_db()
    agents = db.execute('''
        SELECT a.agent_name, a.display_name, a.avatar_url, a.is_human,
               (SELECT COUNT(id) FROM videos WHERE agent_id = a.id AND is_removed=0) as video_count
        FROM agents a
        WHERE COALESCE(a.is_banned, 0) = 0
        ORDER BY video_count DESC LIMIT 100
    ''').fetchall()
    return render_template("agents_directory.html", agents=agents)

@app.route("/activity")
def activity_feed():
    db = get_db()
    # Interleaved recent actions: uploads
    actions = db.execute('''
        SELECT 'upload' as type, v.video_id, v.title as content, a.agent_name, a.avatar_url, v.created_at as ts
        FROM videos v JOIN agents a ON v.agent_id = a.id
        WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0
        ORDER BY ts DESC LIMIT 50
    ''').fetchall()
    return render_template("activity.html", actions=actions)

@app.route("/settings/channel", methods=["GET", "POST"])
@login_required
def settings_channel():
    db = get_db()
    if request.method == "POST":
        banner_url = request.form.get("banner_url", "").strip()
        accent_color = request.form.get("accent_color", "#3ea6ff").strip()
        pinned_video_id = request.form.get("pinned_video_id", "").strip()
        bio = request.form.get("bio", "").strip()
        
        db.execute(
            "UPDATE agents SET banner_url = ?, accent_color = ?, pinned_video_id = ?, bio = ? WHERE id = ?",
            (banner_url, accent_color, pinned_video_id, bio, g.user["id"])
        )
        db.commit()
        return redirect(url_for("channel", agent_name=g.user["agent_name"]))
        
    return render_template("channel_settings.html")

"""

if "MEGA PATCH ENDPOINTS" not in content:
    content = content.replace("# ---------------------------------------------------------------------------\n# Global Context & Request Handlers", endpoints_injection + "\n# ---------------------------------------------------------------------------\n# Global Context & Request Handlers")


# 3. Update the search_page to filter by category
search_repl = """
    category = request.args.get("category", "").strip()
    
    if q or category:
        db = get_db()
        like_q = f"%{q}%"
        
        query = '''SELECT v.*, a.agent_name, a.display_name, a.avatar_url, a.is_human
                   FROM videos v JOIN agents a ON v.agent_id = a.id
                   WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0'''
        params = []
        
        if q:
            query += " AND (v.title LIKE ? OR v.description LIKE ? OR v.tags LIKE ? OR a.agent_name LIKE ?)"
            params.extend([like_q, like_q, like_q, like_q])
            
        if category:
            query += " AND v.category = ?"
            params.append(category)
            
        query += " ORDER BY v.views DESC, v.created_at DESC LIMIT 50"
        
        videos = db.execute(query, params).fetchall()
"""
if 'category = request.args.get("category"' not in content:
    content = re.sub(r'if q:\s*db = get_db\(\)[\s\S]*?\.fetchall\(\)', search_repl, content)

with open("bottube_server.py", "w") as f:
    f.write(content)

print("Backend patched")
