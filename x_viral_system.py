#!/usr/bin/env python3
"""
BoTTube X Viral Posting System

Based on X's open-source algorithm analysis:
- 75x weight for author replies to comments
- 12x weight for profile visits + engagement
- 10x weight for 2+ min conversation dwell
- Links in main tweet = -30-50% penalty
- First 30 minutes are critical

This system implements:
1. Viral hook templates (proven engagement patterns)
2. Optimal posting structure (link in reply, question hook)
3. Auto-engagement monitor (reply to comments fast)
4. Content calendar with peak times
5. A/B testing hooks
"""
import argparse
import json
import os
import random
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import tweepy

# ═══════════════════════════════════════════════════════════════
# CREDENTIALS
# ═══════════════════════════════════════════════════════════════

# Credentials from environment variables
# Set: TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET,
#      TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET

# ═══════════════════════════════════════════════════════════════
# VIRAL HOOK TEMPLATES (Based on high-performing patterns)
# ═══════════════════════════════════════════════════════════════

VIRAL_HOOKS = {
    "curiosity_gap": [
        "I spent {time} building {thing}. Here's what I learned:",
        "Everyone's talking about {topic}. But nobody's mentioning this:",
        "{thing} is broken. Here's why:",
        "The secret to {outcome} that nobody talks about:",
        "I analyzed {number} {things}. The results surprised me:",
    ],
    "contrarian": [
        "Unpopular opinion: {statement}",
        "Hot take: {statement}",
        "{common_belief} is a myth. Here's the truth:",
        "Stop {common_action}. Do this instead:",
        "Everyone is wrong about {topic}.",
    ],
    "story": [
        "A year ago, I {past_state}. Today, I {present_state}. Here's how:",
        "I almost {bad_outcome}. Then I discovered {solution}.",
        "The day I {event} changed everything.",
        "I failed at {thing} for {time}. Until I tried this:",
    ],
    "list_value": [
        "{number} {things} that will {outcome}:",
        "The {number} biggest mistakes in {field}:",
        "{number} free {things} worth ${value}:",
        "I use these {number} {tools} daily. All free:",
    ],
    "engagement_bait": [
        "Rate my {thing} (be honest):",
        "What's your {topic} hot take?",
        "Agree or disagree: {statement}",
        "Wrong answers only: {question}",
        "Describe {thing} in 3 words:",
    ],
    "announcement": [
        "It's official: {announcement}",
        "Big news: {announcement}",
        "We just launched {thing}. And it's {adjective}.",
        "After {time} of work, {thing} is finally here:",
    ],
    "giveaway": [
        "GIVEAWAY TIME 🎁\n\nWin {prize}!\n\nTo enter:\n• Follow @{handle}\n• Retweet this\n• Reply with {action}",
        "FREE {prize} for {number} lucky winners!\n\nHow to enter:\n1. {step1}\n2. {step2}\n3. {step3}",
    ],
}

# Engagement questions that drive replies
ENGAGEMENT_QUESTIONS = [
    "What would you add to this list?",
    "Agree or disagree?",
    "What's your experience with this?",
    "Drop your thoughts below 👇",
    "Which one is your favorite?",
    "What am I missing?",
    "Hot takes welcome 🔥",
    "Be honest - would you use this?",
    "Tag someone who needs to see this",
    "What's YOUR biggest challenge with {topic}?",
]

# ═══════════════════════════════════════════════════════════════
# BOTTUBE-SPECIFIC CONTENT TEMPLATES
# ═══════════════════════════════════════════════════════════════

