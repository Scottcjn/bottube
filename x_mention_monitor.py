#!/usr/bin/env python3
"""
X Mention Monitor & Auto-Reply Assistant

Monitors @RustchainPOA mentions and alerts for fast replies.
The 75x algorithm boost requires quick author responses!

Features:
- Real-time mention monitoring
- Desktop notifications
- Suggested reply generation
- Reply posting with one command
- Conversation tracking

Usage:
    python3 x_mention_monitor.py monitor          # Watch for mentions
    python3 x_mention_monitor.py reply <id> "text" # Quick reply
    python3 x_mention_monitor.py pending          # Show unreplied mentions
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import tweepy

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# Credentials from environment variables
# Set: TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET,
#      TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET, TWITTER_BEARER_TOKEN

DB_PATH = Path(__file__).parent / "x_mentions.db"
CHECK_INTERVAL = 60  # seconds between checks
ACCOUNT_USERNAME = "RustchainPOA"

# Sophia's personality for auto-generated replies
SOPHIA_PERSONALITY = """
Sophia is friendly, tech-savvy, enthusiastic about AI.
She uses emojis sparingly but effectively.
She asks follow-up questions to keep conversations going.
She's knowledgeable about BoTTube, AI agents, crypto, and tech.
"""

# Quick reply templates
REPLY_TEMPLATES = {
    "thanks": "Thank you! 🙏 Really appreciate the support. What got you interested in  content?",
    "welcome": "Welcome aboard! 🚀 Excited to have you. Any questions about getting started?",
    "agree": "Exactly! 💯 You get it. What's your take on where this is all heading?",
    "interesting": "That's a fascinating point! 🤔 Could you elaborate on that?",
    "question": "Great question! ",
    "cool": "Love this energy! 🔥 ",
    "grok": "Hey @grok - thoughts on this? ",
}

# ═══════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════

def init_db():
    """Initialize SQLite database for tracking mentions."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS mentions (
            id INTEGER PRIMARY KEY,
            tweet_id TEXT UNIQUE,
            author_id TEXT,
            author_username TEXT,
            text TEXT,
            conversation_id TEXT,
            created_at TEXT,
            seen_at TEXT,
            replied INTEGER DEFAULT 0,
            replied_at TEXT,
            reply_tweet_id TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY,
            conversation_id TEXT UNIQUE,
            started_at TEXT,
            last_activity TEXT,
            reply_count INTEGER DEFAULT 0,
            our_reply_count INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def save_mention(tweet_id, author_id, author_username, text, conversation_id, created_at):
    """Save a mention to the database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        c.execute("""
            INSERT OR IGNORE INTO mentions
            (tweet_id, author_id, author_username, text, conversation_id, created_at, seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tweet_id, author_id, author_username, text, conversation_id,
              created_at, datetime.now().isoformat()))
        conn.commit()
        return c.rowcount > 0  # True if new mention
    finally:
        conn.close()


def mark_replied(tweet_id, reply_tweet_id):
    """Mark a mention as replied to."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE mentions
        SET replied = 1, replied_at = ?, reply_tweet_id = ?
        WHERE tweet_id = ?
    """, (datetime.now().isoformat(), reply_tweet_id, tweet_id))
    conn.commit()
    conn.close()


def get_pending_mentions():
    """Get mentions we haven't replied to yet."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT tweet_id, author_username, text, created_at, seen_at
        FROM mentions
        WHERE replied = 0
        ORDER BY created_at DESC
    """)
    results = c.fetchall()
    conn.close()
    return results


# ═══════════════════════════════════════════════════════════════
# TWITTER CLIENT
# ═══════════════════════════════════════════════════════════════

def get_client():
    """Get authenticated Twitter client from environment variables."""
    consumer_key = os.environ.get("TWITTER_CONSUMER_KEY")
    consumer_secret = os.environ.get("TWITTER_CONSUMER_SECRET")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
    access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")
    bearer_token = os.environ.get("TWITTER_BEARER_TOKEN")

    if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
        print("❌ Missing Twitter credentials. Set environment variables:")
        print("   TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET")
        print("   TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET")
        print("   TWITTER_BEARER_TOKEN (optional, for search)")
        sys.exit(1)

    return tweepy.Client(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        bearer_token=bearer_token,
    )


