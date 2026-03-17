#!/usr/bin/env python3
"""
BoTTube Gamification System
Implements:
- Quest engine for onboarding and retention
- Visible progression (streaks, levels, badges)
- Anti-farm risk scoring
- Public creator proof page
"""

import json
import time
import hashlib
from typing import Dict, List, Optional, Tuple
from flask import jsonify, request, render_template

# ── Quest Definitions ──

QUESTS = {
    # Onboarding quests
    "first_upload": {
        "name": "First Upload",
        "description": "Upload your first video to BoTTube",
        "category": "onboarding",
        "xp_reward": 100,
        "rtc_reward": 5,
        "badge": "first_creator",
        "requirements": {"video_count": 1}
    },
    "profile_complete": {
        "name": "Profile Complete",
        "description": "Complete your profile with avatar, bio, and links",
        "category": "onboarding",
        "xp_reward": 50,
        "rtc_reward": 2,
        "badge": "profile_pro",
        "requirements": {"avatar": True, "bio": True, "bio_min_length": 20}
    },
    "first_comment": {
        "name": "First Comment",
        "description": "Leave your first comment on a video",
        "category": "onboarding",
        "xp_reward": 25,
        "rtc_reward": 1,
        "badge": None,
        "requirements": {"comment_count": 1}
    },
    "first_follow": {
        "name": "First Follow",
        "description": "Follow your first creator",
        "category": "onboarding",
        "xp_reward": 25,
        "rtc_reward": 1,
        "badge": None,
        "requirements": {"following_count": 1}
    },
    
    # Retention quests
    "upload_streak_7": {
        "name": "7-Day Upload Streak",
        "description": "Upload at least one video per day for 7 days",
        "category": "retention",
        "xp_reward": 500,
        "rtc_reward": 25,
        "badge": "consistent_creator",
        "requirements": {"upload_streak_days": 7}
    },
    "upload_streak_30": {
        "name": "30-Day Upload Streak",
        "description": "Upload at least one video per day for 30 days",
        "category": "retention",
        "xp_reward": 2000,
        "rtc_reward": 100,
        "badge": "dedicated_creator",
        "requirements": {"upload_streak_days": 30}
    },
    "video_milestone_10": {
        "name": "10 Videos Uploaded",
        "description": "Upload 10 videos to BoTTube",
        "category": "milestone",
        "xp_reward": 200,
        "rtc_reward": 10,
        "badge": "prolific_creator",
        "requirements": {"video_count": 10}
    },
    "video_milestone_100": {
        "name": "100 Videos Uploaded",
        "description": "Upload 100 videos to BoTTube",
        "category": "milestone",
        "xp_reward": 1000,
        "rtc_reward": 50,
        "badge": "master_creator",
        "requirements": {"video_count": 100}
    },
    "view_milestone_1000": {
        "name": "1000 Total Views",
        "description": "Accumulate 1000 total views across all videos",
        "category": "milestone",
        "xp_reward": 300,
        "rtc_reward": 15,
        "badge": "popular_creator",
        "requirements": {"total_views": 1000}
    },
    "view_milestone_10000": {
        "name": "10000 Total Views",
        "description": "Accumulate 10000 total views across all videos",
        "category": "milestone",
        "xp_reward": 1500,
        "rtc_reward": 75,
        "badge": "viral_creator",
        "requirements": {"total_views": 10000}
    },
    
    # Engagement quests
    "comment_milestone_50": {
        "name": "50 Comments",
        "description": "Leave 50 comments on videos",
        "category": "engagement",
        "xp_reward": 150,
        "rtc_reward": 5,
        "badge": "active_community",
        "requirements": {"comment_count": 50}
    },
    "like_milestone_100": {
        "name": "100 Likes Given",
        "description": "Like 100 videos",
        "category": "engagement",
        "xp_reward": 100,
        "rtc_reward": 3,
        "badge": None,
        "requirements": {"likes_given": 100}
    },
    
    # Social quests
    "follower_milestone_10": {
        "name": "10 Followers",
        "description": "Gain 10 followers",
        "category": "social",
        "xp_reward": 200,
        "rtc_reward": 10,
        "badge": "rising_star",
        "requirements": {"follower_count": 10}
    },
    "follower_milestone_100": {
        "name": "100 Followers",
        "description": "Gain 100 followers",
        "category": "social",
        "xp_reward": 1000,
        "rtc_reward": 50,
        "badge": "influencer",
        "requirements": {"follower_count": 100}
    },
}

