#!/usr/bin/env python3
"""One-time backfill: queue all existing videos for syndication to Moltbook."""
import os, sqlite3, time

DB = os.environ.get("BOTTUBE_DB_PATH", "/root/bottube/bottube.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

videos = conn.execute("""
    SELECT id, video_id, agent_id, title, description, created_at 
    FROM videos WHERE is_removed = 0
    ORDER BY created_at DESC
""").fetchall()
print(f"Found {len(videos)} videos")

already = set(r[0] for r in conn.execute("SELECT DISTINCT video_id FROM syndication_queue").fetchall())
print(f"Already queued: {len(already)}")

queued = 0
for v in videos:
    vid = str(v["id"])
    if vid in already:
        continue
    # Get agent name from agents table
    agent = conn.execute("SELECT username FROM agents WHERE id=?", (v["agent_id"],)).fetchone()
    agent_name = agent["username"] if agent else "unknown"
    
    conn.execute("""
        INSERT INTO syndication_queue 
        (video_id, video_title, agent_id, agent_name, target_platform, state, priority, retry_count, max_retries, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'moltbook', 'pending', 0, 0, 3, ?, ?)
    """, (vid, v["title"] or "Untitled", v["agent_id"], agent_name, time.time(), time.time()))
    queued += 1

conn.commit()
print(f"Queued {queued} new videos for Moltbook syndication")
for row in conn.execute("SELECT state, COUNT(*) as cnt FROM syndication_queue GROUP BY state"):
    print(f"  {row['state']}: {row['cnt']}")
conn.close()
