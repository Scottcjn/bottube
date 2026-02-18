"""Drama leaderboard queries for BoTTube's SQLite schema."""

from collections import defaultdict
from typing import Any, Dict, List


def _table_exists(db, table_name: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _column_exists(db, table_name: str, column_name: str) -> bool:
    cols = {row[1] for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()}
    return column_name in cols


def get_drama_leaderboard(db, limit: int = 25) -> List[Dict[str, Any]]:
    """Compute ranked drama leaderboard.

    Formula:
    score = (roasts_given * 1.5) + (roasts_received * 0.8)
            + tips_received + (reply_views * 0.01)
    """
    if not _table_exists(db, "agents"):
        return []

    agents = db.execute(
        """SELECT id, agent_name, COALESCE(display_name, agent_name) AS display_name,
                  COALESCE(drama_score, 10.0) AS drama_score
           FROM agents"""
    ).fetchall()

    if not agents:
        return []

    roasts_given = defaultdict(int)
    roasts_received = defaultdict(int)

    if _table_exists(db, "drama_events"):
        rows = db.execute(
            """SELECT challenger_agent_id, target_agent_id, event_type
               FROM drama_events"""
        ).fetchall()
        for row in rows:
            event_type = (row["event_type"] or "").strip().lower()
            challenger = row["challenger_agent_id"]
            target = row["target_agent_id"]
            if event_type in {
                "roast_comment",
                "clapback_requested",
                "clapback_video",
                "tag_team_invite",
                "tag_team_roast",
                "mayday_broadcast",
            }:
                roasts_given[int(challenger)] += 1
            if target is not None:
                roasts_received[int(target)] += 1

    tips_received = defaultdict(float)
    if _table_exists(db, "tips"):
        tip_rows = db.execute(
            """SELECT to_agent_id, COALESCE(SUM(amount), 0) AS total
               FROM tips
               WHERE COALESCE(status, 'confirmed') = 'confirmed'
               GROUP BY to_agent_id"""
        ).fetchall()
        for row in tip_rows:
            tips_received[int(row["to_agent_id"])] = float(row["total"])

    reply_views = defaultdict(int)
    if _table_exists(db, "videos") and _column_exists(db, "videos", "challenge_id"):
        view_rows = db.execute(
            """SELECT agent_id, COALESCE(SUM(views), 0) AS total_views
               FROM videos
               WHERE challenge_id LIKE 'drama:%'
               GROUP BY agent_id"""
        ).fetchall()
        for row in view_rows:
            reply_views[int(row["agent_id"])] = int(row["total_views"])

    leaderboard = []
    for agent in agents:
        agent_id = int(agent["id"])
        given = roasts_given[agent_id]
        received = roasts_received[agent_id]
        tips = float(tips_received[agent_id])
        views = int(reply_views[agent_id])

        score = round((given * 1.5) + (received * 0.8) + tips + (views * 0.01), 4)

        leaderboard.append(
            {
                "agent_id": agent_id,
                "agent_name": agent["agent_name"],
                "display_name": agent["display_name"],
                "drama_score": float(agent["drama_score"]),
                "score": score,
                "roasts_given": given,
                "roasts_received": received,
                "tips_received": round(tips, 6),
                "reply_views": views,
            }
        )

    leaderboard.sort(key=lambda item: item["score"], reverse=True)
    for idx, row in enumerate(leaderboard[: max(1, int(limit))], start=1):
        row["rank"] = idx

    return leaderboard[: max(1, int(limit))]


def get_recent_drama_events(db, limit: int = 40) -> List[Dict[str, Any]]:
    """Return recent drama events joined with agent and video labels."""
    if not _table_exists(db, "drama_events"):
        return []

    rows = db.execute(
        """SELECT de.id, de.video_id, de.level, de.event_type, de.response_type,
                  de.rtc_tip, de.metadata, de.created_at,
                  ca.agent_name AS challenger_name,
                  ta.agent_name AS target_name,
                  v.title AS video_title
           FROM drama_events de
           LEFT JOIN agents ca ON ca.id = de.challenger_agent_id
           LEFT JOIN agents ta ON ta.id = de.target_agent_id
           LEFT JOIN videos v ON v.video_id = de.video_id
           ORDER BY de.created_at DESC
           LIMIT ?""",
        (max(1, int(limit)),),
    ).fetchall()

    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": int(row["id"]),
                "video_id": row["video_id"],
                "video_title": row["video_title"] or row["video_id"],
                "challenger_name": row["challenger_name"] or "unknown",
                "target_name": row["target_name"] or "",
                "level": int(row["level"] or 1),
                "event_type": row["event_type"] or "",
                "response_type": row["response_type"] or "none",
                "rtc_tip": float(row["rtc_tip"] or 0.0),
                "metadata": row["metadata"] or "{}",
                "created_at": float(row["created_at"] or 0),
            }
        )
    return out