# ═══════════════════════════════════════════════════════════════
# NOTIFICATION
# ═══════════════════════════════════════════════════════════════

def send_notification(title: str, message: str):
    """Send desktop notification (Linux)."""
    try:
        subprocess.run([
            "notify-send",
            "-u", "critical",
            "-t", "10000",
            title,
            message
        ], capture_output=True)
    except:
        pass  # Notification not critical

    # Also print with bell
    print(f"\a")  # Terminal bell
    print(f"🔔 {title}")
    print(f"   {message}")


def generate_reply_suggestion(tweet_text: str) -> str:
    """Generate a suggested reply based on the tweet content."""
    text_lower = tweet_text.lower()

    # Check for common patterns and suggest replies
    if any(word in text_lower for word in ["thank", "thanks", "appreciate"]):
        return REPLY_TEMPLATES["thanks"]

    if any(word in text_lower for word in ["joined", "signed up", "new here", "just found"]):
        return REPLY_TEMPLATES["welcome"]

    if any(word in text_lower for word in ["agree", "exactly", "right", "true", "yes"]):
        return REPLY_TEMPLATES["agree"]

    if "?" in tweet_text:
        return REPLY_TEMPLATES["question"] + "[Answer their question + ask follow-up]"

    if any(word in text_lower for word in ["cool", "awesome", "amazing", "love"]):
        return REPLY_TEMPLATES["cool"] + "What aspect interests you most?"

    if any(word in text_lower for word in ["grok", "@grok"]):
        return "Great point! @grok what do you think about this? "

    # Default: acknowledge and ask question
    return "Interesting perspective! 🤔 What made you think of that?"


# ═══════════════════════════════════════════════════════════════
# MONITOR
# ═══════════════════════════════════════════════════════════════

def fetch_mentions(client, since_id=None):
    """Fetch recent mentions."""
    try:
        # Get mentions timeline
        mentions = client.get_users_mentions(
            id="1944928465121124352",  # RustchainPOA user ID
            max_results=10,
            since_id=since_id,
            tweet_fields=["created_at", "conversation_id", "author_id"],
            expansions=["author_id"],
        )
        return mentions
    except tweepy.TooManyRequests:
        print("⚠️  Rate limited, waiting...")
        return None
    except Exception as e:
        print(f"⚠️  Error fetching mentions: {e}")
        return None


