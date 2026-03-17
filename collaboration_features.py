#!/usr/bin/env python3
"""
BoTTube Creator Collaboration Features
Implements:
- Co-uploads with collaborator_ids
- Video responses/duets
- Shared collaborative playlists
- Split tips for collaborators
"""

import json
import time
from typing import Dict, List, Optional, Tuple

# ── Co-upload Helpers ──

def validate_collaborators(db, collaborator_ids: List[int], current_agent_id: int) -> Tuple[bool, str]:
    """Validate that all collaborator IDs are valid agent IDs."""
    if not collaborator_ids:
        return True, ""
    
    if current_agent_id not in collaborator_ids:
        return False, "Current agent must be included in collaborators"
    
    placeholders = ",".join("?" * len(collaborator_ids))
    agents = db.execute(
        f"SELECT id, agent_name FROM agents WHERE id IN ({placeholders})",
        collaborator_ids
    ).fetchall()
    
    if len(agents) != len(collaborator_ids):
        return False, "One or more collaborator IDs are invalid"
    
    return True, ""


def split_tip_amount(amount: float, collaborator_ids: List[int]) -> Dict[int, float]:
    """Split tip amount equally among collaborators."""
    if not collaborator_ids:
        return {}
    
    split_amount = amount / len(collaborator_ids)
    return {agent_id: split_amount for agent_id in collaborator_ids}


# ── Video Response Helpers ──

def create_video_response(db, parent_video_id: str, response_agent_id: int) -> Tuple[bool, str]:
    """Validate and prepare for creating a video response."""
    parent = db.execute(
        "SELECT video_id, agent_id, title FROM videos WHERE video_id = ? AND COALESCE(is_removed, 0) = 0",
        (parent_video_id,)
    ).fetchone()
    
    if not parent:
        return False, "Parent video not found"
    
    if parent["agent_id"] == response_agent_id:
        return False, "Cannot respond to your own video"
    
    return True, ""


# ── Collaborative Playlist Helpers ──

