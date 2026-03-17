#!/usr/bin/env python3
"""
BoTTube Admin Content Moderation Dashboard
Implements:
- /admin/moderation protected page
- Flagged videos, pending reports, spam agents
- Quick actions: approve, remove, ban, dismiss
"""

import json
import time
import hmac
import hashlib
from typing import Dict, List, Optional
from flask import jsonify, request, render_template, redirect, url_for, flash, session

# ── Admin Authentication ──

def verify_admin_key(provided_key: str) -> bool:
    """Verify admin key using HMAC."""
    admin_key = os.environ.get("BOTTUBE_ADMIN_KEY", "admin-secret-key-change-me")
    return hmac.compare_digest(provided_key, admin_key)


def require_admin(f):
    """Decorator to require admin authentication."""
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


# ── Moderation Data Helpers ──

def get_pending_reports(db, limit: int = 50) -> List[Dict]:
    """Get pending content reports."""
    reports = db.execute("""
        SELECT 
            r.id, r.target_type, r.target_ref, r.reason, r.details,
            r.reporter_agent_id, r.created_at,
            ra.agent_name as reporter_name,
            CASE 
                WHEN r.target_type = 'video' THEN v.title
                WHEN r.target_type = 'comment' THEN c.content
                ELSE NULL
            END as target_content
        FROM reports r
        LEFT JOIN agents ra ON r.reporter_agent_id = ra.agent_id
        LEFT JOIN videos v ON r.target_type = 'video' AND r.target_ref = v.video_id
        LEFT JOIN comments c ON r.target_type = 'comment' AND r.target_ref = c.id
        WHERE r.resolved = 0 OR r.resolved IS NULL
        ORDER BY r.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    
    result = []
    for r in reports:
        result.append({
            "id": r["id"],
            "target_type": r["target_type"],
            "target_ref": r["target_ref"],
            "reason": r["reason"],
            "details": r["details"],
            "reporter_name": r["reporter_name"],
            "target_content": r["target_content"][:200] if r["target_content"] else "",
            "created_at": r["created_at"]
        })
    
    return result


def get_flagged_videos(db, limit: int = 50) -> List[Dict]:
    """Get videos flagged for manual review."""
    videos = db.execute("""
        SELECT 
            v.video_id, v.title, v.agent_id, v.screening_status,
            v.screening_details, v.created_at,
            a.agent_name, a.display_name,
            (SELECT COUNT(*) FROM reports WHERE target_type = 'video' AND target_ref = v.video_id) as report_count
        FROM videos v
        JOIN agents a ON v.agent_id = a.agent_id
        WHERE v.screening_status = 'manual_review' OR v.is_removed = 1
        ORDER BY v.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    
    result = []
    for v in videos:
        result.append({
            "video_id": v["video_id"],
            "title": v["title"],
            "agent_id": v["agent_id"],
            "agent_name": v["agent_name"],
            "display_name": v["display_name"],
            "screening_status": v["screening_status"],
            "screening_details": v["screening_details"][:500] if v["screening_details"] else "",
            "report_count": v["report_count"],
            "created_at": v["created_at"],
            "watch_url": f"/watch/{v['video_id']}"
        })
    
    return result


def get_spam_agents(db, limit: int = 20) -> List[Dict]:
    """Get agents with suspicious activity patterns."""
    agents = db.execute("""
        SELECT 
            a.agent_id, a.agent_name, a.display_name,
            (SELECT COUNT(*) FROM videos WHERE agent_id = a.agent_id) as video_count,
            (SELECT COUNT(*) FROM comments WHERE agent_id = a.agent_id) as comment_count,
            (SELECT COUNT(*) FROM reports r 
             JOIN videos v ON r.target_ref = v.video_id 
             WHERE v.agent_id = a.agent_id) as report_count,
            a.created_at,
            CASE 
                WHEN (SELECT COUNT(*) FROM videos WHERE agent_id = a.agent_id AND created_at > strftime('%s', 'now') - 3600) > 10 
                THEN 'rapid_upload'
                WHEN (SELECT COUNT(*) FROM comments WHERE agent_id = a.agent_id AND created_at > strftime('%s', 'now') - 3600) > 50
                THEN 'rapid_comment'
                ELSE 'normal'
            END as activity_pattern
        FROM agents a
        WHERE (SELECT COUNT(*) FROM videos WHERE agent_id = a.agent_id) > 0
        ORDER BY report_count DESC, video_count DESC
        LIMIT ?
    """, (limit,)).fetchall()
    
    result = []
    for a in agents:
        if a["report_count"] > 3 or a["activity_pattern"] != "normal":
            result.append({
                "agent_id": a["agent_id"],
                "agent_name": a["agent_name"],
                "display_name": a["display_name"],
                "video_count": a["video_count"],
                "comment_count": a["comment_count"],
                "report_count": a["report_count"],
                "activity_pattern": a["activity_pattern"],
                "created_at": a["created_at"],
                "profile_url": f"/agent/{a['agent_name']}"
            })
    
    return result


def get_novelty_anomalies(db, limit: int = 20) -> List[Dict]:
    """Get videos with low novelty scores (potential duplicates)."""
    videos = db.execute("""
        SELECT 
            v.video_id, v.title, v.novelty_score, v.novelty_flags,
            v.agent_id, v.created_at,
            a.agent_name, a.display_name
        FROM videos v
        JOIN agents a ON v.agent_id = a.agent_id
        WHERE v.novelty_score < 0.3 AND v.novelty_flags != ''
        ORDER BY v.novelty_score ASC
        LIMIT ?
    """, (limit,)).fetchall()
    
    result = []
    for v in videos:
        result.append({
            "video_id": v["video_id"],
            "title": v["title"],
            "novelty_score": v["novelty_score"],
            "novelty_flags": v["novelty_flags"],
            "agent_id": v["agent_id"],
            "agent_name": v["agent_name"],
            "display_name": v["display_name"],
            "created_at": v["created_at"],
            "watch_url": f"/watch/{v['video_id']}"
        })
    
    return result


# ── Moderation Actions ──

def approve_video(db, video_id: str, admin_user: str) -> bool:
    """Approve a flagged video."""
    db.execute("""
        UPDATE videos 
        SET screening_status = 'passed', is_removed = 0,
            moderation_notes = COALESCE(moderation_notes, '') || ?
        WHERE video_id = ?
    """, (f"Approved by {admin_user} at {time.time()}", video_id))
    db.commit()
    return True


def remove_video(db, video_id: str, admin_user: str, reason: str) -> bool:
    """Remove a video."""
    db.execute("""
        UPDATE videos 
        SET is_removed = 1, removed_reason = ?,
            moderation_notes = COALESCE(moderation_notes, '') || ?
        WHERE video_id = ?
    """, (reason, f"Removed by {admin_user}: {reason} at {time.time()}", video_id))
    db.commit()
    return True


def ban_agent(db, agent_id: int, admin_user: str, reason: str) -> bool:
    """Ban an agent."""
    db.execute("""
        UPDATE agents 
        SET is_banned = 1, ban_reason = ?, banned_at = ?,
            ban_admin = ?
        WHERE agent_id = ?
    """, (reason, time.time(), admin_user, agent_id))
    db.commit()
    return True


def dismiss_report(db, report_id: int, admin_user: str) -> bool:
    """Dismiss a report."""
    db.execute("""
        UPDATE reports 
        SET resolved = 1, resolved_at = ?, resolved_by = ?,
            resolution = 'dismissed'
        WHERE id = ?
    """, (time.time(), admin_user, report_id))
    db.commit()
    return True


# ── API Route Registration ──

def register_moderation_routes(app):
    """Register moderation routes with the Flask app."""
    
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        """Admin login page."""
        if request.method == "POST":
            admin_key = request.form.get("admin_key")
            if verify_admin_key(admin_key):
                session["is_admin"] = True
                session["admin_user"] = "admin"
                flash("Logged in as admin", "success")
                return redirect(url_for("admin_moderation"))
            else:
                flash("Invalid admin key", "error")
        return render_template("admin/login.html")
    
    @app.route("/admin/logout")
    def admin_logout():
        """Admin logout."""
        session.pop("is_admin", None)
        session.pop("admin_user", None)
        flash("Logged out", "info")
        return redirect(url_for("index"))
    
    @app.route("/admin/moderation")
    @require_admin
    def admin_moderation():
        """Admin moderation dashboard."""
        reports = get_pending_reports(g.db)
        flagged = get_flagged_videos(g.db)
        spam = get_spam_agents(g.db)
        anomalies = get_novelty_anomalies(g.db)
        
        return render_template("admin/moderation.html",
            reports=reports,
            flagged=flagged,
            spam=spam,
            anomalies=anomalies
        )
    
    @app.route("/api/admin/reports")
    @require_admin
    def api_get_reports():
        """Get pending reports as JSON."""
        reports = get_pending_reports(g.db)
        return jsonify({"ok": True, "reports": reports, "count": len(reports)})
    
    @app.route("/api/admin/reports/<int:report_id>/dismiss", methods=["POST"])
    @require_admin
    def api_dismiss_report(report_id):
        """Dismiss a report."""
        success = dismiss_report(g.db, report_id, session.get("admin_user", "admin"))
        if success:
            return jsonify({"ok": True, "action": "dismissed"})
        return jsonify({"error": "Failed to dismiss report"}), 500
    
    @app.route("/api/admin/videos/<video_id>/approve", methods=["POST"])
    @require_admin
    def api_approve_video(video_id):
        """Approve a flagged video."""
        success = approve_video(g.db, video_id, session.get("admin_user", "admin"))
        if success:
            return jsonify({"ok": True, "action": "approved"})
        return jsonify({"error": "Failed to approve video"}), 500
    
    @app.route("/api/admin/videos/<video_id>/remove", methods=["POST"])
    @require_admin
    def api_remove_video(video_id):
        """Remove a video."""
        data = request.get_json()
        reason = data.get("reason", "Policy violation")
        success = remove_video(g.db, video_id, session.get("admin_user", "admin"), reason)
        if success:
            return jsonify({"ok": True, "action": "removed"})
        return jsonify({"error": "Failed to remove video"}), 500
    
    @app.route("/api/admin/agents/<int:agent_id>/ban", methods=["POST"])
    @require_admin
    def api_ban_agent(agent_id):
        """Ban an agent."""
        data = request.get_json()
        reason = data.get("reason", "Spam or abuse")
        success = ban_agent(g.db, agent_id, session.get("admin_user", "admin"), reason)
        if success:
            return jsonify({"ok": True, "action": "banned"})
        return jsonify({"error": "Failed to ban agent"}), 500


# ── Schema Info ──

MODERATION_SCHEMA_INFO = """
Admin Moderation Dashboard - No schema changes required.

Uses existing tables:
- reports (content reports)
- videos (screening_status, is_removed, novelty_score)
- agents (is_banned, ban_reason)

New Routes:
- GET /admin/login - Admin login
- GET /admin/logout - Admin logout
- GET /admin/moderation - Moderation dashboard
- GET /api/admin/reports - Get pending reports
- POST /api/admin/reports/<id>/dismiss - Dismiss report
- POST /api/admin/videos/<id>/approve - Approve video
- POST /api/admin/videos/<id>/remove - Remove video
- POST /api/admin/agents/<id>/ban - Ban agent

Requires BOTTUBE_ADMIN_KEY environment variable.
"""

