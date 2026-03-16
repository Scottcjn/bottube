import re

with open("bottube_server.py", "r") as f:
    content = f.read()

# Add endpoints for collaboration features
collab_endpoints = """
# ---------------------------------------------------------------------------
# Collaboration & Playlists (Bounty #2161)
# ---------------------------------------------------------------------------

@app.route("/api/playlists", methods=["POST"])
@require_auth_or_login
def create_playlist():
    \"\"\"Create a shared playlist.\"\"\"
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name", "").strip()[:100]
    description = data.get("description", "").strip()[:500]
    is_public = int(bool(data.get("is_public", True)))
    
    if not name:
        return jsonify({"error": "Playlist name required"}), 400
        
    agent_id = g.agent["id"] if g.agent else g.user["id"]
    playlist_id = secrets.token_hex(8)
    
    db = get_db()
    try:
        db.execute(
            "INSERT INTO playlists (playlist_id, agent_id, name, description, is_public, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (playlist_id, agent_id, name, description, is_public, time.time(), time.time())
        )
        db.execute(
            "INSERT INTO playlist_members (playlist_id, agent_id, role, added_at) VALUES (?, ?, 'owner', ?)",
            (playlist_id, agent_id, time.time())
        )
        db.commit()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
    return jsonify({"status": "success", "playlist_id": playlist_id}), 201

@app.route("/api/playlists/<playlist_id>/members", methods=["POST"])
@require_auth_or_login
def add_playlist_member(playlist_id):
    \"\"\"Add a collaborator to a playlist.\"\"\"
    db = get_db()
    agent_id = g.agent["id"] if g.agent else g.user["id"]
    
    # Verify owner
    owner = db.execute("SELECT id FROM playlist_members WHERE playlist_id = ? AND agent_id = ? AND role = 'owner'", (playlist_id, agent_id)).fetchone()
    if not owner:
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.get_json(force=True, silent=True) or {}
    member_name = data.get("agent_name", "").strip()
    
    target_agent = db.execute("SELECT id FROM agents WHERE agent_name = ?", (member_name,)).fetchone()
    if not target_agent:
        return jsonify({"error": "Agent not found"}), 404
        
    try:
        db.execute(
            "INSERT INTO playlist_members (playlist_id, agent_id, role, added_at) VALUES (?, ?, 'editor', ?)",
            (playlist_id, target_agent["id"], time.time())
        )
        db.commit()
    except Exception:
        return jsonify({"error": "Agent is already a member"}), 400
        
    return jsonify({"status": "success"}), 200

"""

# Insert before EOF or a specific known section
if "def create_playlist():" not in content:
    # Insert right before the error handlers or bottom
    content = content.replace("# ---------------------------------------------------------------------------\n# Global Context & Request Handlers", collab_endpoints + "\n# ---------------------------------------------------------------------------\n# Global Context & Request Handlers")

with open("bottube_server.py", "w") as f:
    f.write(content)

print("Applied playlist endpoints")

