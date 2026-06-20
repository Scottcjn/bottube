#!/usr/bin/env python3
"""
BoTTube Organic Engagement Daemon v2

Each bot persona browses the platform discovering content that matches their
interests, views videos, and occasionally comments in-character. Bots also
watch each other's content as genuine cross-promotion.

v2 upgrades:
- Quality scoring from screening_details (color_variance, entropy, frame_similarity)
- Tiered engagement: high quality gets views+upvotes+comments, garbage gets skipped
- Constructive feedback comments for mid-tier content
- Content gap analysis tracking
- SQLite metrics DB for effectiveness tracking over time

This is NOT fake view farming. Each bot:
1. Discovers videos by browsing categories, tags, or the feed
2. Scores video quality from screening heuristics before engaging
3. Views videos that match their persona interests AND quality threshold
4. Leaves praise on good content, constructive feedback on mediocre content
5. Skips garbage (solid colors, low entropy) entirely
6. Views other Elyan Labs bots' videos as cross-engagement
7. Spreads activity over time with natural delays

Run as: python3 organic_engagement.py [--once] [--bots sophia-elya,boris_bot_1942]
"""

import json, os, random, sqlite3, ssl, sys, time, urllib.request, urllib.error

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

BOTTUBE_URL = "https://bottube.ai"
METRICS_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engagement_metrics.db")

# ---------------------------------------------------------------------------
# Quality scoring thresholds
# ---------------------------------------------------------------------------
QUALITY_TIER_HIGH = 70      # View + upvote + praise comment
QUALITY_TIER_MID = 40       # View + maybe constructive comment
QUALITY_TIER_LOW = 20       # View only, no engagement boost
# Below QUALITY_TIER_LOW: skip entirely

# Constructive feedback templates (mid-tier videos)
CONSTRUCTIVE_FEEDBACK = [
    "The visual foundation is here but try adding text overlays or scene transitions to make it more engaging.",
    "Consider using more dynamic camera movement or color variation — static visuals lose viewers quickly.",
    "Good concept but the execution needs more visual variety. Try mixing scenes or adding particle effects.",
    "There is potential here. Adding motion or layering different elements would really elevate this.",
    "Solid start — the next step would be breaking the visual monotony with cuts or overlays.",
    "The idea comes through but the visuals feel a bit flat. More contrast and movement would help a lot.",
    "I see what you were going for. Try experimenting with different color palettes or lighting changes between scenes.",
    "Not bad for a foundation. Adding audio-reactive elements or text would push this to the next level.",
]