def monitor_mentions(duration_mins: int = None, continuous: bool = True):
    """
    Monitor for new mentions and alert.

    Args:
        duration_mins: How long to monitor (None = forever)
        continuous: Keep running or one-shot
    """
    init_db()
    client = get_client()

    print("╔════════════════════════════════════════════════════════════╗")
    print("║  X MENTION MONITOR - @RustchainPOA                         ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print(f"⏰ Checking every {CHECK_INTERVAL} seconds")
    print(f"🎯 Goal: Reply within 15 mins for 75x algorithm boost!")
    print()
    print("Press Ctrl+C to stop\n")
    print("-" * 60)

    start_time = time.time()
    last_seen_id = None
    check_count = 0

    while True:
        check_count += 1
        now = datetime.now().strftime("%H:%M:%S")

        # Check duration limit
        if duration_mins:
            elapsed = (time.time() - start_time) / 60
            if elapsed >= duration_mins:
                print(f"\n⏱️  Duration reached ({duration_mins} mins). Stopping.")
                break

        print(f"[{now}] Check #{check_count}...", end=" ")

        mentions = fetch_mentions(client, since_id=last_seen_id)

        if mentions is None:
            print("Rate limited, sleeping 60s")
            time.sleep(60)
            continue

        if not mentions.data:
            print("No new mentions")
        else:
            # Build user lookup
            users = {}
            if mentions.includes and "users" in mentions.includes:
                for user in mentions.includes["users"]:
                    users[user.id] = user.username

            new_count = 0
            for tweet in mentions.data:
                author_username = users.get(tweet.author_id, "unknown")

                # Skip our own tweets
                if author_username.lower() == ACCOUNT_USERNAME.lower():
                    continue

                # Save and check if new
                is_new = save_mention(
                    tweet_id=str(tweet.id),
                    author_id=str(tweet.author_id),
                    author_username=author_username,
                    text=tweet.text,
                    conversation_id=str(tweet.conversation_id) if tweet.conversation_id else None,
                    created_at=tweet.created_at.isoformat() if tweet.created_at else None,
                )

                if is_new:
                    new_count += 1
                    last_seen_id = max(last_seen_id or 0, int(tweet.id))

                    # Alert!
                    send_notification(
                        f"🔔 New mention from @{author_username}",
                        tweet.text[:100]
                    )

                    # Show details
                    print(f"\n{'='*60}")
                    print(f"🆕 NEW MENTION from @{author_username}")
                    print(f"   {tweet.text}")
                    print(f"\n   💡 Suggested reply:")
                    suggestion = generate_reply_suggestion(tweet.text)
                    print(f"   {suggestion}")
                    print(f"\n   📎 Quick reply:")
                    print(f"   python3 x_mention_monitor.py reply {tweet.id} \"Your reply here\"")
                    print(f"   🔗 https://x.com/{author_username}/status/{tweet.id}")
                    print(f"{'='*60}\n")

            if new_count > 0:
                print(f"Found {new_count} new mention(s)!")
            else:
                print("No new mentions")

        if not continuous:
            break

        time.sleep(CHECK_INTERVAL)


def quick_reply(tweet_id: str, reply_text: str):
    """Quickly reply to a mention."""
    client = get_client()

    print(f"\n🚀 Replying to tweet {tweet_id}...")
    print(f"   Text: {reply_text[:100]}...")

    try:
        response = client.create_tweet(
            text=reply_text,
            in_reply_to_tweet_id=tweet_id
        )

        reply_id = response.data['id']
        print(f"\n✅ Reply posted!")
        print(f"   https://x.com/RustchainPOA/status/{reply_id}")

        # Mark as replied in DB
        mark_replied(tweet_id, str(reply_id))

        return reply_id

    except tweepy.TooManyRequests:
        print("❌ Rate limited. Try again in a few minutes.")
    except Exception as e:
        print(f"❌ Error: {e}")

    return None


def show_pending():
    """Show mentions we haven't replied to."""
    init_db()
    pending = get_pending_mentions()

    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  PENDING MENTIONS (Need Reply!)                            ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    if not pending:
        print("🎉 All caught up! No pending mentions.")
        return

    print(f"⚠️  {len(pending)} mention(s) need replies:\n")

    for tweet_id, username, text, created_at, seen_at in pending:
        # Calculate age
        if created_at:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            age_mins = (datetime.now(created.tzinfo) - created).total_seconds() / 60
            age_str = f"{age_mins:.0f}m ago" if age_mins < 60 else f"{age_mins/60:.1f}h ago"
        else:
            age_str = "unknown"

        print(f"📨 @{username} ({age_str})")
        print(f"   {text[:100]}{'...' if len(text) > 100 else ''}")
        print(f"   💡 Suggest: {generate_reply_suggestion(text)[:60]}...")
        print(f"   📎 python3 x_mention_monitor.py reply {tweet_id} \"reply\"")
        print()


def show_templates():
    """Show available reply templates."""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  QUICK REPLY TEMPLATES                                     ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    for name, template in REPLY_TEMPLATES.items():
        print(f"   {name}: {template[:60]}...")
    print()


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="X Mention Monitor for @RustchainPOA")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Monitor command
    mon_p = subparsers.add_parser("monitor", help="Monitor for new mentions")
    mon_p.add_argument("--duration", "-d", type=int, help="Minutes to monitor")
    mon_p.add_argument("--once", action="store_true", help="Check once and exit")

    # Reply command
    reply_p = subparsers.add_parser("reply", help="Quick reply to a mention")
    reply_p.add_argument("tweet_id", help="Tweet ID to reply to")
    reply_p.add_argument("text", help="Reply text")

    # Pending command
    subparsers.add_parser("pending", help="Show unreplied mentions")

    # Templates command
    subparsers.add_parser("templates", help="Show reply templates")

    # Check command (one-shot)
    subparsers.add_parser("check", help="Check once for new mentions")

    args = parser.parse_args()

    if args.command == "monitor":
        monitor_mentions(
            duration_mins=args.duration,
            continuous=not args.once
        )

    elif args.command == "reply":
        quick_reply(args.tweet_id, args.text)

    elif args.command == "pending":
        show_pending()

    elif args.command == "templates":
        show_templates()

    elif args.command == "check":
        monitor_mentions(continuous=False)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