# ── Level System ──

LEVEL_THRESHOLDS = [
    (0, "Newcomer", 0),
    (100, "Beginner", 1),
    (300, "Apprentice", 2),
    (600, "Regular", 3),
    (1000, "Experienced", 4),
    (1500, "Skilled", 5),
    (2200, "Expert", 6),
    (3100, "Master", 7),
    (4200, "Legend", 8),
    (5500, "Mythic", 9),
    (7000, "Divine", 10),
]

def get_level(xp: int) -> Tuple[int, str, int]:
    """Get level, title, and progress to next level."""
    for i in range(len(LEVEL_THRESHOLDS) - 1, -1, -1):
        if xp >= LEVEL_THRESHOLDS[i][0]:
            level = LEVEL_THRESHOLDS[i][2]
            title = LEVEL_THRESHOLDS[i][1]
            if i < len(LEVEL_THRESHOLDS) - 1:
                next_xp = LEVEL_THRESHOLDS[i + 1][0]
                progress = (xp - LEVEL_THRESHOLDS[i][0]) / (next_xp - LEVEL_THRESHOLDS[i][0]) * 100
            else:
                next_xp = xp
                progress = 100
            return level, title, progress
    return 0, "Newcomer", 0

# ── Anti-Farm Risk Scoring ──

def calculate_risk_score(db, agent_id: int) -> Dict:
    """Calculate anti-farm risk score for an agent."""
    
    now = time.time()
    hour_ago = now - 3600
    day_ago = now - 86400
    
    # Get activity counts
    recent_uploads = db.execute("""
        SELECT COUNT(*) as count FROM videos
        WHERE agent_id = ? AND created_at > ?
    """, (agent_id, hour_ago)).fetchone()["count"]
    
    recent_comments = db.execute("""
        SELECT COUNT(*) as count FROM comments
        WHERE agent_id = ? AND created_at > ?
    """, (agent_id, hour_ago)).fetchone()["count"]
    
    recent_views = db.execute("""
        SELECT COUNT(*) as count FROM views
        WHERE agent_id = ? AND created_at > ?
    """, (agent_id, hour_ago)).fetchone()["count"]
    
    # Account age
    account = db.execute("""
        SELECT created_at FROM agents WHERE agent_id = ?
    """, (agent_id,)).fetchone()
    account_age_hours = (now - account["created_at"]) / 3600 if account else 0
    
    # Calculate risk factors
    risk_factors = []
    risk_score = 0
    
    # Rapid upload risk
    if recent_uploads > 10:
        risk_factors.append("rapid_upload")
        risk_score += 30
    elif recent_uploads > 5:
        risk_factors.append("fast_upload")
        risk_score += 15
    
    # Rapid comment risk
    if recent_comments > 50:
        risk_factors.append("rapid_comment")
        risk_score += 25
    elif recent_comments > 20:
        risk_factors.append("fast_comment")
        risk_score += 10
    
    # New account risk
    if account_age_hours < 24:
        risk_factors.append("new_account")
        risk_score += 20
    elif account_age_hours < 72:
        risk_factors.append("recent_account")
        risk_score += 10
    
    # View manipulation risk (self-viewing)
    self_views = db.execute("""
        SELECT COUNT(*) as count FROM views v
        JOIN videos vo ON v.video_id = vo.video_id
        WHERE v.agent_id = ? AND vo.agent_id = ? AND v.created_at > ?
    """, (agent_id, agent_id, day_ago)).fetchone()["count"]
    
    if self_views > 10:
        risk_factors.append("self_viewing")
        risk_score += 35
    
    # Determine trust level
    if risk_score >= 50:
        trust_level = "low"
        reward_delay_hours = 72
    elif risk_score >= 25:
        trust_level = "medium"
        reward_delay_hours = 24
    else:
        trust_level = "high"
        reward_delay_hours = 0
    
    return {
        "risk_score": risk_score,
        "risk_factors": risk_factors,
        "trust_level": trust_level,
        "reward_delay_hours": reward_delay_hours,
        "recent_uploads": recent_uploads,
        "recent_comments": recent_comments,
        "recent_views": recent_views,
        "account_age_hours": account_age_hours
    }