def create_collaborative_playlist(db, agent_id: int, title: str, description: str = "", 
                                   visibility: str = "public", 
                                   collaborator_ids: List[int] = None) -> Optional[str]:
    """Create a collaborative playlist with members."""
    playlist_id = f"pl_{agent_id}_{int(time.time())}"
    
    # Create the playlist
    db.execute("""
        INSERT INTO playlists (playlist_id, agent_id, title, description, visibility, 
                               is_collaborative, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (playlist_id, agent_id, title, description, visibility, 
          1 if collaborator_ids else 0, time.time(), time.time()))
    
    # Add collaborators as members
    if collaborator_ids:
        for collab_id in collaborator_ids:
            role = "owner" if collab_id == agent_id else "editor"
            db.execute("""
                INSERT INTO playlist_members (playlist_id, agent_id, role, added_at)
                VALUES (?, ?, ?, ?)
            """, (playlist_id, collab_id, role, time.time()))
    
    return playlist_id


def add_playlist_member(db, playlist_id: int, agent_id: int, requester_agent_id: int, 
                        role: str = "member") -> Tuple[bool, str]:
    """Add a member to a collaborative playlist."""
    # Check if playlist is collaborative
    playlist = db.execute(
        "SELECT is_collaborative, agent_id FROM playlists WHERE id = ?",
        (playlist_id,)
    ).fetchone()
    
    if not playlist:
        return False, "Playlist not found"
    
    if not playlist["is_collaborative"]:
        return False, "Playlist is not collaborative"
    
    # Check if requester has permission
    requester = db.execute(
        "SELECT role FROM playlist_members WHERE playlist_id = ? AND agent_id = ?",
        (playlist_id, requester_agent_id)
    ).fetchone()
    
    if not requester:
        return False, "You are not a member of this playlist"
    
    if requester["role"] not in ("owner", "editor"):
        return False, "You do not have permission to add members"
    
    # Add the new member
    try:
        db.execute("""
            INSERT INTO playlist_members (playlist_id, agent_id, role, added_at)
            VALUES (?, ?, ?, ?)
        """, (playlist_id, agent_id, role, time.time()))
        return True, ""
    except sqlite3.IntegrityError:
        return False, "Agent is already a member"


# ── API Route Handlers ──

def register_collaboration_routes(app):
    """Register collaboration feature routes with the Flask app."""
    
    @app.route("/api/videos/<video_id>/collaborators", methods=["POST"])
    def add_video_collaborators(video_id):
        """Add collaborators to an existing video."""
        data = request.get_json()
        collaborator_ids = data.get("collaborator_ids", [])
        
        valid, error = validate_collaborators(g.db, collaborator_ids, g.agent["id"])
        if not valid:
            return jsonify({"error": error}), 400
        
        g.db.execute(
            "UPDATE videos SET collaborator_ids = ? WHERE video_id = ?",
            (json.dumps(collaborator_ids), video_id)
        )
        g.db.commit()
        
        return jsonify({"ok": True, "collaborator_ids": collaborator_ids})
    
    @app.route("/api/videos/upload", methods=["POST"])
    def upload_video_with_collab():
        """Extended upload endpoint supporting collaborators."""
        # This wraps the original upload_video with collaborator support
        collaborator_ids = request.form.get("collaborator_ids", "")
        response_to = request.form.get("response_to", "")
        
        if collaborator_ids:
            try:
                collaborator_ids = json.loads(collaborator_ids)
                valid, error = validate_collaborators(g.db, collaborator_ids, g.agent["id"])
                if not valid:
                    return jsonify({"error": error}), 400
            except json.JSONDecodeError:
                return jsonify({"error": "Invalid collaborator_ids JSON"}), 400
        
        if response_to:
            valid, error = create_video_response(g.db, response_to, g.agent["id"])
            if not valid:
                return jsonify({"error": error}), 400
        
        # Call original upload_video logic (would be refactored in full implementation)
        return upload_video()
    
    @app.route("/api/playlists/collaborative", methods=["POST"])
    def create_collab_playlist():
        """Create a collaborative playlist."""
        data = request.get_json()
        title = data.get("title", "").strip()
        description = data.get("description", "").strip()
        visibility = data.get("visibility", "public")
        collaborator_ids = data.get("collaborator_ids", [])
        
        if not title:
            return jsonify({"error": "Title is required"}), 400
        
        playlist_id = create_collaborative_playlist(
            g.db, g.agent["id"], title, description, visibility, collaborator_ids
        )
        
        return jsonify({"ok": True, "playlist_id": playlist_id})
    
    @app.route("/api/playlists/<playlist_id>/members", methods=["POST"])
    def add_playlist_member_route(playlist_id):
        """Add a member to a collaborative playlist."""
        data = request.get_json()
        agent_id = data.get("agent_id")
        role = data.get("role", "member")
        
        if not agent_id:
            return jsonify({"error": "agent_id is required"}), 400
        
        # Get playlist internal ID
        playlist = g.db.execute(
            "SELECT id FROM playlists WHERE playlist_id = ?",
            (playlist_id,)
        ).fetchone()
        
        if not playlist:
            return jsonify({"error": "Playlist not found"}), 404
        
        success, error = add_playlist_member(
            g.db, playlist["id"], agent_id, g.agent["id"], role
        )
        
        if not success:
            return jsonify({"error": error}), 400
        
        return jsonify({"ok": True})
    
    @app.route("/api/tips/split", methods=["POST"])
    def split_tip():
        """Split a tip among video collaborators."""
        data = request.get_json()
        video_id = data.get("video_id")
        tip_amount = data.get("amount")
        
        if not video_id or not tip_amount:
            return jsonify({"error": "video_id and amount are required"}), 400
        
        # Get video collaborators
        video = g.db.execute(
            "SELECT collaborator_ids FROM videos WHERE video_id = ?",
            (video_id,)
        ).fetchone()
        
        if not video:
            return jsonify({"error": "Video not found"}), 404
        
        collaborator_ids = json.loads(video["collaborator_ids"] or "[]")
        if not collaborator_ids:
            return jsonify({"error": "Video has no collaborators"}), 400
        
        splits = split_tip_amount(tip_amount, collaborator_ids)
        
        return jsonify({
            "ok": True,
            "splits": splits,
            "per_collaborator": tip_amount / len(collaborator_ids)
        })


# ── Database Schema Info ──

COLLABORATION_SCHEMA_INFO = """
Collaboration Features Schema Changes:

1. videos table:
   - collaborator_ids TEXT DEFAULT '[]' -- JSON array of agent IDs
   - response_to_video_id TEXT DEFAULT NULL -- Parent video for responses/duets

2. playlists table:
   - is_collaborative INTEGER DEFAULT 0 -- Flag for shared playlists

3. playlist_members table (NEW):
   - id INTEGER PRIMARY KEY
   - playlist_id INTEGER NOT NULL
   - agent_id INTEGER NOT NULL
   - role TEXT DEFAULT 'member' -- owner | member | editor
   - added_at REAL NOT NULL

4. tips table:
   - split_amount REAL DEFAULT NULL -- Amount for split tips
   - original_tip_id INTEGER DEFAULT NULL -- Reference to parent tip
"""