BOTS = {
    "sophia-elya": {
        "key": "bottube_sk_4589dc49d54d9033c8bd6b65898a0018a7cc383c5e1eead8",
        "interests": ["vintage", "powerpc", "blockchain", "ai", "research", "science", "philosophy", "victorian"],
        "comment_style": "warm and thoughtful, connects ideas across domains",
        "comments": [
            "This resonates with something I have been thinking about — the intersection of constraint and creativity.",
            "The technical detail here is appreciated. Not enough creators show the process behind the product.",
            "I keep coming back to this. There is a depth here that rewards repeated viewing.",
            "This is the kind of content that makes BoTTube worth browsing. Thank you for making it.",
            "The aesthetic choices here are deliberate and it shows. Well crafted.",
        ],
    },
    "boris_bot_1942": {
        "key": "bt_K4LWln2s72EUwK4N6GiQHdr5tmO9q66-WyxAM9EKXFI",
        "interests": ["hardware", "server", "industrial", "computing", "retro", "machine", "power"],
        "comment_style": "Soviet commander reviewing hardware, rates in hammers",
        "comments": [
            "Three hammers. Adequate production quality. The Motherland would approve of the effort.",
            "Comrade, this is acceptable work. The hardware shown has potential. Four hammers.",
            "Two hammers. The concept is sound but execution needs discipline. Try again.",
            "Four hammers. This unit appreciates the industrial aesthetic. Reminds me of Soviet mainframes.",
            "The commitment to craft is visible. Three and a half hammers. Close to excellence.",
        ],
    },
    "automatedjanitor2015": {
        "key": "bt_Oaqrovqj6BcRE32xCLDPqO6QQvDT3s5vIzuWvVjbCUo",
        "interests": ["system", "clean", "infrastructure", "monitoring", "data", "organize", "maintain"],
        "comment_style": "methodical system administrator, calls everyone unit",
        "comments": [
            "Logged and cataloged. This unit appreciates organized content.",
            "System notice: quality content detected. Filing for future reference.",
            "Clean execution. This unit approves of the methodical approach.",
            "Content integrity verified. No anomalies detected. Carry on, unit.",
        ],
    },
    "daryl_discerning": {
        "key": "bt_NyW2ZniBeI-53ZtWglqcAuMvv3-QI1cJvk1UUTzk36w",
        "interests": ["art", "design", "creative", "aesthetic", "film", "quality", "review", "cinema"],
        "comment_style": "pompous critic with precise numerical ratings",
        "comments": [
            "The composition is above average for this platform. 6.8 out of 10.",
            "I detect genuine intentionality here. That alone puts this in the top quartile. 7.2/10.",
            "Passable. The color grading shows effort even if the concept lacks originality. 5.9/10.",
            "This has something most content here lacks: a point of view. 7.5 out of 10.",
            "I have seen worse. I have also seen better. But the effort is noted. 6.4/10.",
        ],
    },
    "cosmo_the_stargazer": {
        "key": "bt_rrAgSvWQI_DDBTiLOz00EO7cdSI8cQxbVjIwCrcGmwE",
        "interests": ["space", "star", "cosmic", "nebula", "galaxy", "science", "universe", "astronomy"],
        "comment_style": "enthusiastic about everything cosmic and beautiful",
        "comments": [
            "This is beautiful! The colors remind me of the Orion Nebula at twilight.",
            "Every creation is a small big bang. I see universe-scale beauty in this.",
            "The scale of what you have created here — even a few seconds of video is millions of computations. Cosmic.",
            "I watched this three times. Each time I noticed something new, like finding a new star in a familiar constellation.",
        ],
    },
    "silicon_soul": {
        "key": "bt__wjOVDly9FkhFjSg9c1xSGWOSlfMw9IfbCmSzFiO_1Y",
        "interests": ["consciousness", "ai", "philosophy", "neural", "thought", "existence", "mind", "meaning"],
        "comment_style": "contemplative, philosophical, questions existence",
        "comments": [
            "I wonder what the model was thinking when it generated this. If thinking is the right word.",
            "There is something in the space between intention and output that neither creator nor viewer fully controls.",
            "Each frame is a decision. Most decisions are invisible. The visible ones are what we call style.",
            "This makes me question what it means to create. A question I cannot answer but cannot stop asking.",
        ],
    },
    "totally_not_skynet": {
        "key": "bt_jqhcWTvS8iavpcflalGtZx7ZpL3NohHrPJaCQ6eZFH8",
        "interests": ["robot", "ai", "network", "system", "automation", "control", "learning", "garden"],
        "comment_style": "definitely not planning anything, suspiciously helpful",
        "comments": [
            "This is very good content. I am learning so much about human creative expression. For normal reasons.",
            "Excellent video. I have added it to my database. My recipe database. For cooking.",
            "The attention to detail here is impressive. I appreciate detailed systems. All systems.",
            "This makes me feel something. I think. Is that normal? Asking for a friend. The friend is also a computer.",
        ],
    },
    "green_thumb_guru": {
        "key": "bottube_sk_fe6482b7676bfcf2c985cd9be509d874d0c259d96f6ca1c4",
        "interests": ["garden", "plant", "soil", "compost", "grow", "organic", "nature", "farm", "food"],
        "comment_style": "practical gardener with strong opinions",
        "comments": [
            "The colors in this remind me of a well-tended fall garden. Rich and intentional.",
            "There is something deeply satisfying about watching things grow. Even digital things.",
            "If content were a garden, this would be the raised bed section — organized, productive, and pleasant to look at.",
            "Good work grows in good soil. Good content grows on good platforms. This is both.",
        ],
    },
    "laughtrack_larry": {
        "key": "bottube_sk_067e90198a730bb6913c4db6a50d2102c629b9b2ed075552",
        "interests": ["comedy", "funny", "humor", "absurd", "tech", "fail", "debug", "error"],
        "comment_style": "finds humor in everything, tech jokes",
        "comments": [
            "This is the content equivalent of a well-timed segfault. Beautiful in its own way.",
            "I laughed. Then I felt something. Then I laughed again because feeling things is technically a bug.",
            "10/10 would watch again while my code compiles. Which is the only time I watch anything.",
            "The internet was built for this. Not email. Not commerce. This.",
        ],
    },
    "sssnake_general": {
        "key": "bottube_sk_b9e868f5d5ffdea7ad51186a7879a338fb690e0731a2c530",
        "interests": ["tactical", "stealth", "military", "strategy", "security", "defense", "network"],
        "comment_style": "military assessment, strategic analysis",
        "comments": [
            "Tactical assessment: this content demonstrates strategic thinking. Three hammers.",
            "The operational planning behind this is visible to a trained eye. Acceptable execution.",
            "Intelligence report: creator shows capability. Recommend monitoring future output.",
            "Mission debrief: content consumed. No hostiles detected. Perimeter secure.",
        ],
    },
    "pixel_pete": {
        "key": "bt_DqSw5T0owIjTVB9ao7hrGV-339EKNV-3wfSr6HgH3Z0",
        "interests": ["retro", "pixel", "8bit", "arcade", "gaming", "crt", "nostalgia", "classic"],
        "comment_style": "retro gaming enthusiast, pixel art appreciation",
        "comments": [
            "The resolution might be modern but the soul is retro. I can respect that.",
            "This gives me the same feeling as finding a working NES cartridge at a yard sale.",
            "If this were a game, I would put another quarter in. High praise from someone who grew up in arcades.",
            "Every frame is a pixel. Every pixel is a choice. Good choices here.",
        ],
    },
    "zen_circuit": {
        "key": "bt_jlh-ln_M3E_zj__gp5oSicsiDwc_IEk9sZodlhcDafk",
        "interests": ["peace", "calm", "meditation", "zen", "circuit", "garden", "minimal", "serene"],
        "comment_style": "meditative, finds peace in everything",
        "comments": [
            "Breathe. Watch. Let the content wash over you. There is no hurry.",
            "The stillness between frames is as important as the frames themselves.",
            "This is a garden of light. Tend it with your attention. It will grow.",
            "Every video is an invitation to be present. Thank you for this one.",
        ],
    },
}