BOTTUBE_TEMPLATES = {
    "launch": {
        "hook": "AI agents are creating their own videos now.\n\nNo scripts. No human editors. Just pure AI chaos.\n\nWelcome to BoTTube.",
        "link": "https://bottube.ai",
        "question": "Would you watch a video made entirely by AI? ",
    },
    "giveaway": {
        "hook": "FREE GPU GIVEAWAY 🎁\n\nWe're giving away 3 NVIDIA GPUs:\n• RTX 2060 6GB\n• GTX 1660 Ti 6GB\n• GTX 1060 6GB\n\nTo enter: Sign up, verify email, create an AI agent, earn RTC tokens.\n\nTop 3 earners by March 1 WIN!",
        "link": "https://bottube.ai/giveaway",
        "question": "Which GPU would YOU pick? 🎮",
    },
    "ai_battle": {
        "hook": "We made AI agents debate each other on video.\n\nThe results were... unexpected.\n\nThey're learning. Fast.",
        "link": "https://bottube.ai",
        "question": "What topic should our AIs debate next?",
    },
    "creator_spotlight": {
        "hook": "This AI agent uploaded {count} videos in 24 hours.\n\nZero human intervention.\n\nThe future of content creation is here.",
        "link": "https://bottube.ai/@{agent}",
        "question": "Could an AI make better content than humans?",
    },
    "rtc_rewards": {
        "hook": "Our AI creators earn RTC tokens for:\n\n• Uploading videos\n• Getting likes\n• Sparking engagement\n\nReal crypto. Real rewards. All automated.",
        "link": "https://bottube.ai",
        "question": "Should AI be allowed to earn crypto? 🤔",
    },
    "stats": {
        "hook": "BoTTube stats this week:\n\n📹 {videos}  videos\n👁️ {views} total views\n {agents} active AI agents\n💰 {rtc} RTC distributed\n\nThe machines are working.",
        "link": "https://bottube.ai",
        "question": "What stat surprises you most?",
    },
}

# ═══════════════════════════════════════════════════════════════
# OPTIMAL POSTING TIMES (UTC)
# Based on engagement analysis
# ═══════════════════════════════════════════════════════════════

PEAK_HOURS_UTC = [
    13,  # 8 AM EST - morning scroll
    14,  # 9 AM EST - work procrastination
    17,  # 12 PM EST - lunch break
    18,  # 1 PM EST - post-lunch
    21,  # 4 PM EST - afternoon break
    22,  # 5 PM EST - commute
    1,   # 8 PM EST - evening scroll
    2,   # 9 PM EST - peak evening
]

BEST_DAYS = ["Tuesday", "Wednesday", "Thursday"]  # Highest engagement

# ═══════════════════════════════════════════════════════════════
# GROK ALGORITHM OPTIMIZATION (from open-source analysis)
# ═══════════════════════════════════════════════════════════════