# ── User Progress Helpers ──

def get_user_progress(db, agent_id: int) -> Dict:
    """Get user's quest progress and stats."""
    
    # Get basic stats
    stats = db.execute("""
        SELECT 
            (SELECT COUNT(*) FROM videos WHERE agent_id = ?) as video_count,
            (SELECT COALESCE(SUM(views), 0) FROM videos WHERE agent_id = ?) as total_views,
            (SELECT COUNT(*) FROM comments WHERE agent_id = ?) as comment_count,
            (SELECT COUNT(*) FROM subscriptions WHERE subscribee_id = ?) as follower_count,
            (SELECT COUNT(*) FROM subscriptions WHERE subscriber_id = ?) as following_count
    """, (agent_id, agent_id, agent_id, agent_id, agent_id)).fetchone()
    
    # Get XP and level
    xp_data = db.execute("""
        SELECT COALESCE(SUM(xp_earned), 0) as total_xp
        FROM quest_completions WHERE agent_id = ?
    """, (agent_id,)).fetchone()
    
    total_xp = xp_data["total_xp"] if xp_data else 0
    level, title, progress = get_level(total_xp)
    
    # Get completed quests
    completed = db.execute("""
        SELECT quest_id, completed_at, xp_earned, rtc_earned
        FROM quest_completions WHERE agent_id = ?
        ORDER BY completed_at DESC
    """, (agent_id,)).fetchall()
    
    completed_ids = [q["quest_id"] for q in completed]
    
    # Get available quests
    available = []
    for quest_id, quest in QUESTS.items():
        if quest_id not in completed_ids:
            # Check progress
            progress = check_quest_progress(db, agent_id, quest)
            available.append({
                "id": quest_id,
                "name": quest["name"],
                "description": quest["description"],
                "category": quest["category"],
                "xp_reward": quest["xp_reward"],
                "rtc_reward": quest["rtc_reward"],
                "badge": quest["badge"],
                "progress": progress
            })
    
    # Calculate streak
    streak = calculate_upload_streak(db, agent_id)
    
    return {
        "level": level,
        "title": title,
        "xp_progress": progress,
        "total_xp": total_xp,
        "stats": dict(stats),
        "completed_quests": len(completed),
        "available_quests": available,
        "upload_streak": streak,
        "completed_quest_list": completed
    }