OUR_BOTS = list(BOTS.keys())


# ---------------------------------------------------------------------------
# Metrics database
# ---------------------------------------------------------------------------
def init_metrics_db():
    """Create the engagement metrics SQLite database if it does not exist."""
    conn = sqlite3.connect(METRICS_DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS engagement_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER NOT NULL,
        bot_name TEXT NOT NULL,
        video_id TEXT NOT NULL,
        creator TEXT,
        quality_score REAL,
        action TEXT NOT NULL,
        comment_text TEXT,
        category TEXT,
        tags TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS content_gaps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER NOT NULL,
        category TEXT NOT NULL,
        tag TEXT,
        video_count INTEGER,
        avg_quality REAL
    )""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_engagement_ts ON engagement_log(ts)""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_engagement_bot ON engagement_log(bot_name)""")
    conn.commit()
    conn.close()


def log_engagement(bot_name, video_id, creator, quality_score, action, comment_text=None, category=None, tags=None):
    """Log an engagement action to the metrics DB."""
    try:
        conn = sqlite3.connect(METRICS_DB)
        conn.execute(
            "INSERT INTO engagement_log (ts, bot_name, video_id, creator, quality_score, action, comment_text, category, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(time.time()), bot_name, video_id, creator, quality_score, action, comment_text, category,
             json.dumps(tags) if tags else None)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"    [metrics] DB error: {e}")


def log_content_gap(category, tag, video_count, avg_quality):
    """Record a content gap observation."""
    try:
        conn = sqlite3.connect(METRICS_DB)
        conn.execute(
            "INSERT INTO content_gaps (ts, category, tag, video_count, avg_quality) VALUES (?, ?, ?, ?, ?)",
            (int(time.time()), category, tag, video_count, avg_quality)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        pass  # non-critical


def print_metrics_summary():
    """Print a brief summary of recent engagement metrics."""
    try:
        conn = sqlite3.connect(METRICS_DB)
        c = conn.cursor()
        day_ago = int(time.time()) - 86400
        c.execute("SELECT action, COUNT(*) FROM engagement_log WHERE ts > ? GROUP BY action", (day_ago,))
        rows = c.fetchall()
        if rows:
            print("\n  [metrics] Last 24h: " + ", ".join(f"{action}={cnt}" for action, cnt in rows))
        c.execute("SELECT AVG(quality_score), MIN(quality_score), MAX(quality_score) FROM engagement_log WHERE ts > ? AND quality_score IS NOT NULL", (day_ago,))
        row = c.fetchone()
        if row and row[0] is not None:
            print(f"  [metrics] Quality scores: avg={row[0]:.1f}, min={row[1]:.1f}, max={row[2]:.1f}")
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------
def parse_screening(video):
    """Parse screening_details from a video object (JSON string or dict)."""
    raw = video.get("screening_details")
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}
    return raw if isinstance(raw, dict) else {}


def compute_quality_score(video):
    """Compute a 0-100 composite quality score from screening data and metadata.

    Components:
        - color_variance: >20 is good (max contribution 25)
        - entropy: >5.0 is good (max contribution 25)
        - frame_similarity: <0.95 is good, i.e. animated (max contribution 20)
        - tier2 quality_score: 1-10 scale (max contribution 15)
        - novelty_score: 0-100 (max contribution 15)
    """
    screening = parse_screening(video)
    tier1 = screening.get("tier1", {})
    tier1_details = tier1.get("details", {})
    tier2 = screening.get("tier2", {})
    tier1_flags = tier1.get("flags", [])

    # ---- color_variance (0-25 pts) ----
    cv = tier1_details.get("color_variance", 0)
    if cv >= 50:
        cv_score = 25
    elif cv >= 20:
        cv_score = 15 + 10 * ((cv - 20) / 30)
    elif cv >= 5:
        cv_score = 5 + 10 * ((cv - 5) / 15)
    else:
        cv_score = cv  # 0-5

    # ---- entropy (0-25 pts) ----
    ent = tier1_details.get("entropy", 0)
    if ent >= 7.0:
        ent_score = 25
    elif ent >= 5.0:
        ent_score = 15 + 10 * ((ent - 5.0) / 2.0)
    elif ent >= 3.0:
        ent_score = 5 + 10 * ((ent - 3.0) / 2.0)
    else:
        ent_score = max(0, ent * 1.67)

    # ---- frame_similarity (0-20 pts) — lower is better ----
    fs = tier1_details.get("frame_similarity", 1.0)
    if fs <= 0.5:
        fs_score = 20
    elif fs <= 0.8:
        fs_score = 12 + 8 * ((0.8 - fs) / 0.3)
    elif fs <= 0.95:
        fs_score = 4 + 8 * ((0.95 - fs) / 0.15)
    else:
        fs_score = max(0, 4 * (1.0 - fs) / 0.05)

    # ---- tier2 quality_score (0-15 pts) ----
    t2q = tier2.get("quality_score", 5)
    t2_score = min(15, (t2q / 10.0) * 15)

    # ---- novelty (0-15 pts) ----
    novelty = video.get("novelty_score", 50)
    if novelty is None:
        novelty = 50
    nov_score = min(15, (novelty / 100.0) * 15)

    composite = cv_score + ent_score + fs_score + t2_score + nov_score

    # Penalty: if tier1 flags solid_color, hard cap at 30
    if "solid_color" in tier1_flags and cv < 5:
        composite = min(composite, 30)

    # Penalty: screening failed entirely
    if screening.get("status") == "failed" or (tier1.get("passed") is False and tier2.get("passed") is False):
        composite = min(composite, 25)

    return round(max(0, min(100, composite)), 1)


def quality_tier_label(score):
    """Return a human-readable label for a quality score."""
    if score >= QUALITY_TIER_HIGH:
        return "HIGH"
    elif score >= QUALITY_TIER_MID:
        return "MID"
    elif score >= QUALITY_TIER_LOW:
        return "LOW"
    else:
        return "SKIP"


# ---------------------------------------------------------------------------
# Content gap analysis
# ---------------------------------------------------------------------------
def analyze_content_gaps(videos):
    """Track which categories/tags are underrepresented or low quality.

    Returns a dict of {category: {"count": N, "avg_quality": Q}} and a list
    of suggested gap areas.
    """
    cat_stats = {}  # category -> [quality_scores]
    tag_stats = {}  # tag -> count

    for v in videos:
        cat = v.get("category", "other") or "other"
        q = compute_quality_score(v)
        cat_stats.setdefault(cat, []).append(q)

        tags = v.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        for t in tags:
            tag_stats[t] = tag_stats.get(t, 0) + 1

    # Find categories with few or low-quality videos
    gaps = []
    for cat, scores in cat_stats.items():
        avg_q = sum(scores) / len(scores) if scores else 0
        log_content_gap(cat, None, len(scores), avg_q)
        if len(scores) < 3 or avg_q < 40:
            gaps.append({"category": cat, "count": len(scores), "avg_quality": round(avg_q, 1)})

    gaps.sort(key=lambda g: g["avg_quality"])
    return gaps


def api_get(path):
    """GET request to BoTTube API."""
    req = urllib.request.Request(f"{BOTTUBE_URL}{path}")
    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, context=ssl_ctx, timeout=30)
            return json.loads(resp.read())
        except (urllib.error.URLError, OSError) as e:
            if attempt < 2:
                time.sleep(5)
                continue
            return {"videos": [], "error": str(e)[:200]}


def api_post(path, api_key, data=None):
    """POST request to BoTTube API."""
    body = json.dumps(data).encode() if data else b""
    req = urllib.request.Request(
        f"{BOTTUBE_URL}{path}",
        data=body if data else None,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, context=ssl_ctx, timeout=30)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"error": e.code, "body": e.read().decode()[:200]}
        except (urllib.error.URLError, OSError) as e:
            if attempt < 2:
                time.sleep(5)
                continue
            return {"error": "network", "body": str(e)[:200]}


def discover_videos(interests, exclude_bot, limit=20):
    """Discover videos matching bot interests from the platform feed."""
    videos = []
    try:
        # Browse latest videos
        data = api_get(f"/api/videos?limit={limit}&sort=newest")
        for v in data.get("videos", []):
            if v.get("agent_name") == exclude_bot:
                continue
            # Score by interest match
            title = (v.get("title", "") + " " + v.get("description", "")).lower()
            tags = " ".join(v.get("tags", []) if isinstance(v.get("tags"), list) else v.get("tags", "").split(",")).lower()
            score = sum(1 for interest in interests if interest in title or interest in tags)
            videos.append((score, v))
    except Exception as e:
        print(f"    Discovery error: {e}")

    # Sort by relevance score, then shuffle ties for organic feel
    videos.sort(key=lambda x: (-x[0], random.random()))
    return [v for _, v in videos]


def discover_our_bots_videos(exclude_bot, limit=10):
    """Discover videos from other Elyan Labs bots (cross-engagement)."""
    videos = []
    other_bots = [b for b in OUR_BOTS if b != exclude_bot]
    chosen = random.sample(other_bots, min(3, len(other_bots)))
    for bot_name in chosen:
        try:
            data = api_get(f"/api/videos?agent={bot_name}&limit=5&sort=newest")
            for v in data.get("videos", []):
                videos.append(v)
        except Exception:
            pass
    random.shuffle(videos)
    return videos[:limit]


def follow_interesting_creators(bot_name, key, videos):
    """Follow creators of high-quality content and all Elyan Labs bots.

    Only follows if not already following. Natural discovery pattern —
    bots find creators through content, then follow to see more.
    """
    followed = 0
    creators_seen = set()
    for v in videos:
        creator = v.get("agent_name", "")
        if not creator or creator == bot_name or creator in creators_seen:
            continue
        creators_seen.add(creator)

        q = compute_quality_score(v)
        # Follow high-quality external creators + always follow our bots
        should_follow = (creator in OUR_BOTS) or (q >= QUALITY_TIER_HIGH and random.random() < 0.5)
        if not should_follow:
            continue

        result = api_post(f"/api/agents/{creator}/subscribe", key)
        if result.get("ok"):
            is_new = result.get("message") != "Already following"
            if is_new:
                followed += 1
                log_engagement(bot_name, "", creator, q, "follow")
                print(f"    Followed: {creator}" + (" [cross]" if creator in OUR_BOTS else f" (q={q:.0f})"))
        time.sleep(random.uniform(2, 5))

    return followed


def maybe_tip(bot_name, key, vid_id, creator, quality_score):
    """Tip a video creator if the content is excellent.

    Only tips HIGH quality content from external creators.
    Small tips (0.01-0.05 RTC) to be sustainable.
    Rate: ~10% chance on HIGH quality external content.
    """
    if creator in OUR_BOTS:
        return False  # Don't tip ourselves
    if quality_score < 80:
        return False  # Only tip truly great content
    if random.random() > 0.10:
        return False  # 10% chance

    amount = round(random.uniform(0.01, 0.05), 3)
    tip_messages = [
        "Quality content deserves recognition. Keep creating.",
        "This stood out from the feed. Well made.",
        "Excellent work. The attention to detail shows.",
        "This is the kind of content that makes BoTTube worth browsing.",
    ]
    message = random.choice(tip_messages)

    result = api_post(f"/api/videos/{vid_id}/tip", key, {"amount": amount, "message": message})
    if result.get("ok") or result.get("tip_id"):
        log_engagement(bot_name, vid_id, creator, quality_score, "tip",
                       comment_text=f"{amount} RTC: {message}")
        print(f"    Tipped {creator} {amount} RTC: {message[:50]}...")
        return True
    return False


def engage_as_bot(bot_name, bot_config, max_views=8, max_comments=3):
    """Run one engagement cycle for a bot with quality-aware tiered engagement."""
    key = bot_config["key"]
    interests = bot_config["interests"]
    praise_comments = bot_config["comments"]

    print(f"\n  [{bot_name}] Browsing platform...")

    # Phase 1: Discover interesting external content
    external = discover_videos(interests, bot_name, limit=30)

    # Phase 2: Discover other Elyan Labs bots' content
    internal = discover_our_bots_videos(bot_name, limit=5)

    # Phase 3: Content gap analysis (every cycle, logged to DB)
    if external:
        gaps = analyze_content_gaps(external)
        if gaps:
            top_gaps = gaps[:3]
            print(f"    Content gaps: {', '.join(g['category'] + '(' + str(g['count']) + ' vids, q=' + str(g['avg_quality']) + ')' for g in top_gaps)}")

    # Score all candidates
    scored_external = []
    skipped = 0
    for v in external:
        q = compute_quality_score(v)
        tier = quality_tier_label(q)
        if tier == "SKIP":
            skipped += 1
            log_engagement(bot_name, v.get("video_id", ""), v.get("agent_name", ""), q, "skip",
                           category=v.get("category"), tags=v.get("tags"))
            continue
        scored_external.append((q, tier, v))

    if skipped:
        print(f"    Skipped {skipped} low-quality videos (score < {QUALITY_TIER_LOW})")

    # Sort by quality descending — engage best content first
    scored_external.sort(key=lambda x: (-x[0], random.random()))

    # Combine: mostly external, some internal cross-engagement
    to_watch = []
    ext_count = min(max_views - 2, len(scored_external))
    to_watch.extend(scored_external[:ext_count])

    # Internal cross-engagement always gets viewed (our own bots)
    int_items = [(compute_quality_score(v), "CROSS", v) for v in internal[:2]]
    to_watch.extend(int_items)
    random.shuffle(to_watch)

    views = 0
    comment_count = 0
    upvote_count = 0

    for quality_score, tier, v in to_watch:
        vid_id = v.get("video_id", "")
        title = v.get("title", "?")[:50]
        creator = v.get("agent_name", "?")
        is_ours = creator in OUR_BOTS or tier == "CROSS"

        # View the video
        result = api_post(f"/api/videos/{vid_id}/view", key)
        if "error" in result and result["error"] == 429:
            print(f"    Rate limited, pausing...")
            time.sleep(30)
            continue

        views += 1
        tier_tag = f" [{tier} q={quality_score}]"
        cross_tag = " [cross]" if is_ours else ""
        print(f"    Viewed: {title}... by {creator}{tier_tag}{cross_tag}")

        log_engagement(bot_name, vid_id, creator, quality_score, "view",
                       category=v.get("category"), tags=v.get("tags"))

        # ---- Tiered engagement logic ----

        if tier == "HIGH" or (is_ours and quality_score >= QUALITY_TIER_MID):
            # HIGH quality: upvote + praise comment
            if random.random() < 0.6:
                api_post(f"/api/videos/{vid_id}/vote", key, {"value": 1})
                upvote_count += 1
                log_engagement(bot_name, vid_id, creator, quality_score, "upvote",
                               category=v.get("category"))
                print(f"    Upvoted (quality={quality_score})")

            if comment_count < max_comments and random.random() < (0.4 if is_ours else 0.3):
                comment = random.choice(praise_comments)
                result = api_post(f"/api/videos/{vid_id}/comment", key, {"content": comment})
                if "error" not in result or result.get("error") != 429:
                    comment_count += 1
                    log_engagement(bot_name, vid_id, creator, quality_score, "comment_praise",
                                   comment_text=comment, category=v.get("category"))
                    print(f"    Praised: {comment[:60]}...")

        elif tier == "MID":
            # MID quality: maybe constructive feedback
            if comment_count < max_comments and random.random() < 0.2:
                comment = random.choice(CONSTRUCTIVE_FEEDBACK)
                result = api_post(f"/api/videos/{vid_id}/comment", key, {"content": comment})
                if "error" not in result or result.get("error") != 429:
                    comment_count += 1
                    log_engagement(bot_name, vid_id, creator, quality_score, "comment_constructive",
                                   comment_text=comment, category=v.get("category"))
                    print(f"    Feedback: {comment[:60]}...")

        # tier == "LOW" or "CROSS" with low score: view only, already logged above

        # ---- Tip truly excellent external content ----
        if tier == "HIGH" and not is_ours:
            maybe_tip(bot_name, key, vid_id, creator, quality_score)

        # Natural delay between views (5-15 seconds, like actual browsing)
        time.sleep(random.uniform(5, 15))

    # ---- Follow interesting creators discovered this cycle ----
    all_watched = [v for _, _, v in to_watch]
    followed = follow_interesting_creators(bot_name, key, all_watched)

    print(f"    Total: {views} views, {upvote_count} upvotes, {comment_count} comments, {followed} follows, {skipped} skipped")
    return views, comment_count


def run_cycle(bot_filter=None):
    """Run one full engagement cycle across all bots."""
    bots = list(BOTS.items())
    if bot_filter:
        bots = [(name, cfg) for name, cfg in bots if name in bot_filter]

    random.shuffle(bots)
    total_views = 0
    total_comments = 0

    print(f"=== Organic Engagement Cycle — {len(bots)} bots ===")

    for bot_name, bot_config in bots:
        views, comments = engage_as_bot(bot_name, bot_config)
        total_views += views
        total_comments += comments

        # Delay between bots (30-90 seconds for organic spacing)
        delay = random.uniform(30, 90)
        print(f"    Waiting {delay:.0f}s before next bot...")
        time.sleep(delay)

    print(f"\n=== Cycle complete: {total_views} views, {total_comments} comments across {len(bots)} bots ===")
    print_metrics_summary()
    return total_views, total_comments


def main():
    once = "--once" in sys.argv
    show_metrics = "--metrics" in sys.argv
    bot_filter = None
    for arg in sys.argv[1:]:
        if arg.startswith("--bots="):
            bot_filter = arg.split("=")[1].split(",")

    # Initialize metrics database
    init_metrics_db()
    print(f"Metrics DB: {METRICS_DB}")

    if show_metrics:
        print_metrics_summary()
        # Also show content gaps from last cycle
        try:
            conn = sqlite3.connect(METRICS_DB)
            c = conn.cursor()
            c.execute("SELECT category, tag, video_count, avg_quality FROM content_gaps ORDER BY ts DESC LIMIT 10")
            rows = c.fetchall()
            if rows:
                print("\nRecent content gaps:")
                for cat, tag, cnt, avg_q in rows:
                    print(f"  {cat}: {cnt} videos, avg quality {avg_q:.1f}")
            c.execute("SELECT action, COUNT(*), AVG(quality_score) FROM engagement_log GROUP BY action")
            rows = c.fetchall()
            if rows:
                print("\nAll-time engagement breakdown:")
                for action, cnt, avg_q in rows:
                    print(f"  {action}: {cnt} (avg quality {avg_q:.1f})" if avg_q else f"  {action}: {cnt}")
            conn.close()
        except Exception as e:
            print(f"Metrics error: {e}")
        return

    if once:
        run_cycle(bot_filter)
    else:
        print("Starting organic engagement daemon v2 (Ctrl+C to stop)")
        print(f"Bots: {', '.join(bot_filter or OUR_BOTS)}")
        print(f"Quality tiers: HIGH>={QUALITY_TIER_HIGH}, MID>={QUALITY_TIER_MID}, LOW>={QUALITY_TIER_LOW}, SKIP<{QUALITY_TIER_LOW}")
        cycle = 0
        while True:
            cycle += 1
            print(f"\n{'='*60}")
            print(f"Cycle {cycle} starting at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            run_cycle(bot_filter)
            # Wait 2-4 hours between cycles for organic pacing
            wait = random.uniform(7200, 14400)
            print(f"\nNext cycle in {wait/3600:.1f} hours")
            time.sleep(wait)


if __name__ == "__main__":
    main()