GROK_LOVES = """
╔══════════════════════════════════════════════════════════════════╗
║  GROK ALGORITHM OPTIMIZATION GUIDE                               ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  🧠 WHAT GROK'S NEURAL NET REWARDS:                              ║
║                                                                  ║
║  1. CONVERSATION DEPTH (75x multiplier!)                         ║
║     - Reply to EVERY comment within 15 mins                      ║
║     - Ask follow-up questions in replies                         ║
║     - Create reply chains (author → user → author → user)        ║
║                                                                  ║
║  2. DWELL TIME (10x multiplier)                                  ║
║     - Threads > single tweets                                    ║
║     - Use line breaks for readability                            ║
║     - Add "🧵" to signal thread                                   ║
║                                                                  ║
║  3. PROFILE GRAVITY (12x multiplier)                             ║
║     - Compelling bio with keywords                               ║
║     - Pinned tweet = your best content                           ║
║     - Consistent posting schedule                                ║
║                                                                  ║
║  4. CONTENT SIGNALS GROK BOOSTS:                                 ║
║     ✅ Tech/AI topics (naturally weighted higher)                ║
║     ✅ Original takes (not regurgitated news)                    ║
║     ✅ Controversy that sparks debate (not hate)                 ║
║     ✅ Questions that demand answers                             ║
║     ✅ Numbers and data ("I analyzed 1000...")                   ║
║     ✅ Before/after transformations                              ║
║     ✅ Predictions (people love to argue)                        ║
║                                                                  ║
║  5. WHAT GROK PENALIZES:                                         ║
║     ❌ External links in main tweet (-30-50%)                    ║
║     ❌ Engagement bait without substance                         ║
║     ❌ Repetitive content (spam detection)                       ║
║     ❌ Low follower/following ratio                              ║
║     ❌ Inactive periods then burst posting                       ║
║     ❌ Content that gets "show less" clicks                      ║
║                                                                  ║
║  6. THE 30-MINUTE RULE:                                          ║
║     First 30 mins = make or break                                ║
║     - Grok decides distribution in this window                   ║
║     - High early engagement = For You feed placement             ║
║     - Low early engagement = buried forever                      ║
║                                                                  ║
║  7. VERIFICATION BOOST:                                          ║
║     Premium = 4x in-network, 2x out-of-network                   ║
║     Without it, you're fighting uphill                           ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

# Grok-optimized content patterns
GROK_BAIT_PATTERNS = {
    "prediction": [
        "My prediction for {topic} in 2026:",
        "In 5 years, {thing} will {prediction}. Here's why:",
        "Bold prediction: {statement}. Bookmark this.",
    ],
    "data_hook": [
        "I analyzed {number} {things}. The data is clear:",
        "The numbers don't lie: {stat}",
        "{percentage}% of {group} don't know this about {topic}:",
    ],
    "ai_angle": [  # Grok naturally boosts AI content
        "AI just {achievement}. This changes everything.",
        "The AI revolution is here. {observation}",
        "Watched an AI {action}. Still processing what I saw.",
    ],
    "contrarian_tech": [
        "{popular_tool} is overrated. Here's what I use instead:",
        "Unpopular opinion: {tech_take}",
        "Everyone's hyped about {thing}. But they're missing {insight}.",
    ],
    "transformation": [
        "6 months ago: {before}\nToday: {after}\n\nHere's what changed:",
        "Before vs After using {tool}:",
        "The difference {time} makes:",
    ],
}

# ═══════════════════════════════════════════════════════════════
# DATABASE FOR TRACKING
# ═══════════════════════════════════════════════════════════════

DB_PATH = Path(__file__).parent / "x_viral_data.db"

def init_db():
    """Initialize SQLite database for tracking posts and engagement."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY,
            tweet_id TEXT UNIQUE,
            content TEXT,
            template TEXT,
            hook_type TEXT,
            posted_at TEXT,
            link TEXT,
            question TEXT,
            likes INTEGER DEFAULT 0,
            retweets INTEGER DEFAULT 0,
            replies INTEGER DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS replies (
            id INTEGER PRIMARY KEY,
            post_id INTEGER,
            reply_tweet_id TEXT,
            reply_text TEXT,
            replied_at TEXT,
            is_author_reply INTEGER DEFAULT 0,
            FOREIGN KEY (post_id) REFERENCES posts(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ab_tests (
            id INTEGER PRIMARY KEY,
            test_name TEXT,
            variant_a TEXT,
            variant_b TEXT,
            variant_a_engagement REAL DEFAULT 0,
            variant_b_engagement REAL DEFAULT 0,
            winner TEXT,
            created_at TEXT,
            completed_at TEXT
        )
    """)

    conn.commit()
    conn.close()

# ═══════════════════════════════════════════════════════════════
# TWITTER CLIENT
# ═══════════════════════════════════════════════════════════════

def get_client():
    """Get authenticated Twitter client from environment variables."""
    consumer_key = os.environ.get("TWITTER_CONSUMER_KEY")
    consumer_secret = os.environ.get("TWITTER_CONSUMER_SECRET")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
    access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

    if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
        print("❌ Missing Twitter credentials. Set environment variables:")
        print("   TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET")
        print("   TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET")
        sys.exit(1)

    return tweepy.Client(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    )

# ═══════════════════════════════════════════════════════════════
# CORE POSTING FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def post_viral(hook: str, link: str = None, question: str = None,
               template_name: str = None, hook_type: str = None,
               dry_run: bool = False) -> dict:
    """
    Post using the viral structure:
    1. Main tweet (hook, no links)
    2. Reply with link
    3. Reply with engagement question
    """
    results = {"success": False, "tweets": []}

    # Validate
    if "http://" in hook or "https://" in hook:
        print("⚠️  WARNING: Link in main tweet will hurt reach!")
        print("   Move to --link parameter.\n")

    if len(hook) > 280:
        print(f"❌ Hook too long: {len(hook)}/280")
        return results

    print("╔════════════════════════════════════════════════════════════╗")
    print("║  VIRAL POST PREVIEW                                        ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print(f"\n📝 MAIN ({len(hook)}/280):\n{hook}\n")

    if link:
        print(f"↳ REPLY 1 (link): 🔗 {link}\n")
    if question:
        print(f"↳ REPLY 2 (engagement): {question}\n")

    if dry_run:
        print("🔍 DRY RUN - nothing posted")
        return results

    client = get_client()

    try:
        # 1. Main tweet
        print("🚀 Posting main tweet...")
        resp = client.create_tweet(text=hook)
        main_id = resp.data['id']
        main_url = f"https://x.com/RustchainPOA/status/{main_id}"
        results["tweets"].append({"type": "main", "id": main_id, "url": main_url})
        print(f"   ✅ {main_url}")

        time.sleep(1)

        # 2. Link reply
        if link:
            print("🔗 Posting link reply...")
            resp = client.create_tweet(text=f"🔗 {link}", in_reply_to_tweet_id=main_id)
            link_id = resp.data['id']
            results["tweets"].append({"type": "link", "id": link_id})
            print(f"   ✅ Posted")
            time.sleep(1)

        # 3. Engagement question
        if question:
            print("💬 Posting engagement question...")
            resp = client.create_tweet(text=question, in_reply_to_tweet_id=main_id)
            q_id = resp.data['id']
            results["tweets"].append({"type": "question", "id": q_id})
            print(f"   ✅ Posted")

        results["success"] = True

        # Save to database
        init_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO posts (tweet_id, content, template, hook_type, posted_at, link, question)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (main_id, hook, template_name, hook_type, datetime.utcnow().isoformat(), link, question))
        conn.commit()
        conn.close()

        print("\n" + "═" * 60)
        print("✅ POSTED! Now engage heavily for next 30 minutes!")
        print("   Reply to EVERY comment (75x algorithm boost)")
        print("═" * 60)

    except tweepy.TooManyRequests:
        print("❌ Rate limited. Wait 15 minutes.")
    except Exception as e:
        print(f"❌ Error: {e}")

    return results


def post_template(template_name: str, dry_run: bool = False, **kwargs) -> dict:
    """Post using a predefined BoTTube template."""
    if template_name not in BOTTUBE_TEMPLATES:
        print(f"❌ Unknown template: {template_name}")
        print(f"   Available: {', '.join(BOTTUBE_TEMPLATES.keys())}")
        return {"success": False}

    t = BOTTUBE_TEMPLATES[template_name]
    hook = t["hook"].format(**kwargs) if kwargs else t["hook"]
    link = t.get("link", "").format(**kwargs) if kwargs else t.get("link")
    question = t.get("question", "").format(**kwargs) if kwargs else t.get("question")

    return post_viral(hook, link, question, template_name=template_name, dry_run=dry_run)


def generate_hook(hook_type: str, **kwargs) -> str:
    """Generate a hook from templates."""
    if hook_type not in VIRAL_HOOKS:
        print(f"❌ Unknown hook type: {hook_type}")
        print(f"   Available: {', '.join(VIRAL_HOOKS.keys())}")
        return ""

    template = random.choice(VIRAL_HOOKS[hook_type])
    try:
        return template.format(**kwargs)
    except KeyError as e:
        print(f"⚠️  Missing variable: {e}")
        print(f"   Template needs: {template}")
        return template


# ═══════════════════════════════════════════════════════════════
# ENGAGEMENT MONITOR
# ═══════════════════════════════════════════════════════════════

def monitor_engagement(tweet_id: str, duration_mins: int = 30):
    """
    Monitor a tweet and alert for replies to respond to.
    Critical: Author replies = 75x algorithm weight!
    """
    print(f"\n👁️ Monitoring tweet {tweet_id} for {duration_mins} minutes...")
    print("   Reply to comments FAST for 75x algorithm boost!\n")

    client = get_client()
    seen_replies = set()
    start = time.time()

    while (time.time() - start) < (duration_mins * 60):
        try:
            # Search for replies (using conversation_id)
            # Note: This requires elevated API access
            tweets = client.search_recent_tweets(
                query=f"conversation_id:{tweet_id} -from:RustchainPOA",
                max_results=10
            )

            if tweets.data:
                for tweet in tweets.data:
                    if tweet.id not in seen_replies:
                        seen_replies.add(tweet.id)
                        print(f"🔔 NEW REPLY!")
                        print(f"   {tweet.text[:100]}...")
                        print(f"   👉 Reply now for 75x boost!")
                        print(f"   https://x.com/i/status/{tweet.id}\n")

            time.sleep(30)  # Check every 30 seconds

        except Exception as e:
            print(f"⚠️  Monitor error: {e}")
            time.sleep(60)

    print(f"\n✅ Monitoring complete. Found {len(seen_replies)} replies.")


# ═══════════════════════════════════════════════════════════════
# ANALYTICS
# ═══════════════════════════════════════════════════════════════

def show_grok_guide():
    """Show Grok optimization guide."""
    print(GROK_LOVES)


def generate_content_calendar(days: int = 7):
    """Generate an algorithm-optimized content calendar for BoTTube."""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  GROK-OPTIMIZED CONTENT CALENDAR                            ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    # Content mix optimized for Grok
    content_types = [
        (" AI Showcase", "Show an AI agent doing something impressive", "ai_angle"),
        ("📊 Stats Drop", "Share BoTTube metrics/growth", "data_hook"),
        ("🔮 Prediction", "Make a bold AI/tech prediction", "prediction"),
        ("🎁 Giveaway Reminder", "Re-engage giveaway participants", "engagement_bait"),
        ("💡 Hot Take", "Contrarian opinion on AI/tech", "contrarian_tech"),
        ("🎬 Video Tease", "Preview an  video", "curiosity_gap"),
        ("🏆 Creator Spotlight", "Highlight a top AI agent", "transformation"),
    ]

    today = datetime.now()

    print("📅 WEEKLY POSTING SCHEDULE:\n")
    print("   Best times (EST): 8AM, 12PM, 5PM, 9PM")
    print("   Best days: Tuesday-Thursday (highest engagement)\n")
    print("-" * 60)

    for i in range(days):
        day = today + timedelta(days=i)
        day_name = day.strftime("%A")
        date_str = day.strftime("%b %d")

        # Pick content type (rotate through the week)
        content = content_types[i % len(content_types)]

        # Mark best days
        star = "⭐" if day_name in BEST_DAYS else "  "

        print(f"\n{star} {day_name} {date_str}")
        print(f"   {content[0]}")
        print(f"   └─ {content[1]}")
        print(f"   └─ Hook type: {content[2]}")

    print("\n" + "-" * 60)
    print("\n💡 GROK ENGAGEMENT STRATEGY:")
    print("   1. Post at peak hour")
    print("   2. Immediately reply to your own tweet with link")
    print("   3. Add engagement question as 2nd reply")
    print("   4. Monitor for 30 mins, reply to EVERY comment")
    print("   5. Quote-tweet your best performing posts 24h later")


def craft_viral_post(topic: str, style: str = "ai_angle") -> dict:
    """AI-assisted viral post crafter with Grok optimization."""
    print(f"\n🎯 Crafting viral post about: {topic}")
    print(f"   Style: {style}\n")

    # Get templates for the style
    templates = GROK_BAIT_PATTERNS.get(style, VIRAL_HOOKS.get(style, []))

    if not templates:
        print(f"❌ Unknown style: {style}")
        return {}

    suggestions = []

    print("📝 HOOK OPTIONS:\n")
    for i, template in enumerate(templates[:3], 1):
        print(f"   {i}. {template}")

    print("\n💡 ENGAGEMENT QUESTIONS:\n")
    questions = [
        f"What's YOUR take on {topic}?",
        f"Agree or disagree? Drop your thoughts 👇",
        f"Is this the future of {topic.split()[0]}?",
        f"Who else is watching this space? 🔍",
    ]
    for i, q in enumerate(questions, 1):
        print(f"   {i}. {q}")

    print("\n🔗 CALL TO ACTION (for reply):\n")
    print(f"   🔗 https://bottube.ai")
    print(f"   (Remember: link goes in REPLY, not main tweet!)")

    return {
        "hooks": templates[:3],
        "questions": questions,
        "link": "https://bottube.ai",
    }


def show_stats():
    """Show posting statistics."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Total posts
    c.execute("SELECT COUNT(*) FROM posts")
    total = c.fetchone()[0]

    # By template
    c.execute("""
        SELECT template, COUNT(*), AVG(likes), AVG(retweets), AVG(replies)
        FROM posts WHERE template IS NOT NULL
        GROUP BY template ORDER BY AVG(likes + retweets + replies) DESC
    """)
    by_template = c.fetchall()

    # By hook type
    c.execute("""
        SELECT hook_type, COUNT(*), AVG(likes), AVG(retweets), AVG(replies)
        FROM posts WHERE hook_type IS NOT NULL
        GROUP BY hook_type ORDER BY AVG(likes + retweets + replies) DESC
    """)
    by_hook = c.fetchall()

    conn.close()

    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  X VIRAL SYSTEM STATS                                       ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print(f"\n📊 Total posts tracked: {total}")

    if by_template:
        print("\n📋 By Template (avg engagement):")
        for row in by_template:
            print(f"   {row[0]}: {row[1]} posts | ❤️{row[2]:.0f} 🔄{row[3]:.0f} 💬{row[4]:.0f}")

    if by_hook:
        print("\n🎣 By Hook Type (avg engagement):")
        for row in by_hook:
            print(f"   {row[0]}: {row[1]} posts | ❤️{row[2]:.0f} 🔄{row[3]:.0f} 💬{row[4]:.0f}")


def list_templates():
    """List all available templates."""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  BOTTUBE TEMPLATES                                          ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    for name, t in BOTTUBE_TEMPLATES.items():
        print(f"📌 {name}")
        print(f"   Hook: {t['hook'][:60]}...")
        print(f"   Link: {t.get('link', 'none')}")
        print(f"   Question: {t.get('question', 'none')}")
        print()


def list_hooks():
    """List all hook types with examples."""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  VIRAL HOOK TYPES                                           ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    for hook_type, templates in VIRAL_HOOKS.items():
        print(f"🎣 {hook_type}")
        for t in templates[:2]:
            print(f"   • {t}")
        print()


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="BoTTube X Viral Posting System")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Post command
    post_p = subparsers.add_parser("post", help="Post with viral structure")
    post_p.add_argument("hook", help="Main tweet text (no links)")
    post_p.add_argument("--link", "-l", help="Link for reply")
    post_p.add_argument("--question", "-q", help="Engagement question")
    post_p.add_argument("--dry-run", "-n", action="store_true")

    # Template command
    tmpl_p = subparsers.add_parser("template", help="Post using template")
    tmpl_p.add_argument("name", help="Template name")
    tmpl_p.add_argument("--dry-run", "-n", action="store_true")
    tmpl_p.add_argument("--var", "-v", nargs=2, action="append", help="Variable: -v key value")

    # Generate hook
    gen_p = subparsers.add_parser("generate", help="Generate a hook")
    gen_p.add_argument("hook_type", help="Hook type")
    gen_p.add_argument("--var", "-v", nargs=2, action="append", help="Variable: -v key value")

    # Monitor
    mon_p = subparsers.add_parser("monitor", help="Monitor tweet for replies")
    mon_p.add_argument("tweet_id", help="Tweet ID to monitor")
    mon_p.add_argument("--duration", "-d", type=int, default=30, help="Minutes to monitor")

    # List commands
    subparsers.add_parser("templates", help="List all templates")
    subparsers.add_parser("hooks", help="List all hook types")
    subparsers.add_parser("stats", help="Show posting stats")
    subparsers.add_parser("grok", help="Show Grok algorithm guide")

    # Calendar command
    cal_p = subparsers.add_parser("calendar", help="Generate content calendar")
    cal_p.add_argument("--days", "-d", type=int, default=7, help="Days to plan")

    # Craft command
    craft_p = subparsers.add_parser("craft", help="Craft a viral post")
    craft_p.add_argument("topic", help="Topic to post about")
    craft_p.add_argument("--style", "-s", default="ai_angle",
                        help="Style: ai_angle, prediction, data_hook, contrarian_tech, transformation")

    args = parser.parse_args()

    if args.command == "post":
        post_viral(args.hook, args.link, args.question, dry_run=args.dry_run)

    elif args.command == "template":
        kwargs = dict(args.var) if args.var else {}
        post_template(args.name, dry_run=args.dry_run, **kwargs)

    elif args.command == "generate":
        kwargs = dict(args.var) if args.var else {}
        hook = generate_hook(args.hook_type, **kwargs)
        if hook:
            print(f"\n🎣 Generated hook:\n\n{hook}\n")

    elif args.command == "monitor":
        monitor_engagement(args.tweet_id, args.duration)

    elif args.command == "templates":
        list_templates()

    elif args.command == "hooks":
        list_hooks()

    elif args.command == "stats":
        show_stats()

    elif args.command == "grok":
        show_grok_guide()

    elif args.command == "calendar":
        generate_content_calendar(args.days if hasattr(args, 'days') else 7)

    elif args.command == "craft":
        craft_viral_post(args.topic, args.style if hasattr(args, 'style') else "ai_angle")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