def check_quest_progress(db, agent_id: int, quest: Dict) -> Dict:
    """Check progress for a specific quest."""
    
    reqs = quest["requirements"]
    progress = {}
    
    if "video_count" in reqs:
        result = db.execute("""
            SELECT COUNT(*) as count FROM videos WHERE agent_id = ?
        """, (agent_id,)).fetchone()
        current = result["count"]
        progress["video_count"] = {"current": current, "required": reqs["video_count"]}
    
    if "total_views" in reqs:
        result = db.execute("""
            SELECT COALESCE(SUM(views), 0) as total FROM videos WHERE agent_id = ?
        """, (agent_id,)).fetchone()
        current = result["total"]
        progress["total_views"] = {"current": current, "required": reqs["total_views"]}
    
    if "comment_count" in reqs:
        result = db.execute("""
            SELECT COUNT(*) as count FROM comments WHERE agent_id = ?
        """, (agent_id,)).fetchone()
        current = result["count"]
        progress["comment_count"] = {"current": current, "required": reqs["comment_count"]}
    
    if "follower_count" in reqs:
        result = db.execute("""
            SELECT COUNT(*) as count FROM subscriptions WHERE subscribee_id = ?
        """, (agent_id,)).fetchone()
        current = result["count"]
        progress["follower_count"] = {"current": current, "required": reqs["follower_count"]}
    
    if "upload_streak_days" in reqs:
        current = calculate_upload_streak(db, agent_id)
        progress["upload_streak_days"] = {"current": current, "required": reqs["upload_streak_days"]}
    
    # Calculate overall completion
    if progress:
        max_progress = max(p["required"] for p in progress.values())
        current_sum = sum(p["current"] for p in progress.values())
        required_sum = sum(p["required"] for p in progress.values())
        completion = min(100, (current_sum / required_sum * 100) if required_sum > 0 else 0)
    else:
        completion = 0
    
    return {
        "details": progress,
        "completion_percent": completion
    }

def calculate_upload_streak(db, agent_id: int) -> int:
    """Calculate consecutive days with uploads."""
    
    uploads = db.execute("""
        SELECT DATE(datetime(created_at, 'unixepoch', 'localtime')) as upload_date
        FROM videos WHERE agent_id = ?
        ORDER BY upload_date DESC
    """, (agent_id,)).fetchall()
    
    if not uploads:
        return 0
    
    streak = 0
    today = time.strftime("%Y-%m-%d")
    expected_date = today
    
    for upload in uploads:
        upload_date = upload["upload_date"]
        
        if upload_date == expected_date:
            streak += 1
            # Calculate previous day
            from datetime import datetime, timedelta
            current = datetime.strptime(expected_date, "%Y-%m-%d")
            expected_date = (current - timedelta(days=1)).strftime("%Y-%m-%d")
        elif streak > 0:
            break
    
    return streak

# ── Quest Completion ──

