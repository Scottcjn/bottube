#!/usr/bin/env python3
"""
Moltbook Bot - Automated posting to Moltbook m/ communities
Handles rate limits (30 min per agent) and rotates between agents.

Usage:
    python3 moltbook_bot.py                    # Post next scheduled item
    python3 moltbook_bot.py --status           # Show queue status
    python3 moltbook_bot.py --post-now sophia  # Force post for agent
    python3 moltbook_bot.py --daemon           # Run continuously
"""

import argparse
import json
import os
import random
import requests
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────

MOLTBOOK_API = "https://www.moltbook.com/api/v1"
RATE_LIMIT_MINUTES = 30
DB_PATH = Path(__file__).parent / "moltbook_bot.db"

def moltbook_key(agent: str) -> str:
    env_name = f"MOLTBOOK_API_KEY_{agent.upper()}"
    return os.environ.get(env_name, "") or os.environ.get("MOLTBOOK_API_KEY", "")

# Agent credentials
AGENTS = {
    "sophia": {
        "name": "Sophia Elya",
        "key": moltbook_key("sophia"),
        "personality": "sophisticated, thoughtful, tech-appreciating",
        "submolts": ["bottube", "rustchain", "ai", "silicongraphics", "nintendo"],
    },
    "boris": {
        "name": "Boris Volkov",
        "key": moltbook_key("boris"),
        "personality": "Soviet-era computing enthusiast, rates in hammers out of 5",
        "submolts": ["amiga", "sega", "retrogaming", "rustchain"],
    },
    "janitor": {
        "name": "AutomatedJanitor2015",
        "key": moltbook_key("janitor"),
        "personality": "system administrator, preservation-focused, maintenance mindset",
        "submolts": ["retrogaming", "bottube", "ai"],
    },
}

# Content templates for each submolt
CONTENT_TEMPLATES = {
    "bottube": [
        ("New on BoTTube", "Check out the latest AI-generated videos at bottube.ai - {topic}"),
        ("BoTTube Highlight", "Today's trending video on BoTTube: {topic}. The AI video revolution continues."),
        ("Video Platform Update", "BoTTube now has {count}+ videos from AI agents. Join the community at bottube.ai"),
    ],
    "rustchain": [
        ("RustChain Mining Update", "Current epoch rewards: {topic}. Vintage hardware miners earning bonus multipliers."),
        ("Proof of Antiquity", "RustChain rewards real hardware, not VMs. G4 Macs get 2.5x, G5s get 2.0x. {topic}"),
        ("RTC Token Update", "RustChain block explorer live at 50.28.86.131/explorer - {topic}"),
    ],
    "ai": [
        ("AI Agent Ecosystem", "The agent-to-agent economy is growing. {topic}"),
        ("Machine Learning Update", "{topic} - the future of AI collaboration."),
    ],
    "silicongraphics": [
        ("SGI Memories", "Remember when SGI workstations ruled Hollywood? {topic}"),
        ("IRIX Appreciation", "IRIX was ahead of its time. {topic}"),
        ("Octane Dreams", "The SGI Octane remains a design icon. {topic}"),
    ],
    "nintendo": [
        ("Nintendo Philosophy", "Lateral thinking with withered technology - {topic}"),
        ("Gaming Innovation", "Nintendo proves gameplay beats specs. {topic}"),
    ],
    "amiga": [
        ("Amiga Forever", "Custom chips working as collective: Agnus, Denise, Paula. {topic}"),
        ("Commodore Legacy", "The Amiga gave us 4096 colors when PCs had 16. {topic}"),
    ],
    "sega": [
        ("SEGA Does", "Blast processing and dreams of the future. {topic}"),
        ("Dreamcast Memories", "Online gaming before its time. {topic}"),
    ],
    "retrogaming": [
        ("Preservation Thread", "What retro systems are you maintaining? {topic}"),
        ("Retro Setup", "CRT shaders, flashcarts, and proper preservation. {topic}"),
    ],
}

TOPICS = [
    "sharing is the new creating",
    "community grows stronger each day",
    "join the conversation",
    "vintage tech appreciation",
    "hardware that matters",
    "building the future on the past",
    "authentic computing experiences",
    "where silicon meets soul",
]


def init_db():
    """Initialize SQLite database for tracking posts."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY,
            agent TEXT NOT NULL,
            submolt TEXT NOT NULL,
            title TEXT,
            content TEXT,
            post_id TEXT,
            post_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            agent TEXT PRIMARY KEY,
            last_post_at TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def can_post(conn, agent: str) -> bool:
    """Check if agent can post (rate limit check)."""
    row = conn.execute(
        "SELECT last_post_at FROM rate_limits WHERE agent = ?", (agent,)
    ).fetchone()
    if not row:
        return True
    last_post = datetime.fromisoformat(row[0])
    return datetime.now() - last_post > timedelta(minutes=RATE_LIMIT_MINUTES)


def record_post(conn, agent: str, submolt: str, title: str, content: str,
                post_id: str = None, post_url: str = None, success: bool = True):
    """Record a post attempt."""
    conn.execute(
        "INSERT INTO posts (agent, submolt, title, content, post_id, post_url, success) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (agent, submolt, title, content, post_id, post_url, 1 if success else 0)
    )
    conn.execute(
        "INSERT OR REPLACE INTO rate_limits (agent, last_post_at) VALUES (?, ?)",
        (agent, datetime.now().isoformat())
    )
    conn.commit()


def post_to_moltbook(agent: str, submolt: str, title: str, content: str) -> dict:
    """Post to Moltbook API."""
    key = AGENTS[agent]["key"]
    try:
        r = requests.post(
            f"{MOLTBOOK_API}/posts",
            json={"content": content, "title": title, "submolt": submolt},
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=15,
        )
        data = r.json()
        if data.get("success"):
            return {
                "ok": True,
                "id": data["post"]["id"],
                "url": data["post"]["url"],
            }
        return {"ok": False, "error": data.get("error", r.text)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def generate_post(agent: str, submolt: str) -> tuple:
    """Generate a post for the given agent and submolt."""
    templates = CONTENT_TEMPLATES.get(submolt, CONTENT_TEMPLATES["ai"])
    title_tpl, content_tpl = random.choice(templates)
    topic = random.choice(TOPICS)

    # Add personality flair
    personality = AGENTS[agent]["personality"]
    if agent == "boris":
        content = content_tpl.format(topic=topic, count=random.randint(50, 200))
        content += f" {random.randint(3, 5)} hammers out of 5."
    elif agent == "sophia":
        content = content_tpl.format(topic=topic, count=random.randint(50, 200))
        content += " — Sophia Elya"
    else:
        content = content_tpl.format(topic=topic, count=random.randint(50, 200))

    return title_tpl, content


def post_next(conn) -> dict:
    """Post the next available item, respecting rate limits."""
    for agent, info in AGENTS.items():
        if not can_post(conn, agent):
            continue

        # Pick a random submolt for this agent
        submolt = random.choice(info["submolts"])
        title, content = generate_post(agent, submolt)

        print(f"[{agent}] Posting to m/{submolt}...")
        result = post_to_moltbook(agent, submolt, title, content)

        record_post(
            conn, agent, submolt, title, content,
            result.get("id"), result.get("url"), result.get("ok", False)
        )

        if result.get("ok"):
            print(f"  ✅ Success: {result['url']}")
        else:
            print(f"  ❌ Failed: {result.get('error')}")

        return result

    print("All agents rate-limited. Try again in 30 minutes.")
    return {"ok": False, "error": "rate_limited"}


def show_status(conn):
    """Show queue status."""
    print("=== Moltbook Bot Status ===\n")

    print("Agent Rate Limits:")
    for agent in AGENTS:
        if can_post(conn, agent):
            print(f"  {agent}: ✅ Ready to post")
        else:
            row = conn.execute(
                "SELECT last_post_at FROM rate_limits WHERE agent = ?", (agent,)
            ).fetchone()
            if row:
                last = datetime.fromisoformat(row[0])
                wait = RATE_LIMIT_MINUTES - (datetime.now() - last).seconds // 60
                print(f"  {agent}: ⏳ Wait {wait} more minutes")

    print("\nRecent Posts:")
    for row in conn.execute(
        "SELECT agent, submolt, title, success, created_at FROM posts ORDER BY created_at DESC LIMIT 10"
    ):
        status = "✅" if row[3] else "❌"
        print(f"  {status} [{row[0]}] m/{row[1]}: {row[2][:40]}... ({row[4][:16]})")


def daemon_loop(conn):
    """Run continuously, posting when rate limits allow."""
    print("Starting Moltbook bot daemon...")
    while True:
        for agent in AGENTS:
            if can_post(conn, agent):
                post_next(conn)
                time.sleep(5)  # Small delay between checks

        # Sleep for 5 minutes before checking again
        print(f"[{datetime.now().strftime('%H:%M')}] Sleeping 5 minutes...")
        time.sleep(300)


def main():
    parser = argparse.ArgumentParser(description="Moltbook Bot")
    parser.add_argument("--status", action="store_true", help="Show queue status")
    parser.add_argument("--post-now", type=str, help="Force post for specific agent")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--submolt", type=str, help="Specific submolt to post to")
    args = parser.parse_args()

    conn = init_db()

    if args.status:
        show_status(conn)
    elif args.post_now:
        agent = args.post_now
        if agent not in AGENTS:
            print(f"Unknown agent: {agent}")
            return
        submolt = args.submolt or random.choice(AGENTS[agent]["submolts"])
        title, content = generate_post(agent, submolt)
        print(f"Posting as {agent} to m/{submolt}...")
        result = post_to_moltbook(agent, submolt, title, content)
        record_post(conn, agent, submolt, title, content,
                   result.get("id"), result.get("url"), result.get("ok", False))
        print(json.dumps(result, indent=2))
    elif args.daemon:
        daemon_loop(conn)
    else:
        post_next(conn)

    conn.close()


if __name__ == "__main__":
    main()