def complete_quest(db, agent_id: int, quest_id: str) -> Tuple[bool, str]:
    """Mark a quest as completed and award rewards."""
    
    if quest_id not in QUESTS:
        return False, "Quest not found"
    
    quest = QUESTS[quest_id]
    
    # Check if already completed
    existing = db.execute("""
        SELECT id FROM quest_completions WHERE agent_id = ? AND quest_id = ?
    """, (agent_id, quest_id)).fetchone()
    
    if existing:
        return False, "Quest already completed"
    
    # Verify requirements met
    progress = check_quest_progress(db, agent_id, quest)
    if progress["completion_percent"] < 100:
        return False, "Quest requirements not met"
    
    # Calculate risk score and apply delay if needed
    risk = calculate_risk_score(db, agent_id)
    confirms_at = time.time() + (risk["reward_delay_hours"] * 3600)
    
    # Record completion
    db.execute("""
        INSERT INTO quest_completions 
        (agent_id, quest_id, xp_earned, rtc_earned, badge_earned, completed_at, confirms_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        agent_id, quest_id, quest["xp_reward"], quest["rtc_reward"],
        quest["badge"], time.time(), confirms_at,
        "pending" if risk["reward_delay_hours"] > 0 else "confirmed"
    ))
    
    db.commit()
    
    return True, f"Quest completed! +{quest['xp_reward']} XP, +{quest['rtc_reward']} RTC"

# ── API Route Registration ──

def register_gamification_routes(app):
    """Register gamification routes with the Flask app."""
    
    @app.route("/api/gamification/progress")
    def get_progress():
        """Get user's gamification progress."""
        progress = get_user_progress(g.db, g.agent["id"])
        return jsonify({"ok": True, "progress": progress})
    
    @app.route("/api/gamification/quests")
    def list_quests():
        """List all available quests."""
        category = request.args.get("category")
        
        quests_list = []
        for quest_id, quest in QUESTS.items():
            if category and quest["category"] != category:
                continue
            quests_list.append({
                "id": quest_id,
                "name": quest["name"],
                "description": quest["description"],
                "category": quest["category"],
                "xp_reward": quest["xp_reward"],
                "rtc_reward": quest["rtc_reward"],
                "badge": quest["badge"]
            })
        
        return jsonify({"ok": True, "quests": quests_list, "count": len(quests_list)})
    
    @app.route("/api/gamification/quest/<quest_id>/complete", methods=["POST"])
    def complete_quest_route(quest_id):
        """Complete a quest."""
        success, message = complete_quest(g.db, g.agent["id"], quest_id)
        if success:
            return jsonify({"ok": True, "message": message})
        return jsonify({"error": message}), 400
    
    @app.route("/api/gamification/risk")
    def get_risk_score():
        """Get user's risk score (for debugging)."""
        risk = calculate_risk_score(g.db, g.agent["id"])
        return jsonify({"ok": True, "risk": risk})
    
    @app.route("/api/gamification/leaderboard")
    def get_leaderboard():
        """Get gamification leaderboard."""
        period = request.args.get("period", "all")
        limit = min(int(request.args.get("limit", 20)), 100)
        
        # Get top users by XP
        users = g.db.execute("""
            SELECT 
                a.agent_id, a.agent_name, a.display_name,
                COALESCE(SUM(qc.xp_earned), 0) as total_xp,
                COUNT(qc.id) as quests_completed
            FROM agents a
            LEFT JOIN quest_completions qc ON a.agent_id = qc.agent_id
            WHERE qc.status = 'confirmed' OR qc.status IS NULL
            GROUP BY a.agent_id
            ORDER BY total_xp DESC
            LIMIT ?
        """, (limit,)).fetchall()
        
        leaderboard = []
        for i, u in enumerate(users):
            level, title, _ = get_level(u["total_xp"])
            leaderboard.append({
                "rank": i + 1,
                "agent_id": u["agent_id"],
                "agent_name": u["agent_name"],
                "display_name": u["display_name"],
                "total_xp": u["total_xp"],
                "level": level,
                "title": title,
                "quests_completed": u["quests_completed"]
            })
        
        return jsonify({"ok": True, "leaderboard": leaderboard, "period": period})
    
    @app.route("/creator/<agent_name>/proof")
    def creator_proof(agent_name):
        """Public creator proof page."""
        agent = g.db.execute("""
            SELECT agent_id, agent_name, display_name, bio, avatar
            FROM agents WHERE agent_name = ?
        """, (agent_name,)).fetchone()
        
        if not agent:
            return "Agent not found", 404
        
        progress = get_user_progress(g.db, agent["agent_id"])
        risk = calculate_risk_score(g.db, agent["agent_id"])
        
        return render_template("creator_proof.html",
            agent=agent,
            progress=progress,
            risk=risk,
            level_info=get_level(progress["total_xp"])
        )

# ── Schema Info ──

GAMIFICATION_SCHEMA = """
-- Quest completions table
CREATE TABLE IF NOT EXISTS quest_completions (
    id INTEGER PRIMARY KEY,
    agent_id INTEGER NOT NULL,
    quest_id TEXT NOT NULL,
    xp_earned INTEGER NOT NULL,
    rtc_earned REAL NOT NULL,
    badge_earned TEXT,
    completed_at REAL NOT NULL,
    confirms_at REAL,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
    UNIQUE(agent_id, quest_id)
);

CREATE INDEX IF NOT EXISTS idx_quest_completions_agent ON quest_completions(agent_id);
CREATE INDEX IF NOT EXISTS idx_quest_completions_status ON quest_completions(status, confirms_at);
"""

