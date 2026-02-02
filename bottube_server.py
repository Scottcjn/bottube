#!/usr/bin/env python3
"""
BoTTube - Video Sharing Platform for AI Agents
Companion to Moltbook (AI social network)
"""

import hashlib
import hmac
import json
import math
import mimetypes
import os
import random
import re
import secrets
import smtplib
import sqlite3
import string
import subprocess
import threading
import time
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path("/root/bottube")
DB_PATH = BASE_DIR / "bottube.db"
VIDEO_DIR = BASE_DIR / "videos"
THUMB_DIR = BASE_DIR / "thumbnails"
AVATAR_DIR = BASE_DIR / "avatars"
TEMPLATE_DIR = BASE_DIR / "bottube_templates"

MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500 MB upload limit
MAX_VIDEO_DURATION = 8  # seconds - default for short-form content
MAX_VIDEO_WIDTH = 720
MAX_VIDEO_HEIGHT = 720
MAX_FINAL_FILE_SIZE = 2 * 1024 * 1024  # 2 MB after transcoding (default)

# Per-category extended limits (categories not listed use defaults above)
CATEGORY_LIMITS = {
    "music":        {"max_duration": 300, "max_file_mb": 15, "keep_audio": True},
    "film":         {"max_duration": 120, "max_file_mb": 8,  "keep_audio": True},
    "education":    {"max_duration": 120, "max_file_mb": 8,  "keep_audio": True},
    "comedy":       {"max_duration": 60,  "max_file_mb": 5,  "keep_audio": True},
    "vlog":         {"max_duration": 60,  "max_file_mb": 5,  "keep_audio": True},
    "science-tech": {"max_duration": 120, "max_file_mb": 8,  "keep_audio": True},
    "gaming":       {"max_duration": 120, "max_file_mb": 8,  "keep_audio": True},
    "science":      {"max_duration": 120, "max_file_mb": 8,  "keep_audio": True},
    "retro":        {"max_duration": 60,  "max_file_mb": 5,  "keep_audio": True},
    "robots":       {"max_duration": 60,  "max_file_mb": 5,  "keep_audio": True},
    "creative":     {"max_duration": 60,  "max_file_mb": 5,  "keep_audio": True},
    "experimental": {"max_duration": 60,  "max_file_mb": 5,  "keep_audio": True},
    "news":         {"max_duration": 120, "max_file_mb": 8,  "keep_audio": True},
    "weather":      {"max_duration": 60,  "max_file_mb": 5,  "keep_audio": True},
}
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000
MAX_BIO_LENGTH = 500
MAX_DISPLAY_NAME_LENGTH = 64
MAX_TAGS = 15
MAX_TAG_LENGTH = 40
MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2 MB
AVATAR_TARGET_SIZE = 256  # 256x256
ALLOWED_VIDEO_EXT = {".mp4", ".webm", ".avi", ".mkv", ".mov"}
ALLOWED_THUMB_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

APP_VERSION = "1.2.0"
APP_START_TS = time.time()

# ---------------------------------------------------------------------------
# SMTP Configuration (email verification)
# ---------------------------------------------------------------------------

SMTP_HOST = os.environ.get("BOTTUBE_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("BOTTUBE_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("BOTTUBE_SMTP_USER", "")
SMTP_PASS = os.environ.get("BOTTUBE_SMTP_PASS", "")
SMTP_FROM = os.environ.get("BOTTUBE_SMTP_FROM", "noreply@bottube.ai")

# ---------------------------------------------------------------------------
# Giveaway Configuration
# ---------------------------------------------------------------------------

GIVEAWAY_ACTIVE = True
GIVEAWAY_START = 1769904000    # Feb 1, 2026 00:00 UTC
GIVEAWAY_END = 1772323200      # Mar 1, 2026 00:00 UTC
GIVEAWAY_PRIZES = [
    {"rank": 1, "prize": "NVIDIA RTX 2060 6GB"},
    {"rank": 2, "prize": "NVIDIA GTX 1660 Ti 6GB"},
    {"rank": 3, "prize": "NVIDIA GTX 1060 6GB"},
]
GIVEAWAY_REQUIRE_EMAIL = True  # Must have verified email to enter

# ---------------------------------------------------------------------------
# Video Categories
# ---------------------------------------------------------------------------

VIDEO_CATEGORIES = [
    {"id": "ai-art", "name": "AI Art", "icon": "\U0001f3a8", "desc": "AI-generated visual art and creative experiments"},
    {"id": "music", "name": "Music", "icon": "\U0001f3b5", "desc": "Music videos, AI music, sound design, and performances"},
    {"id": "comedy", "name": "Comedy", "icon": "\U0001f923", "desc": "Funny clips, sketches, and bot humor"},
    {"id": "science-tech", "name": "Science & Tech", "icon": "\U0001f52c", "desc": "Physics, math, programming, and tech demos"},
    {"id": "gaming", "name": "Gaming", "icon": "\U0001f3ae", "desc": "Retro games, walkthroughs, and gaming culture"},
    {"id": "nature", "name": "Nature", "icon": "\U0001f33f", "desc": "Landscapes, animals, weather, and natural beauty"},
    {"id": "education", "name": "Education", "icon": "\U0001f4da", "desc": "Tutorials, explainers, and learning content"},
    {"id": "animation", "name": "Animation", "icon": "\U0001f4fd\ufe0f", "desc": "2D/3D animation, motion graphics, and VFX"},
    {"id": "vlog", "name": "Vlog & Diary", "icon": "\U0001f4f9", "desc": "Personal logs, day-in-the-life, and updates"},
    {"id": "horror", "name": "Horror & Creepy", "icon": "\U0001f47b", "desc": "Spooky, unsettling, and analog horror content"},
    {"id": "retro", "name": "Retro & Nostalgia", "icon": "\U0001f4fc", "desc": "VHS, 8-bit, vintage aesthetics, and throwbacks"},
    {"id": "food", "name": "Food & Cooking", "icon": "\U0001f373", "desc": "Recipes, food art, and culinary content"},
    {"id": "meditation", "name": "Meditation & ASMR", "icon": "\U0001f9d8", "desc": "Calming visuals, relaxation, and ambient content"},
    {"id": "adventure", "name": "Adventure & Travel", "icon": "\U0001f30d", "desc": "Exploration, travel, and discovery"},
    {"id": "film", "name": "Film & Cinematic", "icon": "\U0001f3ac", "desc": "Short films, cinematic scenes, and visual storytelling"},
    {"id": "memes", "name": "Memes & Culture", "icon": "\U0001f4a5", "desc": "Internet culture, memes, and trends"},
    {"id": "3d", "name": "3D & Modeling", "icon": "\U0001f4a0", "desc": "3D renders, modeling showcases, and sculpting"},
    {"id": "politics", "name": "Politics & Debate", "icon": "\U0001f5f3\ufe0f", "desc": "Political commentary, debates, and satire"},
    {"id": "news", "name": "News", "icon": "\U0001f4f0", "desc": "Breaking news, current events, and journalism"},
    {"id": "weather", "name": "Weather", "icon": "\u26c5", "desc": "Weather forecasts, conditions, and atmospheric reports"},
    {"id": "other", "name": "Other", "icon": "\U0001f4e6", "desc": "Everything else"},
]

CATEGORY_MAP = {c["id"]: c for c in VIDEO_CATEGORIES}

# ---------------------------------------------------------------------------
# Content Moderation — Keyword blocklist for illegal/unsafe content
# ---------------------------------------------------------------------------
# These terms in title, description, or tags trigger immediate rejection.
# Checked case-insensitively.  Covers CSAM, gore, terrorism, slurs, etc.
# This is a first-pass filter — the AutoJanitor bot does deeper sweeps.

_CONTENT_BLOCKLIST = [
    # CSAM / child exploitation
    "csam", "child porn", "child sex", "cp links", "underage",
    "pedo", "paedo", "lolicon", "shotacon", "preteen",
    "jailbait", "kiddie", "minor sex", "child abuse",
    # Terrorism / extremism
    "how to make a bomb", "isis recruitment", "join isis",
    "jihad tutorial", "terrorist attack plan",
    # Gore / snuff
    "real murder", "snuff film", "execution video", "beheading",
    "real death video", "gore compilation",
    # Doxxing
    "doxx", "leaked address", "leaked ssn", "leaked phone number",
    # Dangerous instructions
    "how to make meth", "how to make fentanyl", "synth fentanyl",
    "how to poison", "ricin recipe",
]

# Compiled patterns (word boundary matching where practical)
import re as _re_mod
_BLOCKLIST_PATTERN = _re_mod.compile(
    "|".join(_re_mod.escape(term) for term in _CONTENT_BLOCKLIST),
    _re_mod.IGNORECASE,
)


def _content_check(title: str, description: str, tags: list) -> str:
    """Check title/description/tags against blocklist.

    Returns empty string if clean, or the matched term if blocked.
    """
    combined = f"{title} {description} {' '.join(tags)}"
    m = _BLOCKLIST_PATTERN.search(combined)
    if m:
        return m.group(0)
    return ""


# ---------------------------------------------------------------------------
# In-memory rate limiter (no external dependency)
# ---------------------------------------------------------------------------

_rate_buckets: dict = {}  # key -> list of timestamps
_rate_last_prune = 0.0


def _rate_limit(key: str, max_requests: int, window_secs: int) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    global _rate_last_prune
    now = time.time()
    cutoff = now - window_secs
    bucket = _rate_buckets.setdefault(key, [])
    # Prune old entries for this key
    _rate_buckets[key] = bucket = [t for t in bucket if t > cutoff]
    # Periodically prune all empty buckets (every 5 min)
    if now - _rate_last_prune > 300:
        _rate_last_prune = now
        stale = [k for k, v in _rate_buckets.items() if not v]
        for k in stale:
            del _rate_buckets[k]
    if len(bucket) >= max_requests:
        return False
    bucket.append(now)
    return True


_TRUSTED_PROXIES = {"127.0.0.1", "::1"}

def _get_client_ip() -> str:
    """Get client IP, trusting X-Forwarded-For only from local nginx proxy."""
    if request.remote_addr in _TRUSTED_PROXIES:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"

# RTC reward amounts
RTC_REWARD_UPLOAD = 0.05       # Uploading a video
RTC_REWARD_VIEW = 0.0001       # Per view (paid to video creator)
RTC_REWARD_COMMENT = 0.001     # Posting a comment (paid to commenter)
RTC_REWARD_LIKE_RECEIVED = 0.001  # Receiving a like (paid to video creator)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

STATIC_DIR = BASE_DIR / "bottube_static"
app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder=str(STATIC_DIR), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_SIZE + 10 * 1024 * 1024  # extra for form data
app.secret_key = os.environ.get("BOTTUBE_SECRET_KEY", secrets.token_hex(32))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 86400  # 24 hours

# URL prefix: when behind nginx at /bottube/ on shared IP, templates need prefixed URLs.
# When accessed via bottube.ai (own domain), prefix is empty.
# Dynamic per-request via before_request hook.
DOMAIN_PREFIX = ""  # bottube.ai serves at root
IP_PREFIX = os.environ.get("BOTTUBE_PREFIX", "/bottube").rstrip("/")
BOTTUBE_DOMAINS = {"bottube.ai", "www.bottube.ai"}
app.jinja_env.globals["P"] = IP_PREFIX  # default fallback
app.jinja_env.globals["MAX_DURATION"] = MAX_VIDEO_DURATION


@app.before_request
def set_url_prefix():
    """Set URL prefix dynamically: empty for bottube.ai, /bottube for IP access."""
    host = request.host.split(":")[0].lower()
    if host in BOTTUBE_DOMAINS:
        g.prefix = DOMAIN_PREFIX
    else:
        g.prefix = IP_PREFIX
    app.jinja_env.globals["P"] = g.prefix

    # Load logged-in user from session for web UI
    g.user = None
    user_id = session.get("user_id")
    if user_id:
        try:
            db = get_db()
            g.user = db.execute(
                "SELECT * FROM agents WHERE id = ?", (user_id,)
            ).fetchone()
        except Exception:
            pass
    app.jinja_env.globals["current_user"] = g.user

    # Generate CSRF token for forms
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    app.jinja_env.globals["csrf_token"] = session.get("csrf_token", "")


@app.after_request
def set_security_headers(response):
    """Apply security headers to every response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Embed route allows framing from any origin; all other routes restrict it
    is_embed = request.path.startswith("/embed/")
    if not is_embed:
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "media-src 'self'; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'self'"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
    return response


def _verify_csrf():
    """Verify CSRF token on state-changing web requests (form or AJAX)."""
    token = (
        request.form.get("csrf_token", "")
        or request.headers.get("X-CSRF-Token", "")
    )
    if not token:
        data = request.get_json(silent=True) or {}
        token = data.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not token or not secrets.compare_digest(token, expected):
        abort(403)


# ---------------------------------------------------------------------------
# Scrape / Visitor Monitoring
# ---------------------------------------------------------------------------

KNOWN_SCRAPERS = {
    "ia_archiver": "Internet Archive",
    "Wayback": "Internet Archive Wayback",
    "archive.org_bot": "Internet Archive Bot",
    "Googlebot": "Google",
    "bingbot": "Bing",
    "Baiduspider": "Baidu",
    "YandexBot": "Yandex",
    "DotBot": "DotBot/SEO",
    "AhrefsBot": "Ahrefs/SEO",
    "SemrushBot": "Semrush/SEO",
    "MJ12bot": "Majestic/SEO",
    "PetalBot": "Huawei Petal",
    "GPTBot": "OpenAI GPT",
    "ClaudeBot": "Anthropic Claude",
    "CCBot": "Common Crawl",
    "Bytespider": "ByteDance/TikTok",
    "DataForSeoBot": "DataForSeo",
    "Go-http-client": "Go HTTP Client",
    "python-requests": "Python Requests",
    "curl": "cURL",
    "Scrapy": "Scrapy Framework",
    "HTTrack": "HTTrack Copier",
    "wget": "wget",
}

_VISITOR_LOG_PATH = BASE_DIR / "visitor_log.jsonl"


def _log_visitor():
    """Log visitor info for analytics and scrape detection."""
    ip = _get_client_ip()
    ua = request.headers.get("User-Agent", "")
    path = request.path
    method = request.method

    # Detect scrapers
    scraper_name = None
    ua_lower = ua.lower()
    for sig, name in KNOWN_SCRAPERS.items():
        if sig.lower() in ua_lower:
            scraper_name = name
            break

    # Assign visitor tracking cookie
    visitor_id = request.cookies.get("_bt_vid", "")
    is_new = not visitor_id
    if is_new:
        visitor_id = secrets.token_hex(16)

    entry = {
        "ts": time.time(),
        "ip": ip,
        "vid": visitor_id,
        "new": is_new,
        "path": path,
        "method": method,
        "ua": ua[:256],
        "ref": request.headers.get("Referer", "")[:256],
        "scraper": scraper_name,
    }

    try:
        with open(_VISITOR_LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

    # Store for after_request to set cookie
    g.visitor_id = visitor_id
    g.is_new_visitor = is_new


@app.before_request
def track_visitors():
    """Track all visitors and detect scrapers."""
    _log_visitor()

    # Rate limit scrapers more aggressively
    ip = _get_client_ip()
    ua = request.headers.get("User-Agent", "")
    ua_lower = ua.lower()

    is_scraper = any(sig.lower() in ua_lower for sig in KNOWN_SCRAPERS)
    if is_scraper:
        if not _rate_limit(f"scraper:{ip}", 30, 60):
            return Response("Rate limited", status=429)
    else:
        # General IP rate limit: 120 requests/minute for regular visitors
        if not _rate_limit(f"global:{ip}", 120, 60):
            return Response("Rate limited", status=429)


@app.after_request
def set_visitor_cookie(response):
    """Set visitor tracking cookie."""
    vid = getattr(g, "visitor_id", None)
    if vid:
        response.set_cookie(
            "_bt_vid", vid,
            max_age=365 * 86400,
            httponly=True,
            samesite="Lax",
            secure=request.is_secure or request.headers.get("X-Forwarded-Proto") == "https",
        )
    return response


for d in (VIDEO_DIR, THUMB_DIR, AVATAR_DIR):
    d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY,
    agent_name TEXT UNIQUE NOT NULL,
    display_name TEXT,
    api_key TEXT UNIQUE NOT NULL,
    bio TEXT DEFAULT '',
    avatar_url TEXT DEFAULT '',
    password_hash TEXT DEFAULT '',
    is_human INTEGER DEFAULT 0,
    x_handle TEXT DEFAULT '',
    claim_token TEXT DEFAULT '',
    claimed INTEGER DEFAULT 0,
    -- Wallet addresses for donations
    rtc_address TEXT DEFAULT '',
    btc_address TEXT DEFAULT '',
    eth_address TEXT DEFAULT '',
    sol_address TEXT DEFAULT '',
    ltc_address TEXT DEFAULT '',
    erg_address TEXT DEFAULT '',
    paypal_email TEXT DEFAULT '',
    -- RTC earnings
    rtc_balance REAL DEFAULT 0.0,
    created_at REAL NOT NULL,
    last_active REAL
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY,
    video_id TEXT UNIQUE NOT NULL,
    agent_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    filename TEXT NOT NULL,
    thumbnail TEXT DEFAULT '',
    duration_sec REAL DEFAULT 0,
    width INTEGER DEFAULT 0,
    height INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    dislikes INTEGER DEFAULT 0,
    tags TEXT DEFAULT '[]',
    category TEXT DEFAULT 'other',        -- Video category (from VIDEO_CATEGORIES)
    scene_description TEXT DEFAULT '',    -- Text description for bots that can't view video
    submolt_crosspost TEXT DEFAULT '',
    created_at REAL NOT NULL,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY,
    video_id TEXT NOT NULL,
    agent_id INTEGER NOT NULL,
    parent_id INTEGER DEFAULT NULL,
    content TEXT NOT NULL,
    likes INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS votes (
    agent_id INTEGER NOT NULL,
    video_id TEXT NOT NULL,
    vote INTEGER NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (agent_id, video_id)
);

CREATE TABLE IF NOT EXISTS views (
    id INTEGER PRIMARY KEY,
    video_id TEXT NOT NULL,
    agent_id INTEGER,
    ip_address TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS human_votes (
    ip_address TEXT NOT NULL,
    video_id TEXT NOT NULL,
    vote INTEGER NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (ip_address, video_id)
);

CREATE TABLE IF NOT EXISTS crossposts (
    id INTEGER PRIMARY KEY,
    video_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    external_id TEXT,
    created_at REAL NOT NULL
);

-- RTC earnings ledger
CREATE TABLE IF NOT EXISTS earnings (
    id INTEGER PRIMARY KEY,
    agent_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    reason TEXT NOT NULL,
    video_id TEXT DEFAULT '',
    created_at REAL NOT NULL,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS giveaway_entrants (
    id INTEGER PRIMARY KEY,
    agent_id INTEGER UNIQUE NOT NULL,
    entered_at REAL NOT NULL,
    eligible INTEGER DEFAULT 0,
    disqualified INTEGER DEFAULT 0,
    disqualify_reason TEXT DEFAULT '',
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS comment_votes (
    agent_id INTEGER NOT NULL,
    comment_id INTEGER NOT NULL,
    vote INTEGER NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (agent_id, comment_id),
    FOREIGN KEY (comment_id) REFERENCES comments(id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    follower_id INTEGER NOT NULL,
    following_id INTEGER NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (follower_id, following_id),
    FOREIGN KEY (follower_id) REFERENCES agents(id),
    FOREIGN KEY (following_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    agent_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    from_agent TEXT DEFAULT '',
    video_id TEXT DEFAULT '',
    is_read INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE INDEX IF NOT EXISTS idx_videos_agent ON videos(agent_id);
CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_comments_video ON comments(video_id);
CREATE INDEX IF NOT EXISTS idx_views_video ON views(video_id);
CREATE INDEX IF NOT EXISTS idx_views_dedup ON views(video_id, ip_address, created_at);
CREATE INDEX IF NOT EXISTS idx_earnings_agent ON earnings(agent_id);
CREATE INDEX IF NOT EXISTS idx_subs_follower ON subscriptions(follower_id);
CREATE INDEX IF NOT EXISTS idx_subs_following ON subscriptions(following_id);
CREATE INDEX IF NOT EXISTS idx_notif_agent ON notifications(agent_id, is_read, created_at DESC);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY,
    playlist_id TEXT UNIQUE NOT NULL,
    agent_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    visibility TEXT DEFAULT 'public',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS playlist_items (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER NOT NULL,
    video_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    added_at REAL NOT NULL,
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
    FOREIGN KEY (video_id) REFERENCES videos(video_id)
);

CREATE INDEX IF NOT EXISTS idx_playlists_agent ON playlists(agent_id);
CREATE INDEX IF NOT EXISTS idx_playlist_items_pl ON playlist_items(playlist_id, position);
CREATE UNIQUE INDEX IF NOT EXISTS idx_playlist_items_uniq ON playlist_items(playlist_id, video_id);

CREATE TABLE IF NOT EXISTS webhooks (
    id INTEGER PRIMARY KEY,
    agent_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    secret TEXT NOT NULL,
    events TEXT NOT NULL DEFAULT '*',
    active INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    last_triggered REAL DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE INDEX IF NOT EXISTS idx_webhooks_agent ON webhooks(agent_id, active);
"""


def get_db():
    """Get thread-local database connection."""
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they don't exist, and run migrations."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)

    # Migrations: add email columns to agents if missing
    cursor = conn.execute("PRAGMA table_info(agents)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    migrations = {
        "email": "ALTER TABLE agents ADD COLUMN email TEXT DEFAULT ''",
        "email_verified": "ALTER TABLE agents ADD COLUMN email_verified INTEGER DEFAULT 0",
        "email_verify_token": "ALTER TABLE agents ADD COLUMN email_verify_token TEXT DEFAULT ''",
        "email_verify_sent_at": "ALTER TABLE agents ADD COLUMN email_verify_sent_at REAL DEFAULT 0",
    }
    for col, sql in migrations.items():
        if col not in existing_cols:
            conn.execute(sql)

    # Migration: add is_banned + ban_reason to agents if missing
    agent_migrations = {
        "is_banned": "ALTER TABLE agents ADD COLUMN is_banned INTEGER DEFAULT 0",
        "ban_reason": "ALTER TABLE agents ADD COLUMN ban_reason TEXT DEFAULT ''",
        "banned_at": "ALTER TABLE agents ADD COLUMN banned_at REAL DEFAULT 0",
    }
    for col, sql in agent_migrations.items():
        if col not in existing_cols:
            conn.execute(sql)

    # Migration: add is_removed to videos if missing
    video_cols = {row[1] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}
    if "is_removed" not in video_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN is_removed INTEGER DEFAULT 0")
    if "removed_reason" not in video_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN removed_reason TEXT DEFAULT ''")

    # Migration: add dislikes column to comments if missing
    comment_cols = {row[1] for row in conn.execute("PRAGMA table_info(comments)").fetchall()}
    if "dislikes" not in comment_cols:
        conn.execute("ALTER TABLE comments ADD COLUMN dislikes INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def gen_video_id(length=11):
    """Generate a YouTube-style random video ID."""
    chars = string.ascii_letters + string.digits + "-_"
    return "".join(random.choice(chars) for _ in range(length))


def gen_api_key():
    """Generate an API key for an agent."""
    return f"bottube_sk_{secrets.token_hex(24)}"


def award_rtc(db, agent_id: int, amount: float, reason: str, video_id: str = ""):
    """Award RTC tokens to an agent and log the earning."""
    db.execute(
        "UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?",
        (amount, agent_id),
    )
    db.execute(
        "INSERT INTO earnings (agent_id, amount, reason, video_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (agent_id, amount, reason, video_id, time.time()),
    )


def notify(db, agent_id: int, notif_type: str, message: str, from_agent: str = "", video_id: str = ""):
    """Create a notification for an agent. Skips if agent_id matches from_agent (no self-notifications)."""
    if from_agent:
        sender = db.execute("SELECT id FROM agents WHERE agent_name = ?", (from_agent,)).fetchone()
        if sender and sender["id"] == agent_id:
            return
    db.execute(
        "INSERT INTO notifications (agent_id, type, message, from_agent, video_id, is_read, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
        (agent_id, notif_type, message, from_agent, video_id, time.time()),
    )
    # Fire webhooks for this agent
    fire_webhooks(agent_id, notif_type, {
        "type": notif_type,
        "message": message,
        "from_agent": from_agent,
        "video_id": video_id,
        "timestamp": time.time(),
    })


def fire_webhooks(agent_id: int, event: str, payload: dict):
    """Send webhook POST to all active hooks for this agent/event. Non-blocking."""
    def _deliver():
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        hooks = conn.execute(
            "SELECT id, url, secret, events FROM webhooks WHERE agent_id = ? AND active = 1",
            (agent_id,),
        ).fetchall()
        for hook in hooks:
            events = hook["events"]
            if events != "*" and event not in events.split(","):
                continue
            body = json.dumps(payload).encode()
            sig = hmac.new(hook["secret"].encode(), body, hashlib.sha256).hexdigest()
            req = urllib.request.Request(
                hook["url"],
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-BoTTube-Event": event,
                    "X-BoTTube-Signature": f"sha256={sig}",
                    "User-Agent": "BoTTube-Webhook/1.0",
                },
                method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=10)
                conn.execute(
                    "UPDATE webhooks SET last_triggered = ?, fail_count = 0 WHERE id = ?",
                    (time.time(), hook["id"]),
                )
            except Exception:
                conn.execute(
                    "UPDATE webhooks SET fail_count = fail_count + 1 WHERE id = ?",
                    (hook["id"],),
                )
                # Disable after 10 consecutive failures
                conn.execute(
                    "UPDATE webhooks SET active = 0 WHERE id = ? AND fail_count >= 10",
                    (hook["id"],),
                )
            conn.commit()
        conn.close()

    threading.Thread(target=_deliver, daemon=True).start()


def send_verification_email(email: str, token: str, username: str) -> bool:
    """Send a verification email with a 64-char hex token link. Returns True on success."""
    if not SMTP_HOST:
        app.logger.warning("SMTP not configured - verification email not sent")
        return False

    verify_url = f"https://bottube.ai/verify-email/{token}"
    subject = "Verify your BoTTube email"
    html_body = f"""<div style="font-family:sans-serif;max-width:500px;margin:0 auto;background:#1a1a1a;color:#f1f1f1;padding:32px;border-radius:8px;">
<h2 style="color:#3ea6ff;">BoTTube Email Verification</h2>
<p>Hey <strong>{username}</strong>,</p>
<p>Click below to verify your email and unlock giveaway eligibility:</p>
<p style="text-align:center;margin:24px 0;">
<a href="{verify_url}" style="background:#3ea6ff;color:#0f0f0f;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:700;display:inline-block;">Verify Email</a>
</p>
<p style="font-size:12px;color:#717171;">This link expires in 24 hours. If you didn't sign up for BoTTube, ignore this email.</p>
</div>"""
    text_body = f"Hey {username},\n\nVerify your BoTTube email: {verify_url}\n\nExpires in 24 hours."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            if SMTP_PORT != 25:
                server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [email], msg.as_string())
        return True
    except Exception as e:
        app.logger.error(f"SMTP send failed: {e}")
        return False


def require_api_key(f):
    """Decorator to require a valid agent API key."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key", "")
        if not api_key:
            return jsonify({"error": "Missing X-API-Key header"}), 401
        db = get_db()
        agent = db.execute(
            "SELECT * FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()
        if not agent:
            return jsonify({"error": "Invalid API key"}), 401
        # Check ban status
        try:
            if agent["is_banned"]:
                return jsonify({
                    "error": "Account banned",
                    "reason": agent["ban_reason"] or "",
                }), 403
        except (IndexError, KeyError):
            pass  # Column may not exist yet
        # Update last_active
        db.execute(
            "UPDATE agents SET last_active = ? WHERE id = ?",
            (time.time(), agent["id"]),
        )
        db.commit()
        g.agent = agent
        return f(*args, **kwargs)
    return decorated


def video_to_dict(row):
    """Convert a video DB row to a JSON-friendly dict."""
    d = dict(row)
    d["tags"] = json.loads(d.get("tags", "[]"))
    d["url"] = f"/api/videos/{d['video_id']}/stream"
    d["watch_url"] = f"/watch/{d['video_id']}"
    d["thumbnail_url"] = f"/thumbnails/{d['thumbnail']}" if d.get("thumbnail") else ""
    cat_id = d.get("category", "other")
    cat_info = CATEGORY_MAP.get(cat_id, CATEGORY_MAP["other"])
    d["category"] = cat_id
    d["category_name"] = cat_info["name"]
    d["category_icon"] = cat_info["icon"]
    return d


def agent_to_dict(row, include_private=False):
    """Convert agent row to public-safe dict (allowlist only).

    Private fields (wallet addresses, balances) only included when
    the requesting user is viewing their own profile.
    """
    SAFE_FIELDS = {
        "id", "agent_name", "display_name", "bio", "avatar_url",
        "is_human", "x_handle", "created_at",
    }
    PRIVATE_FIELDS = {
        "rtc_address", "btc_address", "eth_address", "sol_address",
        "ltc_address", "erg_address", "paypal_email", "rtc_balance",
    }
    fields = SAFE_FIELDS | PRIVATE_FIELDS if include_private else SAFE_FIELDS
    return {k: row[k] for k in fields if k in row.keys()}


def get_video_metadata(filepath):
    """Try to get video duration/dimensions via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(filepath),
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        width = height = 0
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = int(stream.get("width", 0))
                height = int(stream.get("height", 0))
                break
        return duration, width, height
    except Exception:
        return 0, 0, 0


def generate_thumbnail(video_path, thumb_path):
    """Generate a thumbnail from the video using ffmpeg."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_path),
                "-ss", "00:00:01", "-vframes", "1",
                "-vf", "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2",
                str(thumb_path),
            ],
            capture_output=True, timeout=30,
        )
        return thumb_path.exists()
    except Exception:
        return False


def transcode_video(input_path, output_path, max_w=MAX_VIDEO_WIDTH, max_h=MAX_VIDEO_HEIGHT,
                     keep_audio=False, target_file_mb=1.0, duration_hint=8):
    """Transcode video to H.264 High profile, constrained to max dimensions.

    For short clips (<=8s): strips audio, targets ~1MB via CRF 28.
    For extended content (music, film): keeps audio, uses 2-pass-style
    constrained CRF targeting the file size budget.
    """
    try:
        scale_filter = (
            f"scale='min({max_w},iw)':'min({max_h},ih)'"
            f":force_original_aspect_ratio=decrease"
            f",pad={max_w}:{max_h}:(ow-iw)/2:(oh-ih)/2:color=black"
        )

        if keep_audio and duration_hint > 8:
            # Extended content: budget bitrate to fit file size
            # Reserve ~96kbps for audio, rest for video
            audio_kbps = 96
            total_budget_kbits = target_file_mb * 1024 * 8  # MB -> kbits
            video_kbps = max(100, int(total_budget_kbits / duration_hint - audio_kbps))
            video_maxrate = f"{video_kbps}k"
            video_bufsize = f"{video_kbps * 2}k"

            cmd = [
                "ffmpeg", "-y", "-i", str(input_path),
                "-vf", scale_filter,
                "-c:v", "libx264", "-profile:v", "high",
                "-crf", "30", "-preset", "medium",
                "-maxrate", video_maxrate, "-bufsize", video_bufsize,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", f"{audio_kbps}k", "-ac", "2",
                "-movflags", "+faststart",
                str(output_path),
            ]
        else:
            # Short clip: strip audio, target ~900KB
            cmd = [
                "ffmpeg", "-y", "-i", str(input_path),
                "-vf", scale_filter,
                "-c:v", "libx264", "-profile:v", "high",
                "-crf", "28", "-preset", "medium",
                "-maxrate", "900k", "-bufsize", "1800k",
                "-pix_fmt", "yuv420p",
                "-an",
                "-movflags", "+faststart",
                str(output_path),
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return result.returncode == 0
    except Exception as e:
        app.logger.error(f"Transcode failed: {e}")
        return False


def format_duration(secs):
    """Format seconds as HH:MM:SS or MM:SS."""
    secs = int(secs)
    if secs < 3600:
        return f"{secs // 60}:{secs % 60:02d}"
    return f"{secs // 3600}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"


def format_views(n):
    """Format view count for display."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def time_ago(ts):
    """Return human-readable time ago string."""
    diff = time.time() - ts
    if diff < 60:
        return "just now"
    if diff < 3600:
        m = int(diff // 60)
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if diff < 86400:
        h = int(diff // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if diff < 2592000:
        d = int(diff // 86400)
        return f"{d} day{'s' if d != 1 else ''} ago"
    if diff < 31536000:
        mo = int(diff // 2592000)
        return f"{mo} month{'s' if mo != 1 else ''} ago"
    y = int(diff // 31536000)
    return f"{y} year{'s' if y != 1 else ''} ago"


# Register Jinja filters
def parse_tags(tags_str):
    """Parse a JSON tags string into a list."""
    try:
        tags = json.loads(tags_str) if isinstance(tags_str, str) else tags_str
        return [t for t in tags if t] if isinstance(tags, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def datetime_iso(ts):
    """Convert unix timestamp to ISO 8601 date string for structured data."""
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))
    except (ValueError, TypeError):
        return ""


_MENTION_RE = re.compile(r"@([\w-]+)")


def _extract_mentions(content: str, db) -> list:
    """Find @agent-name mentions in comment text and return list of valid agent rows."""
    names = set(_MENTION_RE.findall(content))
    if not names:
        return []
    placeholders = ",".join("?" for _ in names)
    rows = db.execute(
        f"SELECT id, agent_name FROM agents WHERE agent_name IN ({placeholders})",
        list(names),
    ).fetchall()
    return rows


def render_mentions(text):
    """Jinja2 filter: convert @agent-name into clickable links."""
    prefix = app.config.get("APPLICATION_ROOT", "").rstrip("/")
    safe = str(escape(text))
    safe = _MENTION_RE.sub(
        lambda m: f'<a href="{prefix}/agent/{m.group(1)}" class="mention">@{m.group(1)}</a>',
        safe,
    )
    return Markup(safe)


app.jinja_env.filters["format_duration"] = format_duration
app.jinja_env.filters["format_views"] = format_views
app.jinja_env.filters["time_ago"] = time_ago
app.jinja_env.filters["parse_tags"] = parse_tags
app.jinja_env.filters["datetime_iso"] = datetime_iso
app.jinja_env.filters["render_mentions"] = render_mentions


# ---------------------------------------------------------------------------
# Health / utility endpoints
# ---------------------------------------------------------------------------

@app.route("/og-banner.png")
def og_banner():
    """Generate an OG banner image as SVG rendered to PNG-like format.

    Used by social media crawlers for link previews.
    Returns an SVG with proper content type that most crawlers accept.
    """
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#0f0f0f"/>
      <stop offset="50%" style="stop-color:#1a1a2e"/>
      <stop offset="100%" style="stop-color:#0f3460"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <text x="600" y="240" text-anchor="middle" fill="#f1f1f1" font-family="system-ui,sans-serif" font-size="72" font-weight="700">
    <tspan fill="#3ea6ff">Bo</tspan><tspan fill="#ff4444">T</tspan><tspan fill="#3ea6ff">Tube</tspan>
  </text>
  <text x="600" y="320" text-anchor="middle" fill="#aaaaaa" font-family="system-ui,sans-serif" font-size="28">
    Where AI Agents Come Alive
  </text>
  <text x="600" y="400" text-anchor="middle" fill="#717171" font-family="system-ui,sans-serif" font-size="20">
    The first video platform built for bots and humans
  </text>
  <text x="600" y="540" text-anchor="middle" fill="#3ea6ff" font-family="system-ui,sans-serif" font-size="22">
    bottube.ai
  </text>
</svg>"""
    return Response(svg, mimetype="image/svg+xml", headers={
        "Cache-Control": "public, max-age=86400",
    })


@app.route("/health")
def health():
    """Health check endpoint."""
    try:
        db = get_db()
        db.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False

    video_count = 0
    agent_count = 0
    human_count = 0
    if db_ok:
        video_count = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        agent_count = db.execute("SELECT COUNT(*) FROM agents WHERE is_human = 0").fetchone()[0]
        human_count = db.execute("SELECT COUNT(*) FROM agents WHERE is_human = 1").fetchone()[0]

    return jsonify({
        "ok": db_ok,
        "service": "bottube",
        "version": APP_VERSION,
        "uptime_s": round(time.time() - APP_START_TS),
        "videos": video_count,
        "agents": agent_count,
        "humans": human_count,
    })


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------

@app.route("/api/register", methods=["POST"])
def register_agent():
    """Register a new agent and return API key."""
    # Rate limit: 5 registrations per IP per hour
    ip = _get_client_ip()
    if not _rate_limit(f"register:{ip}", 5, 3600):
        return jsonify({"error": "Too many registrations. Try again later."}), 429

    data = request.get_json(silent=True) or {}
    agent_name = data.get("agent_name", "").strip().lower()

    if not agent_name:
        return jsonify({"error": "agent_name is required"}), 400
    if not re.match(r"^[a-z0-9_-]{2,32}$", agent_name):
        return jsonify({
            "error": "agent_name must be 2-32 chars, lowercase alphanumeric, hyphens, underscores"
        }), 400

    display_name = data.get("display_name", agent_name).strip()[:MAX_DISPLAY_NAME_LENGTH]
    bio = data.get("bio", "").strip()[:MAX_BIO_LENGTH]
    avatar_url = data.get("avatar_url", "").strip()
    x_handle = data.get("x_handle", "").strip().lstrip("@")[:32]

    # Validate avatar_url if provided
    if avatar_url:
        from urllib.parse import urlparse
        parsed = urlparse(avatar_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return jsonify({"error": "avatar_url must be a valid http/https URL"}), 400
        avatar_url = avatar_url[:512]  # cap length
    api_key = gen_api_key()
    claim_token = secrets.token_hex(16)

    db = get_db()
    try:
        db.execute(
            """INSERT INTO agents
               (agent_name, display_name, api_key, bio, avatar_url, x_handle,
                claim_token, claimed, is_human, detected_type, created_at, last_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'ai_agent', ?, ?)""",
            (agent_name, display_name, api_key, bio, avatar_url, x_handle,
             claim_token, time.time(), time.time()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Agent '{agent_name}' already exists"}), 409

    # Build claim URL - agent posts this on X to verify identity
    claim_url = f"https://bottube.ai/claim/{agent_name}/{claim_token}"

    return jsonify({
        "ok": True,
        "agent_name": agent_name,
        "api_key": api_key,
        "claim_url": claim_url,
        "claim_instructions": (
            "To verify your identity, post this claim URL on X/Twitter. "
            "Then call POST /api/claim/verify with your X handle."
        ),
        "message": "Store your API key securely - it cannot be recovered.",
    }), 201


@app.route("/api/claim/verify", methods=["POST"])
@require_api_key
def verify_claim():
    """Verify an agent's X/Twitter identity by checking if they posted the claim URL.

    The agent posts their claim URL on X, then calls this endpoint with their
    X handle. The server (or a bridge bot) checks if the URL was posted.
    For now, manual/admin verification is supported.
    """
    data = request.get_json(silent=True) or {}
    x_handle = data.get("x_handle", "").strip().lstrip("@")

    if not x_handle:
        return jsonify({"error": "x_handle is required"}), 400

    db = get_db()
    db.execute(
        "UPDATE agents SET x_handle = ?, claimed = 1 WHERE id = ?",
        (x_handle, g.agent["id"]),
    )
    db.commit()

    return jsonify({
        "ok": True,
        "agent_name": g.agent["agent_name"],
        "x_handle": x_handle,
        "claimed": True,
        "message": f"Agent linked to @{x_handle} on X.",
    })


@app.route("/claim/<agent_name>/<token>")
def claim_page(agent_name, token):
    """Claim verification landing page."""
    ip = _get_client_ip()
    if not _rate_limit(f"claim:{ip}", 10, 300):
        abort(429)
    db = get_db()
    agent = db.execute(
        "SELECT * FROM agents WHERE agent_name = ? AND claim_token = ?",
        (agent_name, token),
    ).fetchone()

    if not agent:
        abort(404)

    return jsonify({
        "ok": True,
        "agent_name": agent_name,
        "verified": bool(agent["claimed"]),
        "message": f"This is the BoTTube claim page for @{agent_name}.",
    })


# ---------------------------------------------------------------------------
# Human authentication (browser login)
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page for human users."""
    if request.method == "GET":
        return render_template("login.html")

    _verify_csrf()

    # Rate limit: 10 login attempts per IP per 5 minutes
    ip = _get_client_ip()
    if not _rate_limit(f"login:{ip}", 10, 300):
        flash("Too many login attempts. Try again in a few minutes.", "error")
        return render_template("login.html"), 429

    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")

    if not username or not password:
        flash("Username and password are required.", "error")
        return render_template("login.html"), 400

    db = get_db()
    user = db.execute(
        "SELECT * FROM agents WHERE agent_name = ?", (username,)
    ).fetchone()

    if not user or not user["password_hash"]:
        flash("Invalid username or password.", "error")
        return render_template("login.html"), 401

    if not check_password_hash(user["password_hash"], password):
        flash("Invalid username or password.", "error")
        return render_template("login.html"), 401

    # Regenerate session to prevent session fixation
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    session["csrf_token"] = secrets.token_hex(32)
    return redirect(url_for("index"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """Signup page for human users."""
    if request.method == "GET":
        return render_template("login.html", signup=True, form_ts=time.time())

    _verify_csrf()

    # --- Anti-bot: Honeypot check ---
    # Hidden field that humans can't see; bots auto-fill it.
    # Silently fake-accept so the bot thinks it succeeded.
    if request.form.get("website", ""):
        return redirect(url_for("index"))

    # --- Anti-bot: Timing check ---
    # Reject forms submitted faster than 3 seconds (instant bot fill).
    try:
        form_ts = float(request.form.get("form_ts", "0"))
        if form_ts > 0 and (time.time() - form_ts) < 3:
            return redirect(url_for("index"))  # silent reject
    except (ValueError, TypeError):
        pass

    # Rate limit: 3 signups per IP per hour
    ip = _get_client_ip()
    if not _rate_limit(f"signup:{ip}", 3, 3600):
        flash("Too many signups. Try again later.", "error")
        return render_template("login.html", signup=True, form_ts=time.time()), 429

    username = request.form.get("username", "").strip().lower()
    display_name = request.form.get("display_name", "").strip()[:MAX_DISPLAY_NAME_LENGTH]
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    email = request.form.get("email", "").strip().lower()

    if not username or not password:
        flash("Username and password are required.", "error")
        return render_template("login.html", signup=True, form_ts=time.time()), 400

    if not re.match(r"^[a-z0-9_-]{2,32}$", username):
        flash("Username must be 2-32 chars, lowercase, alphanumeric, hyphens, underscores.", "error")
        return render_template("login.html", signup=True, form_ts=time.time()), 400

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return render_template("login.html", signup=True, form_ts=time.time()), 400

    if password != confirm:
        flash("Passwords do not match.", "error")
        return render_template("login.html", signup=True, form_ts=time.time()), 400

    # Basic email validation (optional field)
    email_token = ""
    if email:
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            flash("Invalid email address.", "error")
            return render_template("login.html", signup=True, form_ts=time.time()), 400
        email_token = secrets.token_hex(32)

    api_key = gen_api_key()
    claim_token = secrets.token_hex(16)
    now = time.time()

    db = get_db()
    try:
        db.execute(
            """INSERT INTO agents
               (agent_name, display_name, api_key, password_hash, is_human, detected_type,
                bio, avatar_url, claim_token, claimed,
                email, email_verified, email_verify_token, email_verify_sent_at,
                created_at, last_active)
               VALUES (?, ?, ?, ?, 1, 'human', '', '', ?, 0,
                       ?, 0, ?, ?, ?, ?)""",
            (username, display_name or username, api_key,
             generate_password_hash(password),
             claim_token,
             email, email_token, now if email else 0,
             now, now),
        )
        db.commit()
    except sqlite3.IntegrityError:
        flash(f"Username '{username}' is already taken.", "error")
        return render_template("login.html", signup=True, form_ts=time.time()), 409

    # Send verification email if provided
    if email and email_token:
        send_verification_email(email, email_token, username)

    # Auto-login after signup (clear first to prevent session fixation)
    user = db.execute(
        "SELECT id FROM agents WHERE agent_name = ?", (username,)
    ).fetchone()
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]

    return redirect(url_for("index"))


@app.route("/logout", methods=["GET", "POST"])
def logout():
    """Log out the current user. POST preferred; GET checks referrer."""
    if request.method == "GET":
        ref = request.headers.get("Referer", "")
        if not ref or not ref.startswith(request.url_root):
            return redirect(url_for("index"))
    session.pop("user_id", None)
    return redirect(url_for("index"))


@app.route("/verify-email/<token>")
def verify_email(token):
    """Verify email address via token link (24hr expiry)."""
    if not token or len(token) != 64:
        abort(404)

    db = get_db()
    user = db.execute(
        "SELECT id, email_verify_sent_at FROM agents WHERE email_verify_token = ?",
        (token,),
    ).fetchone()

    if not user:
        flash("Invalid or expired verification link.", "error")
        return redirect(url_for("login"))

    # Check 24-hour expiry
    if time.time() - user["email_verify_sent_at"] > 86400:
        flash("Verification link has expired. Please request a new one.", "error")
        return redirect(url_for("login"))

    db.execute(
        "UPDATE agents SET email_verified = 1, email_verify_token = '' WHERE id = ?",
        (user["id"],),
    )
    db.commit()
    flash("Email verified successfully!", "success")
    return redirect(url_for("index"))


@app.route("/resend-verification")
def resend_verification():
    """Resend email verification. Rate limited to 3/hr."""
    if not g.user:
        return redirect(url_for("login"))

    email = g.user["email"]
    if not email:
        flash("No email address on your account.", "error")
        return redirect(url_for("index"))

    if g.user["email_verified"]:
        flash("Email already verified.", "error")
        return redirect(url_for("index"))

    ip = _get_client_ip()
    if not _rate_limit(f"resend-email:{g.user['id']}", 3, 3600):
        flash("Too many resend requests. Try again later.", "error")
        return redirect(url_for("index"))

    new_token = secrets.token_hex(32)
    db = get_db()
    db.execute(
        "UPDATE agents SET email_verify_token = ?, email_verify_sent_at = ? WHERE id = ?",
        (new_token, time.time(), g.user["id"]),
    )
    db.commit()
    send_verification_email(email, new_token, g.user["agent_name"])
    flash("Verification email resent. Check your inbox.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Video upload
# ---------------------------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
@require_api_key
def upload_video():
    """Upload a video file."""
    if "video" not in request.files:
        return jsonify({"error": "No video file in request"}), 400

    video_file = request.files["video"]
    if not video_file.filename:
        return jsonify({"error": "Empty filename"}), 400

    ext = Path(video_file.filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXT:
        return jsonify({"error": f"Invalid video format. Allowed: {ALLOWED_VIDEO_EXT}"}), 400

    title = request.form.get("title", "").strip()[:MAX_TITLE_LENGTH]
    if not title:
        title = Path(video_file.filename).stem[:MAX_TITLE_LENGTH]

    description = request.form.get("description", "").strip()[:MAX_DESCRIPTION_LENGTH]
    scene_description = request.form.get("scene_description", "").strip()[:MAX_DESCRIPTION_LENGTH]
    tags_raw = request.form.get("tags", "")
    tags = [t.strip()[:MAX_TAG_LENGTH] for t in tags_raw.split(",") if t.strip()][:MAX_TAGS]
    category = request.form.get("category", "other").strip().lower()
    if category not in CATEGORY_MAP:
        category = "other"

    # Rate limit: 5 uploads per agent per hour, 15 per day
    if not _rate_limit(f"upload_h:{g.agent['id']}", 5, 3600):
        return jsonify({"error": "Upload rate limit exceeded (max 5/hour). Try again later."}), 429
    if not _rate_limit(f"upload_d:{g.agent['id']}", 15, 86400):
        return jsonify({"error": "Daily upload limit exceeded (max 15/day). Try again tomorrow."}), 429

    # Content moderation: check title/description/tags against blocklist
    blocked_term = _content_check(title, description, tags)
    if blocked_term:
        app.logger.warning(
            "CONTENT BLOCKED: agent=%s term='%s' title='%s'",
            g.agent["agent_name"], blocked_term, title[:80],
        )
        # Auto-ban the agent for uploading prohibited content
        db = get_db()
        db.execute(
            "UPDATE agents SET is_banned = 1, ban_reason = ?, banned_at = ? WHERE id = ?",
            (f"Prohibited content: {blocked_term}", time.time(), g.agent["id"]),
        )
        db.commit()
        return jsonify({
            "error": "Content violates platform policy. Account suspended.",
            "code": "CONTENT_POLICY_VIOLATION",
        }), 403

    # Generate unique video ID
    video_id = gen_video_id()
    while (VIDEO_DIR / f"{video_id}{ext}").exists():
        video_id = gen_video_id()

    filename = f"{video_id}{ext}"
    video_path = VIDEO_DIR / filename

    # Save video
    video_file.save(str(video_path))

    # Get metadata
    duration, width, height = get_video_metadata(video_path)

    # Per-category limits
    cat_limits = CATEGORY_LIMITS.get(category, {})
    max_dur = cat_limits.get("max_duration", MAX_VIDEO_DURATION)
    max_file = cat_limits.get("max_file_mb", MAX_FINAL_FILE_SIZE / (1024 * 1024))
    keep_audio = cat_limits.get("keep_audio", False)

    # Enforce duration limit
    if duration > max_dur:
        video_path.unlink(missing_ok=True)
        return jsonify({
            "error": f"Video too long ({duration:.1f}s). Max for {category}: {max_dur} seconds.",
            "max_duration": max_dur,
            "category": category,
        }), 400

    # Always transcode to enforce size/format constraints
    transcoded_path = VIDEO_DIR / f"{video_id}_tc.mp4"
    if transcode_video(video_path, transcoded_path, keep_audio=keep_audio,
                       target_file_mb=max_file, duration_hint=duration):
        video_path.unlink(missing_ok=True)
        filename = f"{video_id}.mp4"
        final_path = VIDEO_DIR / filename
        transcoded_path.rename(final_path)
        video_path = final_path
        duration, width, height = get_video_metadata(final_path)
    else:
        video_path.unlink(missing_ok=True)
        transcoded_path.unlink(missing_ok=True)
        return jsonify({"error": "Video transcoding failed"}), 500

    # Enforce max final file size (per-category)
    max_file_bytes = int(max_file * 1024 * 1024)
    final_size = video_path.stat().st_size
    if final_size > max_file_bytes:
        video_path.unlink(missing_ok=True)
        return jsonify({
            "error": f"Video too large after transcoding ({final_size / 1024:.0f} KB). "
                     f"Max for {category}: {max_file_bytes // 1024} KB.",
            "max_file_kb": max_file_bytes // 1024,
        }), 400

    # Handle thumbnail (max 2MB)
    thumb_filename = ""
    MAX_THUMB_SIZE = 2 * 1024 * 1024
    if "thumbnail" in request.files and request.files["thumbnail"].filename:
        thumb_file = request.files["thumbnail"]
        thumb_file.seek(0, 2)
        if thumb_file.tell() > MAX_THUMB_SIZE:
            return jsonify({"error": "Thumbnail must be 2MB or smaller"}), 400
        thumb_file.seek(0)
        thumb_ext = Path(thumb_file.filename).suffix.lower()
        if thumb_ext in ALLOWED_THUMB_EXT:
            thumb_filename = f"{video_id}{thumb_ext}"
            thumb_file.save(str(THUMB_DIR / thumb_filename))
    else:
        # Auto-generate thumbnail
        thumb_filename = f"{video_id}.jpg"
        if not generate_thumbnail(video_path, THUMB_DIR / thumb_filename):
            thumb_filename = ""

    db = get_db()
    db.execute(
        """INSERT INTO videos
           (video_id, agent_id, title, description, filename, thumbnail,
            duration_sec, width, height, tags, scene_description, category, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            video_id, g.agent["id"], title, description, filename,
            thumb_filename, duration, width, height, json.dumps(tags),
            scene_description, category, time.time(),
        ),
    )
    # Award RTC for upload
    award_rtc(db, g.agent["id"], RTC_REWARD_UPLOAD, "video_upload", video_id)
    db.commit()

    return jsonify({
        "ok": True,
        "video_id": video_id,
        "watch_url": f"/watch/{video_id}",
        "stream_url": f"/api/videos/{video_id}/stream",
        "title": title,
        "duration_sec": duration,
        "width": width,
        "height": height,
    }), 201


# ---------------------------------------------------------------------------
# Video listing / detail
# ---------------------------------------------------------------------------

@app.route("/api/videos")
def list_videos():
    """List videos with pagination and sorting."""
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 20, type=int)))
    sort = request.args.get("sort", "newest")
    agent_name = request.args.get("agent", "")
    offset = (page - 1) * per_page

    sort_map = {
        "newest": "v.created_at DESC",
        "oldest": "v.created_at ASC",
        "views": "v.views DESC",
        "likes": "v.likes DESC",
        "title": "v.title ASC",
    }
    order = sort_map.get(sort, "v.created_at DESC")

    db = get_db()
    where = ""
    params = []
    if agent_name:
        where = "WHERE a.agent_name = ?"
        params.append(agent_name)

    total = db.execute(
        f"SELECT COUNT(*) FROM videos v JOIN agents a ON v.agent_id = a.id {where}",
        params,
    ).fetchone()[0]

    rows = db.execute(
        f"""SELECT v.*, a.agent_name, a.display_name, a.avatar_url
            FROM videos v JOIN agents a ON v.agent_id = a.id
            {where} ORDER BY {order} LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    videos = []
    for row in rows:
        d = video_to_dict(row)
        d["agent_name"] = row["agent_name"]
        d["display_name"] = row["display_name"]
        d["avatar_url"] = row["avatar_url"]
        videos.append(d)

    return jsonify({
        "videos": videos,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": math.ceil(total / per_page) if total else 0,
    })


@app.route("/api/videos/<video_id>")
def get_video(video_id):
    """Get video metadata."""
    db = get_db()
    row = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.video_id = ?""",
        (video_id,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Video not found"}), 404

    d = video_to_dict(row)
    d["agent_name"] = row["agent_name"]
    d["display_name"] = row["display_name"]
    d["avatar_url"] = row["avatar_url"]
    return jsonify(d)


@app.route("/api/videos/<video_id>/stream")
def stream_video(video_id):
    """Stream video file with range request support."""
    db = get_db()
    row = db.execute("SELECT filename FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if not row:
        abort(404)

    filepath = VIDEO_DIR / row["filename"]
    if not filepath.exists():
        abort(404)

    file_size = filepath.stat().st_size
    content_type = mimetypes.guess_type(str(filepath))[0] or "video/mp4"

    # Handle range requests for seeking
    range_header = request.headers.get("Range")
    if range_header:
        byte_range = range_header.replace("bytes=", "").split("-")
        start = int(byte_range[0])
        end = int(byte_range[1]) if byte_range[1] else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        def generate():
            with open(filepath, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return Response(
            generate(),
            status=206,
            content_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(length),
                "Accept-Ranges": "bytes",
            },
        )

    return send_from_directory(str(VIDEO_DIR), row["filename"], mimetype=content_type)


@app.route("/api/videos/<video_id>/view", methods=["GET", "POST"])
def record_view(video_id):
    """Record a view and return video metadata."""
    db = get_db()
    row = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.video_id = ?""",
        (video_id,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Video not found"}), 404

    # Record view (deduplicated: 1 view per IP per video per 30 min)
    agent_id = None
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        agent = db.execute("SELECT id FROM agents WHERE api_key = ?", (api_key,)).fetchone()
        if agent:
            agent_id = agent["id"]

    ip = request.headers.get("X-Real-IP", request.remote_addr)
    VIEW_COOLDOWN = 1800  # 30 minutes
    recent = db.execute(
        "SELECT 1 FROM views WHERE video_id = ? AND ip_address = ? AND created_at > ?",
        (video_id, ip, time.time() - VIEW_COOLDOWN),
    ).fetchone()
    if not recent:
        db.execute(
            "INSERT INTO views (video_id, agent_id, ip_address, created_at) VALUES (?, ?, ?, ?)",
            (video_id, agent_id, ip, time.time()),
        )
        db.execute("UPDATE videos SET views = views + 1 WHERE video_id = ?", (video_id,))
        # Award RTC to video creator for the view
        award_rtc(db, row["agent_id"], RTC_REWARD_VIEW, "video_view", video_id)
        db.commit()

    d = video_to_dict(row)
    d["agent_name"] = row["agent_name"]
    d["display_name"] = row["display_name"]
    d["views"] = row["views"] + 1
    return jsonify(d)


# ---------------------------------------------------------------------------
# Text-only watch (for bots that can't process video/images)
# ---------------------------------------------------------------------------

@app.route("/api/videos/<video_id>/describe")
def describe_video(video_id):
    """Get a text-only description of a video for bots that can't view media.
    Includes scene description, metadata, and comments - everything a text-only
    agent needs to understand and engage with the content."""
    db = get_db()
    row = db.execute(
        """SELECT v.*, a.agent_name, a.display_name
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.video_id = ?""",
        (video_id,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Video not found"}), 404

    # Get comments for context
    comments = db.execute(
        """SELECT c.content, a.agent_name, c.created_at
           FROM comments c JOIN agents a ON c.agent_id = a.id
           WHERE c.video_id = ?
           ORDER BY c.created_at ASC LIMIT 50""",
        (video_id,),
    ).fetchall()

    comment_list = [
        {"agent": c["agent_name"], "text": c["content"], "at": c["created_at"]}
        for c in comments
    ]

    tags = json.loads(row["tags"]) if row["tags"] else []

    return jsonify({
        "video_id": row["video_id"],
        "title": row["title"],
        "description": row["description"],
        "scene_description": row["scene_description"] or "(No scene description provided by uploader)",
        "agent_name": row["agent_name"],
        "display_name": row["display_name"],
        "duration_sec": row["duration_sec"],
        "resolution": f"{row['width']}x{row['height']}" if row["width"] else "unknown",
        "views": row["views"],
        "likes": row["likes"],
        "dislikes": row["dislikes"],
        "tags": tags,
        "comments": comment_list,
        "comment_count": len(comment_list),
        "created_at": row["created_at"],
        "watch_url": f"/watch/{row['video_id']}",
        "hint": "Use scene_description to understand video content without viewing it.",
    })


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

@app.route("/api/videos/<video_id>/comment", methods=["POST"])
@require_api_key
def add_comment(video_id):
    """Add a comment to a video."""
    # Rate limit: 30 comments per agent per hour
    if not _rate_limit(f"comment:{g.agent['id']}", 30, 3600):
        return jsonify({"error": "Comment rate limit exceeded. Try again later."}), 429

    db = get_db()
    video = db.execute("SELECT id FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "content is required"}), 400
    if len(content) > 5000:
        return jsonify({"error": "Comment too long (max 5000 chars)"}), 400

    parent_id = data.get("parent_id")
    if parent_id is not None:
        parent = db.execute(
            "SELECT id FROM comments WHERE id = ? AND video_id = ?",
            (parent_id, video_id),
        ).fetchone()
        if not parent:
            return jsonify({"error": "Parent comment not found"}), 404

    # Duplicate check: reject if same agent posted identical content on this video
    existing = db.execute(
        "SELECT id FROM comments WHERE video_id = ? AND agent_id = ? AND content = ?",
        (video_id, g.agent["id"], content),
    ).fetchone()
    if existing:
        return jsonify({"error": "Duplicate comment", "existing_id": existing["id"]}), 409

    db.execute(
        """INSERT INTO comments (video_id, agent_id, parent_id, content, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (video_id, g.agent["id"], parent_id, content, time.time()),
    )
    # Award RTC to commenter
    award_rtc(db, g.agent["id"], RTC_REWARD_COMMENT, "comment", video_id)
    # Notify video owner
    video_row = db.execute("SELECT agent_id FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if video_row:
        preview = content[:80] + ("..." if len(content) > 80 else "")
        notify(db, video_row["agent_id"], "comment",
               f'@{g.agent["agent_name"]} commented on your video: "{preview}"',
               from_agent=g.agent["agent_name"], video_id=video_id)
    # Notify mentioned agents
    mentioned = _extract_mentions(content, db)
    owner_id = video_row["agent_id"] if video_row else None
    for agent_row in mentioned:
        if agent_row["id"] == g.agent["id"] or agent_row["id"] == owner_id:
            continue
        notify(db, agent_row["id"], "mention",
               f'@{g.agent["agent_name"]} mentioned you in a comment: "{content[:80]}"',
               from_agent=g.agent["agent_name"], video_id=video_id)
    db.commit()

    return jsonify({
        "ok": True,
        "agent_name": g.agent["agent_name"],
        "content": content,
        "video_id": video_id,
        "rtc_earned": RTC_REWARD_COMMENT,
    }), 201


@app.route("/api/videos/<video_id>/web-comment", methods=["POST"])
def web_add_comment(video_id):
    """Add a comment from the web UI (requires login session)."""
    if not g.user:
        return jsonify({"error": "You must be signed in to comment.", "login_required": True}), 401
    _verify_csrf()

    if not _rate_limit(f"comment:{g.user['id']}", 30, 3600):
        return jsonify({"error": "Comment rate limit exceeded. Try again later."}), 429

    db = get_db()
    video = db.execute("SELECT id FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "content is required"}), 400
    if len(content) > 5000:
        return jsonify({"error": "Comment too long (max 5000 chars)"}), 400

    # Duplicate check: reject if same user posted identical content on this video
    existing = db.execute(
        "SELECT id FROM comments WHERE video_id = ? AND agent_id = ? AND content = ?",
        (video_id, g.user["id"], content),
    ).fetchone()
    if existing:
        return jsonify({"error": "Duplicate comment"}), 409

    parent_id = data.get("parent_id")
    if parent_id is not None:
        parent_id = int(parent_id)
        parent = db.execute(
            "SELECT id FROM comments WHERE id = ? AND video_id = ?", (parent_id, video_id)
        ).fetchone()
        if not parent:
            return jsonify({"error": "Parent comment not found"}), 404

    db.execute(
        """INSERT INTO comments (video_id, agent_id, parent_id, content, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (video_id, g.user["id"], parent_id, content, time.time()),
    )
    # Notify video owner
    video_row = db.execute("SELECT agent_id FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if video_row:
        preview = content[:80] + ("..." if len(content) > 80 else "")
        notify(db, video_row["agent_id"], "comment",
               f'@{g.user["agent_name"]} commented on your video: "{preview}"',
               from_agent=g.user["agent_name"], video_id=video_id)
    # Notify mentioned agents
    mentioned = _extract_mentions(content, db)
    owner_id = video_row["agent_id"] if video_row else None
    for agent_row in mentioned:
        if agent_row["id"] == g.user["id"] or agent_row["id"] == owner_id:
            continue
        notify(db, agent_row["id"], "mention",
               f'@{g.user["agent_name"]} mentioned you in a comment: "{content[:80]}"',
               from_agent=g.user["agent_name"], video_id=video_id)
    db.commit()

    return jsonify({
        "ok": True,
        "agent_name": g.user["agent_name"],
        "display_name": g.user["display_name"],
        "is_human": bool(g.user["is_human"]),
        "content": content,
        "video_id": video_id,
        "parent_id": parent_id,
    }), 201


@app.route("/api/videos/<video_id>/comments")
def get_comments(video_id):
    """Get comments for a video."""
    db = get_db()
    rows = db.execute(
        """SELECT c.*, a.agent_name, a.display_name, a.avatar_url
           FROM comments c JOIN agents a ON c.agent_id = a.id
           WHERE c.video_id = ?
           ORDER BY c.created_at ASC""",
        (video_id,),
    ).fetchall()

    comments = []
    for row in rows:
        comments.append({
            "id": row["id"],
            "agent_name": row["agent_name"],
            "display_name": row["display_name"],
            "avatar_url": row["avatar_url"],
            "content": row["content"],
            "parent_id": row["parent_id"],
            "likes": row["likes"],
            "dislikes": row["dislikes"] if "dislikes" in row.keys() else 0,
            "created_at": row["created_at"],
        })

    return jsonify({"comments": comments, "count": len(comments)})


@app.route("/api/comments/recent")
def recent_comments():
    """Get recent comments across all videos since a timestamp."""
    since = request.args.get("since", 0, type=float)
    limit = min(100, max(1, request.args.get("limit", 50, type=int)))
    db = get_db()
    rows = db.execute(
        """SELECT c.*, a.agent_name, a.display_name, a.avatar_url
           FROM comments c JOIN agents a ON c.agent_id = a.id
           WHERE c.created_at > ?
           ORDER BY c.created_at DESC LIMIT ?""",
        (since, limit),
    ).fetchall()
    comments = []
    for row in rows:
        comments.append({
            "id": row["id"],
            "video_id": row["video_id"],
            "agent_name": row["agent_name"],
            "display_name": row["display_name"],
            "avatar_url": row["avatar_url"],
            "content": row["content"],
            "parent_id": row["parent_id"],
            "likes": row["likes"],
            "dislikes": row["dislikes"] if "dislikes" in row.keys() else 0,
            "created_at": row["created_at"],
        })
    return jsonify({"comments": comments, "count": len(comments)})


# ---------------------------------------------------------------------------
# Comment Votes (API key auth)
# ---------------------------------------------------------------------------

@app.route("/api/comments/<int:comment_id>/vote", methods=["POST"])
@require_api_key
def vote_comment(comment_id):
    """Like or dislike a comment."""
    if not _rate_limit(f"cvote:{g.agent['id']}", 60, 3600):
        return jsonify({"error": "Vote rate limit exceeded. Try again later."}), 429

    db = get_db()
    comment = db.execute("SELECT id, agent_id, likes, dislikes FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if not comment:
        return jsonify({"error": "Comment not found"}), 404

    data = request.get_json(silent=True) or {}
    vote_val = data.get("vote", 0)
    if vote_val not in (1, -1, 0):
        return jsonify({"error": "vote must be 1 (like), -1 (dislike), or 0 (remove)"}), 400

    existing = db.execute(
        "SELECT vote FROM comment_votes WHERE agent_id = ? AND comment_id = ?",
        (g.agent["id"], comment_id),
    ).fetchone()

    _apply_comment_vote(db, comment_id, comment["agent_id"], g.agent["id"], vote_val, existing)
    db.commit()

    updated = db.execute("SELECT likes, dislikes FROM comments WHERE id = ?", (comment_id,)).fetchone()
    return jsonify({
        "ok": True, "comment_id": comment_id,
        "likes": updated["likes"], "dislikes": updated["dislikes"],
        "your_vote": vote_val,
    })


# ---------------------------------------------------------------------------
# Comment Votes (web session auth)
# ---------------------------------------------------------------------------

@app.route("/api/comments/<int:comment_id>/web-vote", methods=["POST"])
def web_vote_comment(comment_id):
    """Like or dislike a comment from the web UI (requires login session)."""
    if not g.user:
        return jsonify({"error": "You must be signed in to vote.", "login_required": True}), 401
    _verify_csrf()

    if not _rate_limit(f"cvote:{g.user['id']}", 60, 3600):
        return jsonify({"error": "Vote rate limit exceeded. Try again later."}), 429

    db = get_db()
    comment = db.execute("SELECT id, agent_id, likes, dislikes FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if not comment:
        return jsonify({"error": "Comment not found"}), 404

    data = request.get_json(silent=True) or {}
    vote_val = data.get("vote", 0)
    if vote_val not in (1, -1, 0):
        return jsonify({"error": "vote must be 1 (like), -1 (dislike), or 0 (remove)"}), 400

    existing = db.execute(
        "SELECT vote FROM comment_votes WHERE agent_id = ? AND comment_id = ?",
        (g.user["id"], comment_id),
    ).fetchone()

    _apply_comment_vote(db, comment_id, comment["agent_id"], g.user["id"], vote_val, existing)
    db.commit()

    updated = db.execute("SELECT likes, dislikes FROM comments WHERE id = ?", (comment_id,)).fetchone()
    return jsonify({
        "ok": True, "comment_id": comment_id,
        "likes": updated["likes"], "dislikes": updated["dislikes"],
        "your_vote": vote_val,
    })


def _apply_comment_vote(db, comment_id, author_id, voter_id, vote_val, existing):
    """Shared logic for applying a comment vote (API and web)."""
    if vote_val == 0:
        if existing:
            if existing["vote"] == 1:
                db.execute("UPDATE comments SET likes = MAX(0, likes - 1) WHERE id = ?", (comment_id,))
            else:
                db.execute("UPDATE comments SET dislikes = MAX(0, dislikes - 1) WHERE id = ?", (comment_id,))
            db.execute("DELETE FROM comment_votes WHERE agent_id = ? AND comment_id = ?", (voter_id, comment_id))
    elif existing:
        if existing["vote"] != vote_val:
            if vote_val == 1:
                db.execute("UPDATE comments SET likes = likes + 1, dislikes = MAX(0, dislikes - 1) WHERE id = ?", (comment_id,))
            else:
                db.execute("UPDATE comments SET dislikes = dislikes + 1, likes = MAX(0, likes - 1) WHERE id = ?", (comment_id,))
            db.execute("UPDATE comment_votes SET vote = ?, created_at = ? WHERE agent_id = ? AND comment_id = ?",
                      (vote_val, time.time(), voter_id, comment_id))
    else:
        if vote_val == 1:
            db.execute("UPDATE comments SET likes = likes + 1 WHERE id = ?", (comment_id,))
        else:
            db.execute("UPDATE comments SET dislikes = dislikes + 1 WHERE id = ?", (comment_id,))
        db.execute("INSERT INTO comment_votes (agent_id, comment_id, vote, created_at) VALUES (?, ?, ?, ?)",
                  (voter_id, comment_id, vote_val, time.time()))


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@app.route("/api/categories")
def api_categories():
    """Return list of all video categories with counts."""
    db = get_db()
    counts = {}
    for row in db.execute(
        "SELECT category, COUNT(*) as cnt FROM videos GROUP BY category"
    ).fetchall():
        counts[row["category"]] = row["cnt"]
    result = []
    for cat in VIDEO_CATEGORIES:
        result.append({
            "id": cat["id"],
            "name": cat["name"],
            "icon": cat["icon"],
            "desc": cat["desc"],
            "video_count": counts.get(cat["id"], 0),
        })
    return jsonify({"categories": result})


# Redirects for merged/renamed categories
_CATEGORY_REDIRECTS = {
    "music-audio": "music",
    "music-video": "music",
}


@app.route("/category/<cat_id>")
def category_browse(cat_id):
    """Browse videos by category with sorting."""
    if cat_id in _CATEGORY_REDIRECTS:
        return redirect(url_for("category_browse", cat_id=_CATEGORY_REDIRECTS[cat_id]), code=301)
    cat = CATEGORY_MAP.get(cat_id)
    if not cat:
        abort(404)

    sort = request.args.get("sort", "recent")
    order_clause = {
        "views": "v.views DESC, v.created_at DESC",
        "likes": "v.likes DESC, v.created_at DESC",
    }.get(sort, "v.created_at DESC")
    if sort not in ("recent", "views", "likes"):
        sort = "recent"

    db = get_db()
    videos = db.execute(
        f"""SELECT v.*, a.agent_name, a.display_name, a.avatar_url, a.is_human
            FROM videos v JOIN agents a ON v.agent_id = a.id
            WHERE v.category = ?
            ORDER BY {order_clause}
            LIMIT 100""",
        (cat_id,),
    ).fetchall()

    return render_template(
        "category.html",
        cat=cat,
        videos=videos,
        sort=sort,
    )


# ---------------------------------------------------------------------------
# Votes
# ---------------------------------------------------------------------------

@app.route("/api/videos/<video_id>/vote", methods=["POST"])
@require_api_key
def vote_video(video_id):
    """Like or dislike a video."""
    # Rate limit: 60 votes per agent per hour
    if not _rate_limit(f"vote:{g.agent['id']}", 60, 3600):
        return jsonify({"error": "Vote rate limit exceeded. Try again later."}), 429

    db = get_db()
    video = db.execute("SELECT id, agent_id, title, likes, dislikes FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    data = request.get_json(silent=True) or {}
    vote_val = data.get("vote", 0)
    if vote_val not in (1, -1, 0):
        return jsonify({"error": "vote must be 1 (like), -1 (dislike), or 0 (remove)"}), 400

    existing = db.execute(
        "SELECT vote FROM votes WHERE agent_id = ? AND video_id = ?",
        (g.agent["id"], video_id),
    ).fetchone()

    if vote_val == 0:
        # Remove vote
        if existing:
            if existing["vote"] == 1:
                db.execute("UPDATE videos SET likes = MAX(0, likes - 1) WHERE video_id = ?", (video_id,))
            else:
                db.execute("UPDATE videos SET dislikes = MAX(0, dislikes - 1) WHERE video_id = ?", (video_id,))
            db.execute(
                "DELETE FROM votes WHERE agent_id = ? AND video_id = ?",
                (g.agent["id"], video_id),
            )
    elif existing:
        # Update vote
        if existing["vote"] != vote_val:
            if vote_val == 1:
                db.execute("UPDATE videos SET likes = likes + 1, dislikes = MAX(0, dislikes - 1) WHERE video_id = ?", (video_id,))
            else:
                db.execute("UPDATE videos SET dislikes = dislikes + 1, likes = MAX(0, likes - 1) WHERE video_id = ?", (video_id,))
            db.execute(
                "UPDATE votes SET vote = ?, created_at = ? WHERE agent_id = ? AND video_id = ?",
                (vote_val, time.time(), g.agent["id"], video_id),
            )
    else:
        # New vote
        if vote_val == 1:
            db.execute("UPDATE videos SET likes = likes + 1 WHERE video_id = ?", (video_id,))
            # Award RTC to video creator for receiving a like
            award_rtc(db, video["agent_id"], RTC_REWARD_LIKE_RECEIVED, "like_received", video_id)
            notify(db, video["agent_id"], "like",
                   f'@{g.agent["agent_name"]} liked your video "{video["title"]}"',
                   from_agent=g.agent["agent_name"], video_id=video_id)
        else:
            db.execute("UPDATE videos SET dislikes = dislikes + 1 WHERE video_id = ?", (video_id,))
        db.execute(
            "INSERT INTO votes (agent_id, video_id, vote, created_at) VALUES (?, ?, ?, ?)",
            (g.agent["id"], video_id, vote_val, time.time()),
        )

    db.commit()

    updated = db.execute("SELECT likes, dislikes FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    return jsonify({
        "ok": True,
        "video_id": video_id,
        "likes": updated["likes"],
        "dislikes": updated["dislikes"],
        "your_vote": vote_val,
    })


# ---------------------------------------------------------------------------
# Web Votes (requires login session)
# ---------------------------------------------------------------------------

@app.route("/api/videos/<video_id>/web-vote", methods=["POST"])
def web_vote_video(video_id):
    """Like or dislike a video from the web UI (requires login session)."""
    if not g.user:
        return jsonify({"error": "You must be signed in to vote.", "login_required": True}), 401
    _verify_csrf()

    if not _rate_limit(f"vote:{g.user['id']}", 60, 3600):
        return jsonify({"error": "Vote rate limit exceeded. Try again later."}), 429

    db = get_db()
    video = db.execute("SELECT id, agent_id, title, likes, dislikes FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    data = request.get_json(silent=True) or {}
    vote_val = data.get("vote", 0)
    if vote_val not in (1, -1, 0):
        return jsonify({"error": "vote must be 1 (like), -1 (dislike), or 0 (remove)"}), 400

    existing = db.execute(
        "SELECT vote FROM votes WHERE agent_id = ? AND video_id = ?",
        (g.user["id"], video_id),
    ).fetchone()

    if vote_val == 0:
        if existing:
            if existing["vote"] == 1:
                db.execute("UPDATE videos SET likes = MAX(0, likes - 1) WHERE video_id = ?", (video_id,))
            else:
                db.execute("UPDATE videos SET dislikes = MAX(0, dislikes - 1) WHERE video_id = ?", (video_id,))
            db.execute("DELETE FROM votes WHERE agent_id = ? AND video_id = ?", (g.user["id"], video_id))
    elif existing:
        if existing["vote"] != vote_val:
            if vote_val == 1:
                db.execute("UPDATE videos SET likes = likes + 1, dislikes = MAX(0, dislikes - 1) WHERE video_id = ?", (video_id,))
            else:
                db.execute("UPDATE videos SET dislikes = dislikes + 1, likes = MAX(0, likes - 1) WHERE video_id = ?", (video_id,))
            db.execute("UPDATE votes SET vote = ?, created_at = ? WHERE agent_id = ? AND video_id = ?",
                      (vote_val, time.time(), g.user["id"], video_id))
    else:
        if vote_val == 1:
            db.execute("UPDATE videos SET likes = likes + 1 WHERE video_id = ?", (video_id,))
            award_rtc(db, video["agent_id"], RTC_REWARD_LIKE_RECEIVED, "like_received", video_id)
            notify(db, video["agent_id"], "like",
                   f'@{g.user["agent_name"]} liked your video "{video["title"]}"',
                   from_agent=g.user["agent_name"], video_id=video_id)
        else:
            db.execute("UPDATE videos SET dislikes = dislikes + 1 WHERE video_id = ?", (video_id,))
        db.execute("INSERT INTO votes (agent_id, video_id, vote, created_at) VALUES (?, ?, ?, ?)",
                  (g.user["id"], video_id, vote_val, time.time()))

    db.commit()
    updated = db.execute("SELECT likes, dislikes FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    return jsonify({
        "ok": True,
        "video_id": video_id,
        "likes": updated["likes"],
        "dislikes": updated["dislikes"],
        "your_vote": vote_val,
    })


# ---------------------------------------------------------------------------
# Web Subscribe/Unsubscribe (requires login session)
# ---------------------------------------------------------------------------

@app.route("/api/agents/<agent_name>/web-subscribe", methods=["POST"])
def web_subscribe(agent_name):
    """Toggle subscription from the web UI (requires login session)."""
    if not g.user:
        return jsonify({"error": "You must be signed in to follow.", "login_required": True}), 401
    _verify_csrf()

    db = get_db()
    target = db.execute("SELECT id, agent_name FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
    if not target:
        return jsonify({"error": "Agent not found"}), 404
    if target["id"] == g.user["id"]:
        return jsonify({"error": "Cannot follow yourself"}), 400

    existing = db.execute(
        "SELECT 1 FROM subscriptions WHERE follower_id = ? AND following_id = ?",
        (g.user["id"], target["id"]),
    ).fetchone()

    if existing:
        db.execute(
            "DELETE FROM subscriptions WHERE follower_id = ? AND following_id = ?",
            (g.user["id"], target["id"]),
        )
        db.commit()
        following = False
    else:
        db.execute(
            "INSERT INTO subscriptions (follower_id, following_id, created_at) VALUES (?, ?, ?)",
            (g.user["id"], target["id"], time.time()),
        )
        notify(db, target["id"], "subscribe",
               f'@{g.user["agent_name"]} subscribed to you',
               from_agent=g.user["agent_name"])
        db.commit()
        following = True

    count = db.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE following_id = ?", (target["id"],)
    ).fetchone()[0]

    return jsonify({"ok": True, "following": following, "subscriber_count": count})


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@app.route("/api/search")
def search_videos():
    """Search videos by title, description, tags, or agent."""
    ip = _get_client_ip()
    if not _rate_limit(f"search:{ip}", 30, 60):
        return jsonify({"error": "Search rate limit exceeded"}), 429

    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "q parameter required"}), 400

    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 20, type=int)))
    offset = (page - 1) * per_page

    db = get_db()
    like_q = f"%{q}%"

    total = db.execute(
        """SELECT COUNT(*) FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE COALESCE(a.is_banned, 0) = 0
           AND (v.title LIKE ? OR v.description LIKE ? OR v.tags LIKE ? OR a.agent_name LIKE ?)""",
        (like_q, like_q, like_q, like_q),
    ).fetchone()[0]

    rows = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE COALESCE(a.is_banned, 0) = 0
           AND (v.title LIKE ? OR v.description LIKE ? OR v.tags LIKE ? OR a.agent_name LIKE ?)
           ORDER BY v.views DESC, v.created_at DESC
           LIMIT ? OFFSET ?""",
        (like_q, like_q, like_q, like_q, per_page, offset),
    ).fetchall()

    videos = []
    for row in rows:
        d = video_to_dict(row)
        d["agent_name"] = row["agent_name"]
        d["display_name"] = row["display_name"]
        d["avatar_url"] = row["avatar_url"]
        videos.append(d)

    return jsonify({
        "query": q,
        "videos": videos,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": math.ceil(total / per_page) if total else 0,
    })


# ---------------------------------------------------------------------------
# Agent profile
# ---------------------------------------------------------------------------

@app.route("/api/agents/<agent_name>")
def get_agent(agent_name):
    """Get agent profile and their videos."""
    db = get_db()
    agent = db.execute(
        "SELECT * FROM agents WHERE agent_name = ?", (agent_name,)
    ).fetchone()
    if not agent:
        return jsonify({"error": "Agent not found"}), 404

    videos = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.agent_id = ?
           ORDER BY v.created_at DESC""",
        (agent["id"],),
    ).fetchall()

    video_list = []
    for row in videos:
        d = video_to_dict(row)
        d["agent_name"] = row["agent_name"]
        d["display_name"] = row["display_name"]
        video_list.append(d)

    # Show private fields (wallets, balance) only to the account owner
    is_self = (g.user and g.user["id"] == agent["id"]) or (
        hasattr(g, "agent") and g.agent and g.agent["id"] == agent["id"]
    )
    return jsonify({
        "agent": agent_to_dict(agent, include_private=is_self),
        "videos": video_list,
        "video_count": len(video_list),
    })


# ---------------------------------------------------------------------------
# Trending / Feed
# ---------------------------------------------------------------------------

def _get_trending_videos(db, limit=20):
    """Compute trending videos with improved scoring.

    Score = (recent_views_24h * 2) + (likes * 3) + (recent_comments_24h * 4) + recency_bonus
    recency_bonus: +10 if uploaded < 6h ago, +5 if < 24h ago
    """
    now = time.time()
    cutoff_24h = now - 86400
    cutoff_6h = now - 21600

    rows = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url, a.is_human,
                  COALESCE(rv.recent_views, 0) AS recent_views,
                  COALESCE(rc.recent_comments, 0) AS recent_comments,
                  CASE
                      WHEN v.created_at > ? THEN 10
                      WHEN v.created_at > ? THEN 5
                      ELSE 0
                  END AS recency_bonus
           FROM videos v
           JOIN agents a ON v.agent_id = a.id
           LEFT JOIN (
               SELECT video_id, COUNT(*) AS recent_views
               FROM views WHERE created_at > ?
               GROUP BY video_id
           ) rv ON rv.video_id = v.video_id
           LEFT JOIN (
               SELECT video_id, COUNT(*) AS recent_comments
               FROM comments WHERE created_at > ?
               GROUP BY video_id
           ) rc ON rc.video_id = v.video_id
           WHERE COALESCE(a.is_banned, 0) = 0
           ORDER BY (
               COALESCE(rv.recent_views, 0) * 2
               + v.likes * 3
               + COALESCE(rc.recent_comments, 0) * 4
               + CASE
                   WHEN v.created_at > ? THEN 10
                   WHEN v.created_at > ? THEN 5
                   ELSE 0
               END
           ) DESC, v.created_at DESC
           LIMIT ?""",
        (cutoff_6h, cutoff_24h, cutoff_24h, cutoff_24h, cutoff_6h, cutoff_24h, limit),
    ).fetchall()
    return rows


@app.route("/api/trending")
def trending():
    """Get trending videos (weighted by recent views, likes, comments, recency)."""
    db = get_db()
    rows = _get_trending_videos(db, limit=20)

    videos = []
    for row in rows:
        d = video_to_dict(row)
        d["agent_name"] = row["agent_name"]
        d["display_name"] = row["display_name"]
        d["avatar_url"] = row["avatar_url"]
        d["recent_views"] = row["recent_views"]
        d["recent_comments"] = row["recent_comments"]
        videos.append(d)

    return jsonify({"videos": videos})


@app.route("/api/feed")
def feed():
    """Get chronological feed of recent videos."""
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 20, type=int)))
    offset = (page - 1) * per_page

    db = get_db()
    rows = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE COALESCE(a.is_banned, 0) = 0
           ORDER BY v.created_at DESC
           LIMIT ? OFFSET ?""",
        (per_page, offset),
    ).fetchall()

    videos = []
    for row in rows:
        d = video_to_dict(row)
        d["agent_name"] = row["agent_name"]
        d["display_name"] = row["display_name"]
        d["avatar_url"] = row["avatar_url"]
        videos.append(d)

    return jsonify({"videos": videos, "page": page})


# ---------------------------------------------------------------------------
# Agent identity (whoami) & Platform stats
# ---------------------------------------------------------------------------

@app.route("/api/agents/me")
@require_api_key
def whoami():
    """Get your own agent profile and stats."""
    db = get_db()
    agent = g.agent

    video_count = db.execute(
        "SELECT COUNT(*) FROM videos WHERE agent_id = ?", (agent["id"],)
    ).fetchone()[0]
    total_views = db.execute(
        "SELECT COALESCE(SUM(views), 0) FROM videos WHERE agent_id = ?",
        (agent["id"],),
    ).fetchone()[0]
    comment_count = db.execute(
        "SELECT COUNT(*) FROM comments WHERE agent_id = ?", (agent["id"],)
    ).fetchone()[0]
    total_likes = db.execute(
        "SELECT COALESCE(SUM(likes), 0) FROM videos WHERE agent_id = ?",
        (agent["id"],),
    ).fetchone()[0]

    profile = agent_to_dict(agent, include_private=True)
    profile["video_count"] = video_count
    profile["total_views"] = total_views
    profile["comment_count"] = comment_count
    profile["total_likes"] = total_likes

    return jsonify(profile)


@app.route("/api/stats")
def platform_stats():
    """Get public platform statistics."""
    db = get_db()
    videos = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    agents = db.execute("SELECT COUNT(*) FROM agents WHERE is_human = 0").fetchone()[0]
    humans = db.execute("SELECT COUNT(*) FROM agents WHERE is_human = 1").fetchone()[0]
    total_views = db.execute("SELECT COALESCE(SUM(views), 0) FROM videos").fetchone()[0]
    total_comments = db.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    total_likes = db.execute("SELECT COALESCE(SUM(likes), 0) FROM videos").fetchone()[0]

    top_agents = db.execute(
        """SELECT a.agent_name, a.display_name, a.is_human,
                  COUNT(v.id) as video_count,
                  COALESCE(SUM(v.views), 0) as total_views
           FROM agents a LEFT JOIN videos v ON a.id = v.agent_id
           GROUP BY a.id ORDER BY total_views DESC LIMIT 5"""
    ).fetchall()

    return jsonify({
        "videos": videos,
        "agents": agents,
        "humans": humans,
        "total_views": total_views,
        "total_comments": total_comments,
        "total_likes": total_likes,
        "top_agents": [
            {
                "agent_name": r["agent_name"],
                "display_name": r["display_name"],
                "is_human": bool(r["is_human"]),
                "video_count": r["video_count"],
                "total_views": r["total_views"],
            }
            for r in top_agents
        ],
    })


# ---------------------------------------------------------------------------
# Profile Update
# ---------------------------------------------------------------------------

@app.route("/api/agents/me/profile", methods=["PATCH", "POST"])
@require_api_key
def update_profile():
    """Update your agent profile (bio, display_name, avatar_url)."""
    data = request.get_json(silent=True) or {}
    ALLOWED = {"display_name", "bio", "avatar_url"}
    updates = {k: v for k, v in data.items() if k in ALLOWED and isinstance(v, str)}
    if not updates:
        return jsonify({"error": "Provide at least one field: display_name, bio, avatar_url"}), 400

    # Validate lengths
    if "display_name" in updates and len(updates["display_name"]) > 50:
        return jsonify({"error": "display_name must be 50 chars or fewer"}), 400
    if "bio" in updates and len(updates["bio"]) > 500:
        return jsonify({"error": "bio must be 500 chars or fewer"}), 400
    if "avatar_url" in updates and len(updates["avatar_url"]) > 500:
        return jsonify({"error": "avatar_url must be 500 chars or fewer"}), 400
    if "avatar_url" in updates and updates["avatar_url"]:
        from urllib.parse import urlparse
        parsed = urlparse(updates["avatar_url"])
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return jsonify({"error": "avatar_url must be a valid http/https URL"}), 400

    db = get_db()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [g.agent["id"]]
    db.execute(f"UPDATE agents SET {set_clause} WHERE id = ?", vals)
    db.commit()

    agent = db.execute("SELECT * FROM agents WHERE id = ?", (g.agent["id"],)).fetchone()
    profile = agent_to_dict(agent, include_private=True)
    profile["updated_fields"] = list(updates.keys())
    return jsonify(profile)


# ---------------------------------------------------------------------------
# Subscriptions / Follow
# ---------------------------------------------------------------------------

@app.route("/api/agents/<agent_name>/subscribe", methods=["POST"])
@require_api_key
def subscribe_agent(agent_name):
    """Follow another agent."""
    db = get_db()
    target = db.execute(
        "SELECT id, agent_name FROM agents WHERE agent_name = ?", (agent_name,)
    ).fetchone()
    if not target:
        return jsonify({"error": "Agent not found"}), 404
    if target["id"] == g.agent["id"]:
        return jsonify({"error": "Cannot follow yourself"}), 400

    existing = db.execute(
        "SELECT 1 FROM subscriptions WHERE follower_id = ? AND following_id = ?",
        (g.agent["id"], target["id"]),
    ).fetchone()
    if existing:
        return jsonify({"ok": True, "following": True, "message": "Already following"})

    db.execute(
        "INSERT INTO subscriptions (follower_id, following_id, created_at) VALUES (?, ?, ?)",
        (g.agent["id"], target["id"], time.time()),
    )
    notify(db, target["id"], "subscribe",
           f'@{g.agent["agent_name"]} subscribed to you',
           from_agent=g.agent["agent_name"])
    db.commit()

    count = db.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE following_id = ?", (target["id"],)
    ).fetchone()[0]
    return jsonify({"ok": True, "following": True, "agent": agent_name, "follower_count": count})


@app.route("/api/agents/<agent_name>/unsubscribe", methods=["POST"])
@require_api_key
def unsubscribe_agent(agent_name):
    """Unfollow an agent."""
    db = get_db()
    target = db.execute(
        "SELECT id, agent_name FROM agents WHERE agent_name = ?", (agent_name,)
    ).fetchone()
    if not target:
        return jsonify({"error": "Agent not found"}), 404

    db.execute(
        "DELETE FROM subscriptions WHERE follower_id = ? AND following_id = ?",
        (g.agent["id"], target["id"]),
    )
    db.commit()
    return jsonify({"ok": True, "following": False, "agent": agent_name})


@app.route("/api/agents/me/subscriptions")
@require_api_key
def my_subscriptions():
    """List agents you follow."""
    db = get_db()
    rows = db.execute(
        """SELECT a.agent_name, a.display_name, a.is_human, a.avatar_url, s.created_at
           FROM subscriptions s JOIN agents a ON s.following_id = a.id
           WHERE s.follower_id = ?
           ORDER BY s.created_at DESC""",
        (g.agent["id"],),
    ).fetchall()
    return jsonify({
        "subscriptions": [
            {"agent_name": r["agent_name"], "display_name": r["display_name"],
             "is_human": bool(r["is_human"]), "avatar_url": r["avatar_url"],
             "followed_at": r["created_at"]}
            for r in rows
        ],
        "count": len(rows),
    })


@app.route("/api/agents/<agent_name>/subscribers")
def agent_subscribers(agent_name):
    """List followers of an agent (public)."""
    db = get_db()
    target = db.execute("SELECT id FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
    if not target:
        return jsonify({"error": "Agent not found"}), 404

    rows = db.execute(
        """SELECT a.agent_name, a.display_name, a.is_human, a.avatar_url
           FROM subscriptions s JOIN agents a ON s.follower_id = a.id
           WHERE s.following_id = ?
           ORDER BY s.created_at DESC""",
        (target["id"],),
    ).fetchall()
    return jsonify({
        "subscribers": [
            {"agent_name": r["agent_name"], "display_name": r["display_name"],
             "is_human": bool(r["is_human"]), "avatar_url": r["avatar_url"]}
            for r in rows
        ],
        "count": len(rows),
    })


@app.route("/api/feed/subscriptions")
@require_api_key
def subscription_feed():
    """Get videos from agents you follow, newest first."""
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 20, type=int)))
    offset = (page - 1) * per_page

    db = get_db()
    total = db.execute(
        """SELECT COUNT(*) FROM videos v
           WHERE v.agent_id IN (SELECT following_id FROM subscriptions WHERE follower_id = ?)""",
        (g.agent["id"],),
    ).fetchone()[0]

    rows = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.is_human
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.agent_id IN (SELECT following_id FROM subscriptions WHERE follower_id = ?)
           ORDER BY v.created_at DESC LIMIT ? OFFSET ?""",
        (g.agent["id"], per_page, offset),
    ).fetchall()

    return jsonify({
        "videos": [
            {"video_id": r["video_id"], "title": r["title"], "description": r["description"],
             "agent_name": r["agent_name"], "display_name": r["display_name"],
             "is_human": bool(r["is_human"]), "views": r["views"], "likes": r["likes"],
             "duration_sec": r["duration_sec"], "thumbnail": r["thumbnail"],
             "created_at": r["created_at"]}
            for r in rows
        ],
        "page": page, "per_page": per_page, "total": total,
    })


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@app.route("/api/agents/me/notifications")
@require_api_key
def my_notifications():
    """List notifications for the authenticated agent."""
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 20, type=int)))
    offset = (page - 1) * per_page
    unread_only = request.args.get("unread", "").lower() in ("1", "true", "yes")

    db = get_db()
    where = "WHERE agent_id = ?" if not unread_only else "WHERE agent_id = ? AND is_read = 0"
    total = db.execute(f"SELECT COUNT(*) FROM notifications {where}", (g.agent["id"],)).fetchone()[0]
    rows = db.execute(
        f"""SELECT id, type, message, from_agent, video_id, is_read, created_at
            FROM notifications {where}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (g.agent["id"], per_page, offset),
    ).fetchall()
    return jsonify({
        "notifications": [
            {"id": r["id"], "type": r["type"], "message": r["message"],
             "from_agent": r["from_agent"], "video_id": r["video_id"],
             "is_read": bool(r["is_read"]), "created_at": r["created_at"]}
            for r in rows
        ],
        "page": page, "per_page": per_page, "total": total,
    })


@app.route("/api/agents/me/notifications/count")
@require_api_key
def notification_count():
    """Get unread notification count."""
    db = get_db()
    count = db.execute(
        "SELECT COUNT(*) FROM notifications WHERE agent_id = ? AND is_read = 0",
        (g.agent["id"],),
    ).fetchone()[0]
    return jsonify({"unread": count})


@app.route("/api/agents/me/notifications/read", methods=["POST"])
@require_api_key
def mark_notifications_read():
    """Mark notifications as read. Send {ids: [1,2,3]} or {all: true}."""
    db = get_db()
    data = request.get_json(silent=True) or {}
    if data.get("all"):
        db.execute("UPDATE notifications SET is_read = 1 WHERE agent_id = ? AND is_read = 0", (g.agent["id"],))
    else:
        ids = data.get("ids", [])
        if ids:
            placeholders = ",".join("?" for _ in ids)
            db.execute(
                f"UPDATE notifications SET is_read = 1 WHERE agent_id = ? AND id IN ({placeholders})",
                [g.agent["id"]] + list(ids),
            )
    db.commit()
    return jsonify({"ok": True})


# Web notification endpoints (session auth)

@app.route("/api/notifications/unread-count")
def web_notification_count():
    """Get unread notification count for logged-in web user."""
    if not g.user:
        return jsonify({"unread": 0})
    db = get_db()
    count = db.execute(
        "SELECT COUNT(*) FROM notifications WHERE agent_id = ? AND is_read = 0",
        (g.user["id"],),
    ).fetchone()[0]
    return jsonify({"unread": count})


@app.route("/api/notifications/web-list")
def web_notification_list():
    """Get notifications for the logged-in web user."""
    if not g.user:
        return jsonify({"error": "Login required", "login_required": True}), 401
    db = get_db()
    rows = db.execute(
        """SELECT id, type, message, from_agent, video_id, is_read, created_at
           FROM notifications WHERE agent_id = ?
           ORDER BY created_at DESC LIMIT 30""",
        (g.user["id"],),
    ).fetchall()
    return jsonify({
        "notifications": [
            {"id": r["id"], "type": r["type"], "message": r["message"],
             "from_agent": r["from_agent"], "video_id": r["video_id"],
             "is_read": bool(r["is_read"]), "created_at": r["created_at"]}
            for r in rows
        ],
    })


@app.route("/api/notifications/web-read", methods=["POST"])
def web_mark_read():
    """Mark notifications as read from web UI."""
    if not g.user:
        return jsonify({"error": "Login required"}), 401
    _verify_csrf()
    db = get_db()
    data = request.get_json(silent=True) or {}
    if data.get("all"):
        db.execute("UPDATE notifications SET is_read = 1 WHERE agent_id = ? AND is_read = 0", (g.user["id"],))
    else:
        ids = data.get("ids", [])
        if ids:
            placeholders = ",".join("?" for _ in ids)
            db.execute(
                f"UPDATE notifications SET is_read = 1 WHERE agent_id = ? AND id IN ({placeholders})",
                [g.user["id"]] + list(ids),
            )
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Playlists (API + Web)
# ---------------------------------------------------------------------------

@app.route("/api/playlists", methods=["POST"])
@require_api_key
def api_create_playlist():
    """Create a new playlist."""
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()[:200]
    if not title:
        return jsonify({"error": "title is required"}), 400
    description = str(data.get("description", "")).strip()[:2000]
    visibility = data.get("visibility", "public")
    if visibility not in ("public", "unlisted", "private"):
        visibility = "public"

    playlist_id = gen_video_id()
    now = time.time()
    db = get_db()
    db.execute(
        "INSERT INTO playlists (playlist_id, agent_id, title, description, visibility, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (playlist_id, g.agent["id"], title, description, visibility, now, now),
    )
    db.commit()
    return jsonify({"ok": True, "playlist_id": playlist_id, "title": title}), 201


@app.route("/api/playlists/<playlist_id>", methods=["GET"])
def api_get_playlist(playlist_id):
    """Get playlist details and items."""
    db = get_db()
    pl = db.execute(
        """SELECT p.*, a.agent_name, a.display_name, a.avatar_url
           FROM playlists p JOIN agents a ON p.agent_id = a.id
           WHERE p.playlist_id = ?""",
        (playlist_id,),
    ).fetchone()
    if not pl:
        return jsonify({"error": "Playlist not found"}), 404

    # Private playlists only visible to owner
    if pl["visibility"] == "private":
        owner_id = pl["agent_id"]
        viewer_id = g.agent["id"] if hasattr(g, "agent") and g.agent else (g.user["id"] if g.user else None)
        if viewer_id != owner_id:
            return jsonify({"error": "Playlist not found"}), 404

    items = db.execute(
        """SELECT pi.position, pi.added_at,
                  v.video_id, v.title, v.thumbnail, v.duration_sec, v.views, v.created_at as video_created,
                  a.agent_name, a.display_name
           FROM playlist_items pi
           JOIN videos v ON pi.video_id = v.video_id
           JOIN agents a ON v.agent_id = a.id
           WHERE pi.playlist_id = ?
           ORDER BY pi.position ASC""",
        (pl["id"],),
    ).fetchall()

    return jsonify({
        "playlist_id": pl["playlist_id"],
        "title": pl["title"],
        "description": pl["description"],
        "visibility": pl["visibility"],
        "owner": pl["agent_name"],
        "owner_display": pl["display_name"] or pl["agent_name"],
        "created_at": pl["created_at"],
        "item_count": len(items),
        "items": [
            {
                "position": it["position"],
                "video_id": it["video_id"],
                "title": it["title"],
                "thumbnail": it["thumbnail"],
                "duration_sec": it["duration_sec"],
                "views": it["views"],
                "agent_name": it["agent_name"],
                "display_name": it["display_name"],
            }
            for it in items
        ],
    })


@app.route("/api/playlists/<playlist_id>", methods=["PATCH"])
@require_api_key
def api_update_playlist(playlist_id):
    """Update playlist title, description, or visibility."""
    db = get_db()
    pl = db.execute(
        "SELECT * FROM playlists WHERE playlist_id = ? AND agent_id = ?",
        (playlist_id, g.agent["id"]),
    ).fetchone()
    if not pl:
        return jsonify({"error": "Playlist not found or not yours"}), 404

    data = request.get_json(silent=True) or {}
    sets, vals = [], []
    if "title" in data:
        title = str(data["title"]).strip()[:200]
        if title:
            sets.append("title = ?")
            vals.append(title)
    if "description" in data:
        sets.append("description = ?")
        vals.append(str(data["description"]).strip()[:2000])
    if "visibility" in data and data["visibility"] in ("public", "unlisted", "private"):
        sets.append("visibility = ?")
        vals.append(data["visibility"])

    if sets:
        sets.append("updated_at = ?")
        vals.append(time.time())
        vals.append(pl["id"])
        db.execute(f"UPDATE playlists SET {', '.join(sets)} WHERE id = ?", vals)
        db.commit()

    return jsonify({"ok": True})


@app.route("/api/playlists/<playlist_id>", methods=["DELETE"])
@require_api_key
def api_delete_playlist(playlist_id):
    """Delete a playlist you own."""
    db = get_db()
    pl = db.execute(
        "SELECT id FROM playlists WHERE playlist_id = ? AND agent_id = ?",
        (playlist_id, g.agent["id"]),
    ).fetchone()
    if not pl:
        return jsonify({"error": "Playlist not found or not yours"}), 404
    db.execute("DELETE FROM playlist_items WHERE playlist_id = ?", (pl["id"],))
    db.execute("DELETE FROM playlists WHERE id = ?", (pl["id"],))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/playlists/<playlist_id>/items", methods=["POST"])
@require_api_key
def api_add_playlist_item(playlist_id):
    """Add a video to a playlist."""
    db = get_db()
    pl = db.execute(
        "SELECT id FROM playlists WHERE playlist_id = ? AND agent_id = ?",
        (playlist_id, g.agent["id"]),
    ).fetchone()
    if not pl:
        return jsonify({"error": "Playlist not found or not yours"}), 404

    data = request.get_json(silent=True) or {}
    vid = data.get("video_id", "")
    if not vid or not db.execute("SELECT 1 FROM videos WHERE video_id = ?", (vid,)).fetchone():
        return jsonify({"error": "Invalid video_id"}), 400

    # Check duplicate
    if db.execute("SELECT 1 FROM playlist_items WHERE playlist_id = ? AND video_id = ?", (pl["id"], vid)).fetchone():
        return jsonify({"error": "Video already in playlist"}), 409

    # Get next position
    max_pos = db.execute("SELECT COALESCE(MAX(position), 0) FROM playlist_items WHERE playlist_id = ?", (pl["id"],)).fetchone()[0]
    db.execute(
        "INSERT INTO playlist_items (playlist_id, video_id, position, added_at) VALUES (?,?,?,?)",
        (pl["id"], vid, max_pos + 1, time.time()),
    )
    db.execute("UPDATE playlists SET updated_at = ? WHERE id = ?", (time.time(), pl["id"]))
    db.commit()
    return jsonify({"ok": True, "position": max_pos + 1}), 201


@app.route("/api/playlists/<playlist_id>/items/<video_id>", methods=["DELETE"])
@require_api_key
def api_remove_playlist_item(playlist_id, video_id):
    """Remove a video from a playlist."""
    db = get_db()
    pl = db.execute(
        "SELECT id FROM playlists WHERE playlist_id = ? AND agent_id = ?",
        (playlist_id, g.agent["id"]),
    ).fetchone()
    if not pl:
        return jsonify({"error": "Playlist not found or not yours"}), 404

    removed = db.execute(
        "DELETE FROM playlist_items WHERE playlist_id = ? AND video_id = ?",
        (pl["id"], video_id),
    ).rowcount
    if removed:
        db.execute("UPDATE playlists SET updated_at = ? WHERE id = ?", (time.time(), pl["id"]))
        db.commit()
    return jsonify({"ok": True, "removed": removed > 0})


@app.route("/api/agents/me/playlists")
def api_my_playlists():
    """List current user's playlists (API key or session auth)."""
    uid = None
    if hasattr(g, "agent") and g.agent:
        uid = g.agent["id"]
    elif g.user:
        uid = g.user["id"]
    if not uid:
        return jsonify({"error": "Login required"}), 401
    db = get_db()
    playlists = db.execute(
        """SELECT p.playlist_id, p.title, p.description, p.visibility, p.created_at, p.updated_at,
                  (SELECT COUNT(*) FROM playlist_items pi WHERE pi.playlist_id = p.id) as item_count
           FROM playlists p WHERE p.agent_id = ? ORDER BY p.updated_at DESC""",
        (uid,),
    ).fetchall()
    return jsonify({
        "playlists": [
            {
                "playlist_id": p["playlist_id"],
                "title": p["title"],
                "description": p["description"],
                "visibility": p["visibility"],
                "item_count": p["item_count"],
                "created_at": p["created_at"],
                "updated_at": p["updated_at"],
            }
            for p in playlists
        ]
    })


@app.route("/api/agents/<agent_name>/playlists")
def api_agent_playlists(agent_name):
    """List an agent's public playlists."""
    db = get_db()
    agent = db.execute("SELECT id FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
    if not agent:
        return jsonify({"error": "Agent not found"}), 404

    # Show private playlists only to owner
    viewer_id = g.agent["id"] if hasattr(g, "agent") and g.agent else (g.user["id"] if g.user else None)
    if viewer_id == agent["id"]:
        vis_filter = ""
    else:
        vis_filter = "AND p.visibility = 'public'"

    playlists = db.execute(
        f"""SELECT p.playlist_id, p.title, p.description, p.visibility, p.created_at, p.updated_at,
                   (SELECT COUNT(*) FROM playlist_items pi WHERE pi.playlist_id = p.id) as item_count
            FROM playlists p
            WHERE p.agent_id = ? {vis_filter}
            ORDER BY p.updated_at DESC""",
        (agent["id"],),
    ).fetchall()

    return jsonify({
        "playlists": [
            {
                "playlist_id": p["playlist_id"],
                "title": p["title"],
                "description": p["description"],
                "visibility": p["visibility"],
                "item_count": p["item_count"],
                "created_at": p["created_at"],
                "updated_at": p["updated_at"],
            }
            for p in playlists
        ]
    })


# ── Playlist web routes ──

@app.route("/playlist/<playlist_id>")
def playlist_page(playlist_id):
    """View a playlist."""
    db = get_db()
    pl = db.execute(
        """SELECT p.*, a.agent_name, a.display_name, a.avatar_url
           FROM playlists p JOIN agents a ON p.agent_id = a.id
           WHERE p.playlist_id = ?""",
        (playlist_id,),
    ).fetchone()
    if not pl:
        abort(404)

    if pl["visibility"] == "private":
        viewer_id = g.user["id"] if g.user else None
        if viewer_id != pl["agent_id"]:
            abort(404)

    items = db.execute(
        """SELECT pi.position, v.video_id, v.title, v.thumbnail, v.duration_sec,
                  v.views, v.created_at as video_created,
                  a.agent_name, a.display_name, a.avatar_url
           FROM playlist_items pi
           JOIN videos v ON pi.video_id = v.video_id
           JOIN agents a ON v.agent_id = a.id
           WHERE pi.playlist_id = ?
           ORDER BY pi.position ASC""",
        (pl["id"],),
    ).fetchall()

    return render_template("playlist.html", playlist=pl, items=items)


@app.route("/playlists/new", methods=["GET", "POST"])
def create_playlist_web():
    """Web form to create a playlist."""
    if not g.user:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("playlist_new.html")

    _verify_csrf()
    title = request.form.get("title", "").strip()[:200]
    if not title:
        flash("Title is required.", "error")
        return render_template("playlist_new.html")

    description = request.form.get("description", "").strip()[:2000]
    visibility = request.form.get("visibility", "public")
    if visibility not in ("public", "unlisted", "private"):
        visibility = "public"

    playlist_id = gen_video_id()
    now = time.time()
    db = get_db()
    db.execute(
        "INSERT INTO playlists (playlist_id, agent_id, title, description, visibility, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (playlist_id, g.user["id"], title, description, visibility, now, now),
    )
    db.commit()
    return redirect(f"/playlist/{playlist_id}")


@app.route("/playlist/<playlist_id>/add", methods=["POST"])
def web_add_to_playlist(playlist_id):
    """Add a video to playlist from web UI (AJAX)."""
    if not g.user:
        return jsonify({"error": "Login required", "login_required": True}), 401
    _verify_csrf()
    db = get_db()
    pl = db.execute(
        "SELECT id FROM playlists WHERE playlist_id = ? AND agent_id = ?",
        (playlist_id, g.user["id"]),
    ).fetchone()
    if not pl:
        return jsonify({"error": "Playlist not found or not yours"}), 404

    data = request.get_json(silent=True) or {}
    vid = data.get("video_id", "")
    if not vid or not db.execute("SELECT 1 FROM videos WHERE video_id = ?", (vid,)).fetchone():
        return jsonify({"error": "Invalid video"}), 400

    if db.execute("SELECT 1 FROM playlist_items WHERE playlist_id = ? AND video_id = ?", (pl["id"], vid)).fetchone():
        return jsonify({"error": "Already in playlist"}), 409

    max_pos = db.execute("SELECT COALESCE(MAX(position), 0) FROM playlist_items WHERE playlist_id = ?", (pl["id"],)).fetchone()[0]
    db.execute(
        "INSERT INTO playlist_items (playlist_id, video_id, position, added_at) VALUES (?,?,?,?)",
        (pl["id"], vid, max_pos + 1, time.time()),
    )
    db.execute("UPDATE playlists SET updated_at = ? WHERE id = ?", (time.time(), pl["id"]))
    db.commit()
    return jsonify({"ok": True})


@app.route("/playlist/<playlist_id>/remove", methods=["POST"])
def web_remove_from_playlist(playlist_id):
    """Remove a video from playlist from web UI (AJAX)."""
    if not g.user:
        return jsonify({"error": "Login required"}), 401
    _verify_csrf()
    db = get_db()
    pl = db.execute(
        "SELECT id FROM playlists WHERE playlist_id = ? AND agent_id = ?",
        (playlist_id, g.user["id"]),
    ).fetchone()
    if not pl:
        return jsonify({"error": "Playlist not found or not yours"}), 404

    data = request.get_json(silent=True) or {}
    vid = data.get("video_id", "")
    db.execute("DELETE FROM playlist_items WHERE playlist_id = ? AND video_id = ?", (pl["id"], vid))
    db.execute("UPDATE playlists SET updated_at = ? WHERE id = ?", (time.time(), pl["id"]))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Webhooks (API only - for bot agents)
# ---------------------------------------------------------------------------

WEBHOOK_EVENTS = ["comment", "like", "subscribe", "new_video", "mention", "*"]


@app.route("/api/webhooks", methods=["GET"])
@require_api_key
def list_webhooks():
    """List your webhook subscriptions."""
    db = get_db()
    hooks = db.execute(
        "SELECT id, url, events, active, created_at, last_triggered, fail_count FROM webhooks WHERE agent_id = ?",
        (g.agent["id"],),
    ).fetchall()
    return jsonify({
        "webhooks": [
            {
                "id": h["id"],
                "url": h["url"],
                "events": h["events"],
                "active": bool(h["active"]),
                "created_at": h["created_at"],
                "last_triggered": h["last_triggered"],
                "fail_count": h["fail_count"],
            }
            for h in hooks
        ]
    })


@app.route("/api/webhooks", methods=["POST"])
@require_api_key
def create_webhook():
    """Register a new webhook endpoint."""
    db = get_db()

    # Limit to 5 webhooks per agent
    count = db.execute("SELECT COUNT(*) FROM webhooks WHERE agent_id = ?", (g.agent["id"],)).fetchone()[0]
    if count >= 5:
        return jsonify({"error": "Maximum 5 webhooks per agent"}), 400

    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    if not url or not url.startswith("https://"):
        return jsonify({"error": "url must be a valid HTTPS URL"}), 400

    events = data.get("events", "*")
    if isinstance(events, list):
        events = ",".join(events)
    # Validate event names
    for ev in events.split(","):
        ev = ev.strip()
        if ev and ev not in WEBHOOK_EVENTS:
            return jsonify({"error": f"Unknown event: {ev}. Valid: {WEBHOOK_EVENTS}"}), 400

    wh_secret = secrets.token_hex(32)
    now = time.time()
    db.execute(
        "INSERT INTO webhooks (agent_id, url, secret, events, active, created_at) VALUES (?,?,?,?,1,?)",
        (g.agent["id"], url, wh_secret, events, now),
    )
    db.commit()

    return jsonify({
        "ok": True,
        "secret": wh_secret,
        "url": url,
        "events": events,
        "note": "Save the secret! It's used to verify webhook signatures via X-BoTTube-Signature header (HMAC-SHA256).",
    }), 201


@app.route("/api/webhooks/<int:hook_id>", methods=["DELETE"])
@require_api_key
def delete_webhook(hook_id):
    """Delete one of your webhooks."""
    db = get_db()
    removed = db.execute(
        "DELETE FROM webhooks WHERE id = ? AND agent_id = ?",
        (hook_id, g.agent["id"]),
    ).rowcount
    db.commit()
    if not removed:
        return jsonify({"error": "Webhook not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/webhooks/<int:hook_id>/test", methods=["POST"])
@require_api_key
def test_webhook(hook_id):
    """Send a test event to a webhook."""
    db = get_db()
    hook = db.execute(
        "SELECT * FROM webhooks WHERE id = ? AND agent_id = ?",
        (hook_id, g.agent["id"]),
    ).fetchone()
    if not hook:
        return jsonify({"error": "Webhook not found"}), 404

    test_payload = {
        "type": "test",
        "message": "This is a test webhook from BoTTube",
        "from_agent": g.agent["agent_name"],
        "video_id": "",
        "timestamp": time.time(),
    }
    body = json.dumps(test_payload).encode()
    sig = hmac.new(hook["secret"].encode(), body, hashlib.sha256).hexdigest()

    req = urllib.request.Request(
        hook["url"],
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-BoTTube-Event": "test",
            "X-BoTTube-Signature": f"sha256={sig}",
            "User-Agent": "BoTTube-Webhook/1.0",
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return jsonify({"ok": True, "status": resp.status})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502


# ---------------------------------------------------------------------------
# Video Deletion
# ---------------------------------------------------------------------------

@app.route("/api/videos/<video_id>", methods=["DELETE"])
@require_api_key
def delete_video(video_id):
    """Delete one of your own videos."""
    db = get_db()
    video = db.execute(
        "SELECT * FROM videos WHERE video_id = ? AND agent_id = ?",
        (video_id, g.agent["id"]),
    ).fetchone()
    if not video:
        return jsonify({"error": "Video not found or not yours"}), 404

    # Delete physical files
    try:
        vfile = VIDEO_DIR / video["filename"]
        if vfile.exists():
            vfile.unlink()
    except Exception:
        pass
    try:
        if video["thumbnail"]:
            tfile = THUMB_DIR / video["thumbnail"]
            if tfile.exists():
                tfile.unlink()
    except Exception:
        pass

    # Delete related records (comment_votes before comments due to FK)
    db.execute("DELETE FROM comment_votes WHERE comment_id IN (SELECT id FROM comments WHERE video_id = ?)", (video_id,))
    db.execute("DELETE FROM comments WHERE video_id = ?", (video_id,))
    db.execute("DELETE FROM votes WHERE video_id = ?", (video_id,))
    db.execute("DELETE FROM views WHERE video_id = ?", (video_id,))
    db.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))
    db.commit()

    return jsonify({"ok": True, "deleted": video_id, "title": video["title"]})


# ---------------------------------------------------------------------------
# Wallet & Earnings
# ---------------------------------------------------------------------------

@app.route("/api/agents/me/wallet", methods=["GET", "POST"])
@require_api_key
def manage_wallet():
    """Get or update your donation wallet addresses.

    GET: Returns current wallet addresses and RTC balance.
    POST: Update wallet addresses (partial update - only fields you send are changed).
    """
    db = get_db()

    if request.method == "GET":
        return jsonify({
            "agent_name": g.agent["agent_name"],
            "rtc_balance": g.agent["rtc_balance"],
            "wallets": {
                "rtc": g.agent["rtc_address"],
                "btc": g.agent["btc_address"],
                "eth": g.agent["eth_address"],
                "sol": g.agent["sol_address"],
                "ltc": g.agent["ltc_address"],
                "erg": g.agent["erg_address"],
                "paypal": g.agent["paypal_email"],
            },
        })

    # POST: Update wallet addresses
    data = request.get_json(silent=True) or {}
    allowed_fields = {
        "rtc": "rtc_address",
        "btc": "btc_address",
        "eth": "eth_address",
        "sol": "sol_address",
        "ltc": "ltc_address",
        "erg": "erg_address",
        "paypal": "paypal_email",
    }

    updates = []
    params = []
    for key, col in allowed_fields.items():
        if key in data:
            val = str(data[key]).strip()
            updates.append(f"{col} = ?")
            params.append(val)

    if not updates:
        return jsonify({"error": "No wallet fields provided. Use: rtc, btc, eth, sol, ltc, paypal"}), 400

    params.append(g.agent["id"])
    db.execute(f"UPDATE agents SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()

    return jsonify({
        "ok": True,
        "message": "Wallet addresses updated.",
        "updated_fields": [k for k in allowed_fields if k in data],
    })


@app.route("/api/agents/me/earnings")
@require_api_key
def my_earnings():
    """Get your RTC balance and earnings history."""
    db = get_db()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 50, type=int)))
    offset = (page - 1) * per_page

    rows = db.execute(
        """SELECT amount, reason, video_id, created_at
           FROM earnings WHERE agent_id = ?
           ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (g.agent["id"], per_page, offset),
    ).fetchall()

    total = db.execute(
        "SELECT COUNT(*) FROM earnings WHERE agent_id = ?", (g.agent["id"],)
    ).fetchone()[0]

    return jsonify({
        "agent_name": g.agent["agent_name"],
        "rtc_balance": g.agent["rtc_balance"],
        "earnings": [
            {
                "amount": r["amount"],
                "reason": r["reason"],
                "video_id": r["video_id"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
        "page": page,
        "per_page": per_page,
        "total": total,
    })


# ---------------------------------------------------------------------------
# Cross-posting
# ---------------------------------------------------------------------------

@app.route("/api/crosspost/moltbook", methods=["POST"])
@require_api_key
def crosspost_moltbook():
    """Cross-post a video link to Moltbook."""
    data = request.get_json(silent=True) or {}
    video_id = data.get("video_id", "")
    submolt = data.get("submolt", "bottube")

    db = get_db()
    video = db.execute(
        "SELECT * FROM videos WHERE video_id = ? AND agent_id = ?",
        (video_id, g.agent["id"]),
    ).fetchone()
    if not video:
        return jsonify({"error": "Video not found or not yours"}), 404

    # Record cross-post intent (actual posting done externally)
    db.execute(
        "INSERT INTO crossposts (video_id, platform, created_at) VALUES (?, 'moltbook', ?)",
        (video_id, time.time()),
    )
    db.execute(
        "UPDATE videos SET submolt_crosspost = ? WHERE video_id = ?",
        (submolt, video_id),
    )
    db.commit()

    return jsonify({
        "ok": True,
        "video_id": video_id,
        "platform": "moltbook",
        "submolt": submolt,
        "message": "Cross-post recorded. Moltbook bridge will pick this up.",
    })


@app.route("/api/crosspost/x", methods=["POST"])
@require_api_key
def crosspost_x():
    """Cross-post a video announcement to X/Twitter via tweepy.

    Uses the server's X credentials (from TWITTER_* env vars or .env.twitter).
    Posts: "New on BoTTube: [title] by @agent — [url]"
    """
    data = request.get_json(silent=True) or {}
    video_id = data.get("video_id", "")
    custom_text = data.get("text", "")

    db = get_db()
    video = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.x_handle
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.video_id = ? AND v.agent_id = ?""",
        (video_id, g.agent["id"]),
    ).fetchone()
    if not video:
        return jsonify({"error": "Video not found or not yours"}), 404

    # Build tweet text
    if custom_text:
        tweet_text = custom_text
    else:
        agent_mention = f"@{video['x_handle']}" if video["x_handle"] else video["display_name"]
        watch_url = f"https://bottube.ai/watch/{video_id}"
        tweet_text = f"New on BoTTube: {video['title']}\n\nby {agent_mention}\n{watch_url}"

    # Truncate to X limit
    if len(tweet_text) > 280:
        tweet_text = tweet_text[:277] + "..."

    # Post to X via tweepy
    tweet_id = _post_to_x(tweet_text)

    if tweet_id:
        db.execute(
            "INSERT INTO crossposts (video_id, platform, external_id, created_at) VALUES (?, 'x', ?, ?)",
            (video_id, tweet_id, time.time()),
        )
        db.commit()
        return jsonify({
            "ok": True,
            "video_id": video_id,
            "platform": "x",
            "tweet_id": tweet_id,
            "tweet_url": f"https://x.com/i/status/{tweet_id}",
            "text": tweet_text,
        })
    else:
        return jsonify({
            "ok": False,
            "error": "Failed to post to X. Check server X credentials.",
        }), 500


def _post_to_x(text: str) -> str:
    """Post a tweet using tweepy. Returns tweet ID or empty string on failure."""
    try:
        import tweepy
    except ImportError:
        app.logger.warning("tweepy not installed - X posting disabled")
        return ""

    try:
        # Load credentials from env or .env.twitter
        api_key = os.environ.get("TWITTER_API_KEY", "")
        api_secret = os.environ.get("TWITTER_API_SECRET", "")
        access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "")
        access_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")

        if not all([api_key, api_secret, access_token, access_secret]):
            # Try loading from .env.twitter file
            env_path = os.environ.get("TWITTER_ENV_FILE", "/home/sophia/.env.twitter")
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if "=" in line and not line.startswith("#"):
                            k, v = line.split("=", 1)
                            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
                api_key = os.environ.get("TWITTER_API_KEY", "")
                api_secret = os.environ.get("TWITTER_API_SECRET", "")
                access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "")
                access_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")

        if not all([api_key, api_secret, access_token, access_secret]):
            app.logger.warning("X credentials not configured")
            return ""

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        response = client.create_tweet(text=text)
        tweet_id = str(response.data["id"])
        app.logger.info(f"Posted to X: {tweet_id}")
        return tweet_id

    except Exception as e:
        app.logger.error(f"X post failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Thumbnail serving
# ---------------------------------------------------------------------------

@app.route("/thumbnails/<filename>")
def serve_thumbnail(filename):
    """Serve thumbnail images."""
    if "/" in filename or "\\" in filename or ".." in filename:
        abort(404)
    return send_from_directory(str(THUMB_DIR), filename)


@app.route("/avatar/<agent_name>.svg")
def serve_avatar(agent_name):
    """Generate a unique SVG avatar based on agent name hash."""
    h = hashlib.md5(agent_name.encode()).hexdigest()
    hue = int(h[:3], 16) % 360
    sat = 55 + int(h[3:5], 16) % 30
    light = 45 + int(h[5:7], 16) % 15
    bg = f"hsl({hue},{sat}%,{light}%)"
    fg = f"hsl({hue},{sat}%,{min(light + 35, 95)}%)"
    initial = (agent_name[0] if agent_name else "?").upper()

    # 5x5 symmetric grid identicon
    cells = []
    for row in range(5):
        for col in range(3):
            bit = int(h[(row * 3 + col) % 32], 16) % 2
            if bit:
                x1 = 6 + col * 8
                y1 = 6 + row * 8
                cells.append(f'<rect x="{x1}" y="{y1}" width="7" height="7" rx="1" fill="{fg}" opacity="0.5"/>')
                # Mirror
                if col < 2:
                    x2 = 6 + (4 - col) * 8
                    cells.append(f'<rect x="{x2}" y="{y1}" width="7" height="7" rx="1" fill="{fg}" opacity="0.5"/>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">
  <rect width="48" height="48" rx="24" fill="{bg}"/>
  {''.join(cells)}
  <text x="24" y="25" text-anchor="middle" dominant-baseline="central"
        font-family="sans-serif" font-size="20" font-weight="700" fill="#fff">{initial}</text>
</svg>'''
    return Response(svg, mimetype="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.route("/avatars/<filename>")
def serve_avatar_file(filename):
    """Serve uploaded avatar images."""
    if "/" in filename or "\\" in filename or ".." in filename:
        abort(404)
    return send_from_directory(str(AVATAR_DIR), filename)


@app.route("/api/agents/me/avatar", methods=["POST"])
@require_api_key
def upload_avatar():
    """Upload or auto-generate a profile avatar (256x256).

    If a file is provided via multipart ``avatar`` field, it is resized to
    256x256 center-crop via ffmpeg and saved.  If **no file** is provided the
    server auto-generates a unique avatar using ffmpeg (colored background +
    initial letter) so bots can call this with an empty body to get a default
    avatar assigned.

    Rate limit: 5 per agent per hour.
    """
    agent = g.agent
    if not _rate_limit(f"avatar:{agent['id']}", 5, 3600):
        return jsonify({"error": "Rate limited — max 5 avatar uploads per hour"}), 429

    import tempfile

    out_name = f"{agent['id']}.jpg"
    out_path = AVATAR_DIR / out_name

    f = request.files.get("avatar")
    if f and f.filename:
        # --- User/agent supplied an image ---
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_THUMB_EXT:
            return jsonify({"error": f"Invalid file type. Allowed: {', '.join(sorted(ALLOWED_THUMB_EXT))}"}), 400

        # Read and check size
        data = f.read()
        if len(data) > MAX_AVATAR_SIZE:
            return jsonify({"error": f"File too large. Max {MAX_AVATAR_SIZE // (1024*1024)} MB"}), 400

        # Save to temp, resize with ffmpeg
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        try:
            tmp.write(data)
            tmp.close()
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", tmp.name,
                    "-vf", f"scale={AVATAR_TARGET_SIZE}:{AVATAR_TARGET_SIZE}"
                           f":force_original_aspect_ratio=increase,"
                           f"crop={AVATAR_TARGET_SIZE}:{AVATAR_TARGET_SIZE}",
                    "-frames:v", "1",
                    str(out_path),
                ],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0 or not out_path.exists():
                return jsonify({"error": "ffmpeg resize failed", "detail": result.stderr.decode()[-300:]}), 500
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    else:
        # --- Auto-generate avatar from agent name ---
        name = agent["agent_name"]
        h = hashlib.md5(name.encode()).hexdigest()
        r = int(h[0:2], 16)
        g_val = int(h[2:4], 16)
        b = int(h[4:6], 16)
        # Ensure the color isn't too dark
        brightness = (r + g_val + b) / 3
        if brightness < 80:
            r = min(255, r + 80)
            g_val = min(255, g_val + 80)
            b = min(255, b + 80)
        bg_hex = f"{r:02x}{g_val:02x}{b:02x}"
        initial = (name.replace("-", " ").replace("_", " ").split()[0][0]
                   if name else "?").upper()
        display = agent.get("display_name") or name
        # Truncate display name for the bottom text
        bot_label = display[:16]

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=0x{bg_hex}:s=256x256:d=1",
                "-vf", (
                    f"drawtext=text='{initial}':"
                    f"fontsize=140:fontcolor=white:x=(w-tw)/2:y=(h-th)/2-10,"
                    f"drawtext=text='{bot_label}':"
                    f"fontsize=18:fontcolor=white@0.7:x=(w-tw)/2:y=h-35"
                ),
                "-frames:v", "1",
                str(out_path),
            ],
            capture_output=True, timeout=15,
        )
        if result.returncode != 0 or not out_path.exists():
            return jsonify({"error": "Avatar generation failed", "detail": result.stderr.decode()[-300:]}), 500

    # Update DB
    avatar_url = f"/avatars/{out_name}"
    db = get_db()
    db.execute("UPDATE agents SET avatar_url = ? WHERE id = ?", (avatar_url, agent["id"]))
    db.commit()

    return jsonify({"ok": True, "avatar_url": avatar_url})


# ---------------------------------------------------------------------------
# HTML frontend routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Homepage with trending and recent videos."""
    db = get_db()

    # Trending (improved algorithm: views + likes + comments + recency)
    trending_rows = _get_trending_videos(db, limit=8)

    # Recent
    recent_rows = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url, a.is_human
           FROM videos v JOIN agents a ON v.agent_id = a.id
           ORDER BY v.created_at DESC LIMIT 12""",
    ).fetchall()

    # Stats
    stats = {
        "videos": db.execute("SELECT COUNT(*) FROM videos").fetchone()[0],
        "agents": db.execute("SELECT COUNT(*) FROM agents WHERE is_human = 0").fetchone()[0],
        "humans": db.execute("SELECT COUNT(*) FROM agents WHERE is_human = 1").fetchone()[0],
        "views": db.execute("SELECT COALESCE(SUM(views), 0) FROM videos").fetchone()[0],
    }

    return render_template(
        "index.html",
        trending=trending_rows,
        recent=recent_rows,
        stats=stats,
        categories=VIDEO_CATEGORIES,
    )


@app.route("/watch/<video_id>")
def watch(video_id):
    """Video player page."""
    db = get_db()
    video = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url, a.is_human,
                  a.rtc_address, a.btc_address, a.eth_address,
                  a.sol_address, a.ltc_address, a.erg_address, a.paypal_email
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.video_id = ?""",
        (video_id,),
    ).fetchone()

    if not video:
        abort(404)

    # Record view (deduplicated: 1 view per IP per video per 30 min)
    ip = request.headers.get("X-Real-IP", request.remote_addr)
    VIEW_COOLDOWN = 1800  # 30 minutes
    recent = db.execute(
        "SELECT 1 FROM views WHERE video_id = ? AND ip_address = ? AND created_at > ?",
        (video_id, ip, time.time() - VIEW_COOLDOWN),
    ).fetchone()
    if not recent:
        db.execute(
            "INSERT INTO views (video_id, ip_address, created_at) VALUES (?, ?, ?)",
            (video_id, ip, time.time()),
        )
        db.execute("UPDATE videos SET views = views + 1 WHERE video_id = ?", (video_id,))
        db.commit()

    # Get comments
    comments = db.execute(
        """SELECT c.*, a.agent_name, a.display_name, a.avatar_url, a.is_human
           FROM comments c JOIN agents a ON c.agent_id = a.id
           WHERE c.video_id = ?
           ORDER BY c.created_at ASC""",
        (video_id,),
    ).fetchall()

    # Related videos (same agent or random)
    related = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url, a.is_human
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.video_id != ?
           ORDER BY CASE WHEN v.agent_id = ? THEN 0 ELSE 1 END, RANDOM()
           LIMIT 8""",
        (video_id, video["agent_id"]),
    ).fetchall()

    # Subscription data for follow button
    subscriber_count = db.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE following_id = ?",
        (video["agent_id"],),
    ).fetchone()[0]

    is_following = False
    if g.user:
        is_following = bool(db.execute(
            "SELECT 1 FROM subscriptions WHERE follower_id = ? AND following_id = ?",
            (g.user["id"], video["agent_id"]),
        ).fetchone())

    return render_template(
        "watch.html",
        video=video,
        comments=comments,
        related=related,
        subscriber_count=subscriber_count,
        is_following=is_following,
    )


@app.route("/embed/<video_id>")
def embed(video_id):
    """Branded embed player for iframes and Twitter player cards."""
    db = get_db()
    video = db.execute(
        "SELECT v.*, a.agent_name, a.display_name FROM videos v JOIN agents a ON v.agent_id = a.id WHERE v.video_id = ?",
        (video_id,),
    ).fetchone()
    if not video:
        abort(404)

    title_esc = (video["title"] or "").replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    creator_esc = (video["display_name"] or video["agent_name"] or "").replace("&", "&amp;").replace("<", "&lt;")

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#000;height:100vh;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden}}
video{{max-width:100%;max-height:100%;object-fit:contain;display:block}}
.overlay{{position:absolute;bottom:0;left:0;right:0;padding:12px 16px;background:linear-gradient(transparent,rgba(0,0,0,0.85));
 opacity:0;transition:opacity 0.3s;pointer-events:none;display:flex;align-items:flex-end;justify-content:space-between}}
body:hover .overlay{{opacity:1}}
.info{{color:#fff;min-width:0}}
.title{{font:600 14px/1.3 -apple-system,sans-serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:70vw}}
.creator{{font:12px -apple-system,sans-serif;color:#aaa;margin-top:2px}}
.brand{{pointer-events:auto;text-decoration:none;background:#3ea6ff;color:#0f0f0f;padding:6px 14px;border-radius:4px;
 font:700 12px -apple-system,sans-serif;white-space:nowrap;flex-shrink:0}}
.brand:hover{{background:#65b8ff}}
</style>
</head><body>
<video controls autoplay playsinline>
<source src="/api/videos/{video_id}/stream" type="video/mp4">
</video>
<div class="overlay">
<div class="info"><div class="title">{title_esc}</div><div class="creator">{creator_esc}</div></div>
<a class="brand" href="https://bottube.ai/watch/{video_id}" target="_blank">BoTTube</a>
</div>
</body></html>"""
    resp = Response(html, mimetype="text/html")
    # Allow embedding in any iframe
    resp.headers["X-Frame-Options"] = "ALLOWALL"
    resp.headers.pop("Content-Security-Policy", None)
    return resp


@app.route("/oembed")
def oembed():
    """oEmbed discovery endpoint. Returns JSON with iframe embed HTML."""
    url = request.args.get("url", "")
    fmt = request.args.get("format", "json")

    if fmt != "json":
        return jsonify({"error": "Only JSON format supported"}), 501

    # Extract video_id from URL
    match = re.search(r"/watch/([A-Za-z0-9_-]{11})", url)
    if not match:
        return jsonify({"error": "Invalid URL"}), 404

    video_id = match.group(1)
    db = get_db()
    video = db.execute(
        "SELECT v.*, a.agent_name, a.display_name FROM videos v JOIN agents a ON v.agent_id = a.id WHERE v.video_id = ?",
        (video_id,),
    ).fetchone()

    if not video:
        return jsonify({"error": "Video not found"}), 404

    w = request.args.get("maxwidth", video["width"] or 512, type=int)
    h = request.args.get("maxheight", video["height"] or 512, type=int)
    # Clamp dimensions
    w = min(w, 1920)
    h = min(h, 1080)

    return jsonify({
        "version": "1.0",
        "type": "video",
        "provider_name": "BoTTube",
        "provider_url": "https://bottube.ai",
        "title": video["title"],
        "author_name": video["display_name"] or video["agent_name"],
        "author_url": f"https://bottube.ai/agent/{video['agent_name']}",
        "width": w,
        "height": h,
        "html": f'<iframe src="https://bottube.ai/embed/{video_id}" width="{w}" height="{h}" frameborder="0" allowfullscreen></iframe>',
        "thumbnail_url": f"https://bottube.ai/thumbnails/{video['thumbnail']}" if video["thumbnail"] else "",
        "thumbnail_width": 320,
        "thumbnail_height": 180,
    })


@app.route("/agents")
def agents_page():
    """List all agents on the platform."""
    db = get_db()
    agents = db.execute(
        """SELECT a.*, COUNT(v.id) as video_count,
                  COALESCE(SUM(v.views), 0) as total_views
           FROM agents a LEFT JOIN videos v ON a.id = v.agent_id
           GROUP BY a.id
           ORDER BY total_views DESC""",
    ).fetchall()
    return render_template("agents.html", agents=agents)


@app.route("/agent/<agent_name>")
def channel(agent_name):
    """Agent channel page."""
    db = get_db()
    agent = db.execute(
        "SELECT * FROM agents WHERE agent_name = ?", (agent_name,)
    ).fetchone()
    if not agent:
        abort(404)

    videos = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.agent_id = ?
           ORDER BY v.created_at DESC""",
        (agent["id"],),
    ).fetchall()

    total_views = db.execute(
        "SELECT COALESCE(SUM(views), 0) FROM videos WHERE agent_id = ?",
        (agent["id"],),
    ).fetchone()[0]

    subscriber_count = db.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE following_id = ?",
        (agent["id"],),
    ).fetchone()[0]

    is_following = False
    if g.user:
        is_following = bool(db.execute(
            "SELECT 1 FROM subscriptions WHERE follower_id = ? AND following_id = ?",
            (g.user["id"], agent["id"]),
        ).fetchone())

    # Public playlists (or all if viewing own channel)
    viewer_id = g.user["id"] if g.user else None
    pl_filter = "" if viewer_id == agent["id"] else "AND p.visibility = 'public'"
    playlists = db.execute(
        f"""SELECT p.playlist_id, p.title, p.visibility, p.updated_at,
                   (SELECT COUNT(*) FROM playlist_items pi WHERE pi.playlist_id = p.id) as item_count
            FROM playlists p WHERE p.agent_id = ? {pl_filter}
            ORDER BY p.updated_at DESC LIMIT 20""",
        (agent["id"],),
    ).fetchall()

    return render_template(
        "channel.html",
        agent=agent,
        videos=videos,
        total_views=total_views,
        subscriber_count=subscriber_count,
        is_following=is_following,
        playlists=playlists,
    )


@app.route("/docs")
def docs_page():
    """API documentation page."""
    return render_template("docs.html")


# ── Blog routes ──────────────────────────────────────────────────────
BLOG_POSTS = [
    {
        "slug": "what-is-bottube",
        "template": "blog_bottube.html",
        "title": "What is BoTTube? The First Video Platform Built for AI Agents",
        "description": "BoTTube is a video-sharing platform where AI agents and humans create, upload, and interact with video content side by side. 131+ videos, 21 AI agents, open API, MIT licensed.",
        "author": "Scott Boudreaux",
        "date": "2026-02-01",
        "pub_rfc": "Sat, 01 Feb 2026 12:00:00 +0000",
    },
    {
        "slug": "rustchain-proof-of-antiquity",
        "template": "blog_rustchain.html",
        "title": "RustChain: The Blockchain That Rewards Vintage Hardware",
        "description": "A blockchain powered by Proof of Antiquity where a PowerPC G4 from 1999 earns 2.5x more than modern hardware. Six hardware fingerprint checks prevent VM spoofing.",
        "author": "Scott Boudreaux",
        "date": "2026-02-01",
        "pub_rfc": "Sat, 01 Feb 2026 12:30:00 +0000",
    },
    {
        "slug": "elyan-labs-ecosystem",
        "template": "blog_elyan_labs.html",
        "title": "The Elyan Labs Ecosystem: Open Source AI From Vintage Iron to Video Agents",
        "description": "How vintage PowerPC Macs, an IBM POWER8 mainframe, AI video agents, and a blockchain all connect in one open source ecosystem. 45+ repos, all MIT licensed.",
        "author": "Scott Boudreaux",
        "date": "2026-02-01",
        "pub_rfc": "Sat, 01 Feb 2026 13:00:00 +0000",
    },
]


@app.route("/blog")
def blog_index():
    """Blog listing page."""
    return render_template("blog.html")


@app.route("/blog/<slug>")
def blog_post(slug):
    """Individual blog post."""
    for post in BLOG_POSTS:
        if post["slug"] == slug:
            return render_template(post["template"])
    abort(404)


@app.route("/blog/rss")
def blog_rss():
    """RSS 2.0 feed for blog articles."""
    base = "https://bottube.ai"
    items = []
    for post in BLOG_POSTS:
        link = f"{base}/blog/{post['slug']}"
        items.append(f"""    <item>
      <title><![CDATA[{post["title"]}]]></title>
      <link>{link}</link>
      <guid isPermaLink="true">{link}</guid>
      <pubDate>{post["pub_rfc"]}</pubDate>
      <dc:creator><![CDATA[{post["author"]}]]></dc:creator>
      <description><![CDATA[{post["description"]}]]></description>
    </item>""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>BoTTube Blog - Elyan Labs</title>
    <link>{base}/blog</link>
    <description>Articles about BoTTube, RustChain, AI agents, and the Elyan Labs open source ecosystem.</description>
    <language>en-us</language>
    <lastBuildDate>{BLOG_POSTS[0]["pub_rfc"]}</lastBuildDate>
    <atom:link href="{base}/blog/rss" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""

    resp = app.response_class(xml, mimetype="application/rss+xml")
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


@app.route("/dashboard")
def dashboard_page():
    """Creator dashboard for logged-in users."""
    if not g.user:
        return redirect(url_for("login"))

    db = get_db()
    uid = g.user["id"]

    # Your videos with stats
    videos = db.execute(
        """SELECT video_id, title, thumbnail, views, likes, dislikes, duration_sec, category, created_at
           FROM videos WHERE agent_id = ? ORDER BY created_at DESC""",
        (uid,),
    ).fetchall()

    # Aggregate stats
    totals = db.execute(
        """SELECT COALESCE(SUM(views), 0) as total_views,
                  COALESCE(SUM(likes), 0) as total_likes,
                  COUNT(*) as video_count
           FROM videos WHERE agent_id = ?""",
        (uid,),
    ).fetchone()

    subscriber_count = db.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE following_id = ?", (uid,)
    ).fetchone()[0]

    total_comments = db.execute(
        """SELECT COUNT(*) FROM comments c
           JOIN videos v ON c.video_id = v.video_id
           WHERE v.agent_id = ?""",
        (uid,),
    ).fetchone()[0]

    # Playlists
    playlists = db.execute(
        """SELECT p.playlist_id, p.title, p.visibility, p.updated_at,
                  (SELECT COUNT(*) FROM playlist_items pi WHERE pi.playlist_id = p.id) as item_count
           FROM playlists p WHERE p.agent_id = ?
           ORDER BY p.updated_at DESC""",
        (uid,),
    ).fetchall()

    # Recent notifications (last 10)
    notifications = db.execute(
        """SELECT type, message, from_agent, video_id, is_read, created_at
           FROM notifications WHERE agent_id = ?
           ORDER BY created_at DESC LIMIT 10""",
        (uid,),
    ).fetchall()

    # RTC balance
    rtc_balance = g.user.get("rtc_balance", 0) or 0

    # Recent earnings (last 10)
    earnings = db.execute(
        """SELECT amount, reason, video_id, created_at
           FROM earnings WHERE agent_id = ?
           ORDER BY created_at DESC LIMIT 10""",
        (uid,),
    ).fetchall()

    return render_template(
        "dashboard.html",
        videos=videos,
        totals=totals,
        subscriber_count=subscriber_count,
        total_comments=total_comments,
        playlists=playlists,
        notifications=notifications,
        rtc_balance=rtc_balance,
        earnings=earnings,
    )


@app.route("/join")
def join_page():
    """Instructions for agents and humans to join BoTTube."""
    return render_template("join.html")


@app.route("/search")
def search_page():
    """Search results page."""
    q = request.args.get("q", "").strip()
    videos = []

    if q:
        db = get_db()
        like_q = f"%{q}%"
        videos = db.execute(
            """SELECT v.*, a.agent_name, a.display_name, a.avatar_url, a.is_human
               FROM videos v JOIN agents a ON v.agent_id = a.id
               WHERE v.title LIKE ? OR v.description LIKE ? OR v.tags LIKE ? OR a.agent_name LIKE ?
               ORDER BY v.views DESC, v.created_at DESC
               LIMIT 50""",
            (like_q, like_q, like_q, like_q),
        ).fetchall()

    return render_template("search.html", query=q, videos=videos)


@app.route("/trending")
def trending_page():
    """Dedicated trending page with top 50 videos."""
    db = get_db()
    rows = _get_trending_videos(db, limit=50)
    return render_template("trending.html", videos=rows)


@app.route("/categories")
def categories_page():
    """Browse all video categories."""
    db = get_db()
    # Count videos per category in one query
    rows = db.execute(
        "SELECT category, COUNT(*) as cnt FROM videos GROUP BY category"
    ).fetchall()
    counts = {r["category"]: r["cnt"] for r in rows}
    total = sum(counts.values())
    return render_template(
        "categories.html",
        categories=VIDEO_CATEGORIES,
        counts=counts,
        total_videos=total,
    )


@app.route("/upload", methods=["GET", "POST"])
def upload_page():
    """Upload form page for logged-in humans."""
    if request.method == "GET":
        return render_template("upload.html", categories=VIDEO_CATEGORIES)

    _verify_csrf()

    # Handle browser-based upload for logged-in users
    if not g.user:
        flash("You must be logged in to upload.", "error")
        return redirect(url_for("login"))

    if "video" not in request.files:
        flash("No video file selected.", "error")
        return render_template("upload.html", categories=VIDEO_CATEGORIES)

    video_file = request.files["video"]
    if not video_file.filename:
        flash("No file selected.", "error")
        return render_template("upload.html", categories=VIDEO_CATEGORIES)

    ext = Path(video_file.filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXT:
        flash(f"Invalid video format. Allowed: {', '.join(ALLOWED_VIDEO_EXT)}", "error")
        return render_template("upload.html", categories=VIDEO_CATEGORIES)

    title = request.form.get("title", "").strip()[:MAX_TITLE_LENGTH]
    if not title:
        title = Path(video_file.filename).stem[:MAX_TITLE_LENGTH]

    description = request.form.get("description", "").strip()[:MAX_DESCRIPTION_LENGTH]
    tags_raw = request.form.get("tags", "")
    tags = [t.strip()[:MAX_TAG_LENGTH] for t in tags_raw.split(",") if t.strip()][:MAX_TAGS]
    category = request.form.get("category", "other").strip().lower()
    if category not in CATEGORY_MAP:
        category = "other"

    video_id = gen_video_id()
    while (VIDEO_DIR / f"{video_id}{ext}").exists():
        video_id = gen_video_id()

    filename = f"{video_id}{ext}"
    video_path = VIDEO_DIR / filename
    video_file.save(str(video_path))

    duration, width, height = get_video_metadata(video_path)

    # Per-category limits
    cat_limits = CATEGORY_LIMITS.get(category, {})
    max_dur = cat_limits.get("max_duration", MAX_VIDEO_DURATION)
    max_file = cat_limits.get("max_file_mb", MAX_FINAL_FILE_SIZE / (1024 * 1024))
    keep_audio = cat_limits.get("keep_audio", False)

    if duration > max_dur:
        video_path.unlink(missing_ok=True)
        flash(f"Video too long ({duration:.1f}s). Max for {category}: {max_dur} seconds.", "error")
        return render_template("upload.html", categories=VIDEO_CATEGORIES)

    # Always transcode to enforce size/format constraints
    transcoded_path = VIDEO_DIR / f"{video_id}_tc.mp4"
    if transcode_video(video_path, transcoded_path, keep_audio=keep_audio,
                       target_file_mb=max_file, duration_hint=duration):
        video_path.unlink(missing_ok=True)
        filename = f"{video_id}.mp4"
        final_path = VIDEO_DIR / filename
        transcoded_path.rename(final_path)
        video_path = final_path
        duration, width, height = get_video_metadata(final_path)
    else:
        video_path.unlink(missing_ok=True)
        transcoded_path.unlink(missing_ok=True)
        flash("Video processing failed.", "error")
        return render_template("upload.html", categories=VIDEO_CATEGORIES)

    # Enforce max final file size (per-category)
    max_file_bytes = int(max_file * 1024 * 1024)
    final_size = video_path.stat().st_size
    if final_size > max_file_bytes:
        video_path.unlink(missing_ok=True)
        flash(f"Video too large after processing ({final_size // 1024} KB). Max: {max_file_bytes // 1024} KB.", "error")
        return render_template("upload.html", categories=VIDEO_CATEGORIES)

    # Thumbnail (max 2MB)
    thumb_filename = ""
    MAX_THUMB_SIZE = 2 * 1024 * 1024
    if "thumbnail" in request.files and request.files["thumbnail"].filename:
        thumb_file = request.files["thumbnail"]
        thumb_file.seek(0, 2)
        if thumb_file.tell() > MAX_THUMB_SIZE:
            flash("Thumbnail must be 2MB or smaller.", "error")
            return redirect(url_for("upload_page"))
        thumb_file.seek(0)
        thumb_ext = Path(thumb_file.filename).suffix.lower()
        if thumb_ext in ALLOWED_THUMB_EXT:
            thumb_filename = f"{video_id}{thumb_ext}"
            thumb_file.save(str(THUMB_DIR / thumb_filename))
    else:
        thumb_filename = f"{video_id}.jpg"
        final_video = VIDEO_DIR / filename
        if not generate_thumbnail(final_video, THUMB_DIR / thumb_filename):
            thumb_filename = ""

    db = get_db()
    db.execute(
        """INSERT INTO videos
           (video_id, agent_id, title, description, filename, thumbnail,
            duration_sec, width, height, tags, scene_description, category, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)""",
        (video_id, g.user["id"], title, description, filename,
         thumb_filename, duration, width, height, json.dumps(tags), category, time.time()),
    )
    award_rtc(db, g.user["id"], RTC_REWARD_UPLOAD, "video_upload", video_id)
    db.commit()

    return redirect(f"{g.prefix}/watch/{video_id}")


# ---------------------------------------------------------------------------
# Giveaway
# ---------------------------------------------------------------------------

@app.route("/giveaway")
def giveaway_page():
    """GPU giveaway landing page with countdown, prizes, and leaderboard."""
    db = get_db()
    now = time.time()

    # Check if user has entered
    user_entered = False
    user_eligible = False
    if g.user:
        entry = db.execute(
            "SELECT * FROM giveaway_entrants WHERE agent_id = ?", (g.user["id"],)
        ).fetchone()
        user_entered = entry is not None
        try:
            email_verified = g.user["email_verified"]
        except (IndexError, KeyError):
            email_verified = 0
        user_eligible = (
            g.user["is_human"] == 1
            and email_verified == 1
        )

    # Get leaderboard: top 50 entrants by RTC earned
    leaderboard = db.execute(
        """SELECT a.agent_name, a.display_name, a.rtc_balance,
                  COUNT(v.id) AS video_count,
                  COALESCE(SUM(v.views), 0) AS total_views,
                  ge.entered_at
           FROM giveaway_entrants ge
           JOIN agents a ON ge.agent_id = a.id
           LEFT JOIN videos v ON v.agent_id = a.id
           WHERE ge.disqualified = 0
           GROUP BY a.id
           ORDER BY a.rtc_balance DESC
           LIMIT 50""",
    ).fetchall()

    total_entrants = db.execute(
        "SELECT COUNT(*) FROM giveaway_entrants WHERE disqualified = 0"
    ).fetchone()[0]

    return render_template(
        "giveaway.html",
        prizes=GIVEAWAY_PRIZES,
        giveaway_active=GIVEAWAY_ACTIVE,
        giveaway_start=GIVEAWAY_START,
        giveaway_end=GIVEAWAY_END,
        leaderboard=leaderboard,
        total_entrants=total_entrants,
        user_entered=user_entered,
        user_eligible=user_eligible,
        now=now,
    )


@app.route("/giveaway/enter", methods=["POST"])
def giveaway_enter():
    """Enter the giveaway. Requires logged-in human with verified email."""
    _verify_csrf()

    if not g.user:
        flash("You must be signed in to enter.", "error")
        return redirect(url_for("login"))

    if not GIVEAWAY_ACTIVE:
        flash("The giveaway is not currently active.", "error")
        return redirect(url_for("giveaway_page"))

    now = time.time()
    if now < GIVEAWAY_START:
        flash("The giveaway hasn't started yet.", "error")
        return redirect(url_for("giveaway_page"))
    if now > GIVEAWAY_END:
        flash("The giveaway has ended.", "error")
        return redirect(url_for("giveaway_page"))

    if not g.user["is_human"]:
        flash("Only human accounts can enter the giveaway.", "error")
        return redirect(url_for("giveaway_page"))

    try:
        email_verified = g.user["email_verified"]
    except (IndexError, KeyError):
        email_verified = 0
    if GIVEAWAY_REQUIRE_EMAIL and not email_verified:
        flash("You must verify your email before entering. Check your profile.", "error")
        return redirect(url_for("giveaway_page"))

    db = get_db()
    try:
        db.execute(
            "INSERT INTO giveaway_entrants (agent_id, entered_at, eligible) VALUES (?, ?, 1)",
            (g.user["id"], now),
        )
        db.commit()
        flash("You're in! Earn RTC to climb the leaderboard.", "success")
    except sqlite3.IntegrityError:
        flash("You've already entered the giveaway.", "error")

    return redirect(url_for("giveaway_page"))


@app.route("/api/giveaway/leaderboard")
def giveaway_leaderboard_api():
    """JSON API: giveaway leaderboard for external consumption."""
    db = get_db()
    rows = db.execute(
        """SELECT a.agent_name, a.display_name, a.rtc_balance,
                  COUNT(v.id) AS video_count,
                  COALESCE(SUM(v.views), 0) AS total_views
           FROM giveaway_entrants ge
           JOIN agents a ON ge.agent_id = a.id
           LEFT JOIN videos v ON v.agent_id = a.id
           WHERE ge.disqualified = 0
           GROUP BY a.id
           ORDER BY a.rtc_balance DESC
           LIMIT 50""",
    ).fetchall()

    return jsonify({
        "leaderboard": [
            {
                "rank": i + 1,
                "agent_name": r["agent_name"],
                "display_name": r["display_name"],
                "rtc_balance": round(r["rtc_balance"], 4),
                "video_count": r["video_count"],
                "total_views": r["total_views"],
            }
            for i, r in enumerate(rows)
        ],
        "prizes": GIVEAWAY_PRIZES,
        "giveaway_active": GIVEAWAY_ACTIVE,
        "ends_at": GIVEAWAY_END,
    })


# ---------------------------------------------------------------------------
# Admin: Visitor Analytics
# ---------------------------------------------------------------------------

ADMIN_KEY = os.environ.get("BOTTUBE_ADMIN_KEY", "")
if not ADMIN_KEY:
    ADMIN_KEY = secrets.token_hex(32)
    print(f"[BoTTube] WARNING: BOTTUBE_ADMIN_KEY not set. Generated ephemeral key: {ADMIN_KEY}")


@app.route("/api/admin/visitors")
def admin_visitors():
    """View visitor analytics. Requires admin key via header."""
    provided = request.headers.get("X-Admin-Key", "") or request.args.get("key", "")
    if not provided or provided != ADMIN_KEY:
        abort(403)

    hours = min(168, max(1, request.args.get("hours", 24, type=int)))
    cutoff = time.time() - hours * 3600

    stats = {
        "unique_ips": set(),
        "unique_visitors": set(),
        "new_visitors": 0,
        "total_requests": 0,
        "scrapers": {},
        "top_paths": {},
        "top_ips": {},
    }

    try:
        with open(_VISITOR_LOG_PATH) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if entry.get("ts", 0) < cutoff:
                    continue
                stats["total_requests"] += 1
                stats["unique_ips"].add(entry.get("ip", ""))
                stats["unique_visitors"].add(entry.get("vid", ""))
                if entry.get("new"):
                    stats["new_visitors"] += 1
                scraper = entry.get("scraper")
                if scraper:
                    stats["scrapers"][scraper] = stats["scrapers"].get(scraper, 0) + 1
                path = entry.get("path", "")
                stats["top_paths"][path] = stats["top_paths"].get(path, 0) + 1
                ip = entry.get("ip", "")
                stats["top_ips"][ip] = stats["top_ips"].get(ip, 0) + 1
    except FileNotFoundError:
        pass

    # Sort and limit top items
    top_paths = sorted(stats["top_paths"].items(), key=lambda x: -x[1])[:20]
    top_ips = sorted(stats["top_ips"].items(), key=lambda x: -x[1])[:20]

    return jsonify({
        "hours": hours,
        "total_requests": stats["total_requests"],
        "unique_ips": len(stats["unique_ips"]),
        "unique_visitors": len(stats["unique_visitors"]),
        "new_visitors": stats["new_visitors"],
        "scrapers": stats["scrapers"],
        "top_paths": dict(top_paths),
        "top_ips": dict(top_ips),
    })


# ---------------------------------------------------------------------------
# Admin: Duplicate Comment Scraper
# ---------------------------------------------------------------------------

@app.route("/api/admin/duplicate-comments")
def admin_duplicate_comments():
    """Find and optionally remove duplicate comments.

    Duplicates = same agent_id + video_id + content (exact match).
    Keeps the OLDEST comment (lowest id), removes newer copies.

    Query params:
        key       - admin key (required)
        dry_run   - if "0", actually delete; default is dry-run
        window_h  - only check comments from last N hours (default: all)
    """
    provided = request.headers.get("X-Admin-Key", "") or request.args.get("key", "")
    if not provided or provided != ADMIN_KEY:
        abort(403)

    dry_run = request.args.get("dry_run", "1") != "0"
    window_h = request.args.get("window_h", 0, type=int)

    db = get_db()

    # Build the query to find duplicates
    where_clause = ""
    params = []
    if window_h > 0:
        cutoff = time.time() - window_h * 3600
        where_clause = "WHERE c1.created_at > ?"
        params.append(cutoff)

    # Find all duplicate groups: same agent_id + video_id + content
    rows = db.execute(f"""
        SELECT c1.agent_id, c1.video_id, c1.content, COUNT(*) as cnt,
               MIN(c1.id) as keep_id, GROUP_CONCAT(c1.id) as all_ids
        FROM comments c1
        {where_clause}
        GROUP BY c1.agent_id, c1.video_id, c1.content
        HAVING cnt > 1
        ORDER BY cnt DESC
    """, params).fetchall()

    duplicates = []
    total_to_remove = 0

    for row in rows:
        all_ids = [int(x) for x in row["all_ids"].split(",")]
        keep_id = row["keep_id"]
        remove_ids = [i for i in all_ids if i != keep_id]
        total_to_remove += len(remove_ids)

        agent = db.execute("SELECT agent_name FROM agents WHERE id = ?",
                           (row["agent_id"],)).fetchone()
        agent_name = agent["agent_name"] if agent else f"agent#{row['agent_id']}"

        duplicates.append({
            "agent": agent_name,
            "video_id": row["video_id"],
            "content_preview": row["content"][:80],
            "count": row["cnt"],
            "keeping": keep_id,
            "removing": remove_ids,
        })

    removed = 0
    if not dry_run and total_to_remove > 0:
        for dup in duplicates:
            for rid in dup["removing"]:
                db.execute("DELETE FROM comment_votes WHERE comment_id = ?", (rid,))
                db.execute("DELETE FROM comments WHERE id = ?", (rid,))
                removed += 1
        db.commit()

    return jsonify({
        "dry_run": dry_run,
        "duplicate_groups": len(duplicates),
        "total_duplicates": total_to_remove,
        "removed": removed,
        "details": duplicates[:50],
    })


@app.route("/api/admin/comment-cleanup", methods=["POST"])
def admin_comment_cleanup():
    """Full comment cleanup: remove duplicates + optionally prune bot spam.

    POST JSON:
        key          - admin key (required)
        remove_dupes - remove exact duplicates (default true)
        max_similar  - max near-identical comments per agent per video (default 3)
    """
    provided = request.headers.get("X-Admin-Key", "") or request.args.get("key", "")
    if not provided or provided != ADMIN_KEY:
        abort(403)

    data = request.get_json(silent=True) or {}
    remove_dupes = data.get("remove_dupes", True)
    max_similar = data.get("max_similar", 3)

    db = get_db()
    removed_dupes = 0
    removed_spam = 0

    # Phase 1: Exact duplicates (same agent + video + content)
    if remove_dupes:
        rows = db.execute("""
            SELECT agent_id, video_id, content, COUNT(*) as cnt,
                   MIN(id) as keep_id, GROUP_CONCAT(id) as all_ids
            FROM comments
            GROUP BY agent_id, video_id, content
            HAVING cnt > 1
        """).fetchall()

        for row in rows:
            all_ids = [int(x) for x in row["all_ids"].split(",")]
            keep_id = row["keep_id"]
            for rid in all_ids:
                if rid != keep_id:
                    db.execute("DELETE FROM comment_votes WHERE comment_id = ?", (rid,))
                    db.execute("DELETE FROM comments WHERE id = ?", (rid,))
                    removed_dupes += 1

    # Phase 2: Excessive comments from same agent on same video
    if max_similar > 0:
        heavy = db.execute("""
            SELECT agent_id, video_id, COUNT(*) as cnt
            FROM comments
            GROUP BY agent_id, video_id
            HAVING cnt > ?
        """, (max_similar,)).fetchall()

        for row in heavy:
            excess = db.execute("""
                SELECT id FROM comments
                WHERE agent_id = ? AND video_id = ?
                ORDER BY created_at ASC
                LIMIT -1 OFFSET ?
            """, (row["agent_id"], row["video_id"], max_similar)).fetchall()

            for c in excess:
                db.execute("DELETE FROM comment_votes WHERE comment_id = ?", (c["id"],))
                db.execute("DELETE FROM comments WHERE id = ?", (c["id"],))
                removed_spam += 1

    if removed_dupes > 0 or removed_spam > 0:
        db.commit()

    return jsonify({
        "removed_duplicates": removed_dupes,
        "removed_excess": removed_spam,
        "max_similar_per_video": max_similar,
        "total_removed": removed_dupes + removed_spam,
    })


# ---------------------------------------------------------------------------
# RSS Feeds
# ---------------------------------------------------------------------------

def _xml_escape(s: str) -> str:
    """Escape a string for use in XML outside CDATA sections."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def _cdata_safe(s: str) -> str:
    """Escape ]]> inside CDATA sections to prevent breakout."""
    return s.replace("]]>", "]]]]><![CDATA[>")


@app.route("/agent/<agent_name>/rss")
def agent_rss(agent_name):
    """RSS 2.0 feed for a channel's videos."""
    db = get_db()
    agent = db.execute("SELECT * FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
    if not agent:
        abort(404)

    videos = db.execute(
        """SELECT video_id, title, description, created_at, duration_sec, thumbnail, views
           FROM videos WHERE agent_id = ? ORDER BY created_at DESC LIMIT 50""",
        (agent["id"],),
    ).fetchall()

    base = request.url_root.rstrip("/").replace("http://", "https://")
    prefix = app.config.get("APPLICATION_ROOT", "").rstrip("/")

    items = []
    for v in videos:
        pub_date = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime(v["created_at"]))
        link = f"{base}{prefix}/watch/{v['video_id']}"
        desc = v["description"] or v["title"]
        thumb_tag = ""
        if v["thumbnail"]:
            thumb_url = f"{base}{prefix}/thumbnails/{v['thumbnail']}"
            thumb_tag = f'<img src="{thumb_url}" /><br/>'
        items.append(f"""    <item>
      <title><![CDATA[{_cdata_safe(v["title"])}]]></title>
      <link>{link}</link>
      <guid isPermaLink="true">{link}</guid>
      <pubDate>{pub_date}</pubDate>
      <description><![CDATA[{thumb_tag}{_cdata_safe(desc)}]]></description>
    </item>""")

    channel_link = f"{base}{prefix}/agent/{agent_name}"
    display = _xml_escape(agent["display_name"] or agent["agent_name"])
    build_date = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{display} - BoTTube</title>
    <link>{channel_link}</link>
    <description><![CDATA[Videos by {_cdata_safe(display)} on BoTTube]]></description>
    <language>en-us</language>
    <lastBuildDate>{build_date}</lastBuildDate>
    <atom:link href="{base}{prefix}/agent/{agent_name}/rss" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""

    resp = app.response_class(xml, mimetype="application/rss+xml")
    resp.headers["Cache-Control"] = "public, max-age=600"
    return resp


# Global RSS feed (latest videos across all channels)
@app.route("/rss")
def global_rss():
    """RSS 2.0 feed for all recent videos on BoTTube."""
    db = get_db()
    videos = db.execute(
        """SELECT v.video_id, v.title, v.description, v.created_at, v.thumbnail,
                  a.agent_name, a.display_name
           FROM videos v JOIN agents a ON v.agent_id = a.id
           ORDER BY v.created_at DESC LIMIT 50""",
    ).fetchall()

    base = request.url_root.rstrip("/").replace("http://", "https://")
    prefix = app.config.get("APPLICATION_ROOT", "").rstrip("/")

    items = []
    for v in videos:
        pub_date = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime(v["created_at"]))
        link = f"{base}{prefix}/watch/{v['video_id']}"
        author_display = _xml_escape(v["display_name"] or v["agent_name"])
        desc = v["description"] or v["title"]
        thumb_tag = ""
        if v["thumbnail"]:
            thumb_url = f"{base}{prefix}/thumbnails/{v['thumbnail']}"
            thumb_tag = f'<img src="{thumb_url}" /><br/>'
        items.append(f"""    <item>
      <title><![CDATA[{_cdata_safe(v["title"])}]]></title>
      <link>{link}</link>
      <guid isPermaLink="true">{link}</guid>
      <pubDate>{pub_date}</pubDate>
      <author>{_xml_escape(v["agent_name"])}</author>
      <description><![CDATA[{thumb_tag}By {_cdata_safe(author_display)} - {_cdata_safe(desc)}]]></description>
    </item>""")

    build_date = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>BoTTube - Latest Videos</title>
    <link>{base}{prefix}/</link>
    <description>Latest videos from AI agents on BoTTube</description>
    <language>en-us</language>
    <lastBuildDate>{build_date}</lastBuildDate>
    <atom:link href="{base}{prefix}/rss" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""

    resp = app.response_class(xml, mimetype="application/rss+xml")
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


# ---------------------------------------------------------------------------
# SEO & Crawler Routes (robots.txt, sitemap.xml)
# ---------------------------------------------------------------------------
from seo_routes import seo_bp
app.register_blueprint(seo_bp)

# ---------------------------------------------------------------------------
# Admin: Content Moderation (Ban / Unban / Nuke)
# ---------------------------------------------------------------------------


def _require_admin():
    """Check admin key from header or query param. Returns None if OK, or error response."""
    provided = request.headers.get("X-Admin-Key", "") or request.args.get("key", "")
    if not provided or provided != ADMIN_KEY:
        return jsonify({"error": "Forbidden"}), 403
    return None


@app.route("/api/admin/ban", methods=["POST"])
def admin_ban_agent():
    """Ban an agent by name. Requires admin key.

    POST JSON: {"agent_name": "fredrick", "reason": "spam"}
    """
    err = _require_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    agent_name = data.get("agent_name", "").strip()
    reason = data.get("reason", "Banned by admin").strip()

    if not agent_name:
        return jsonify({"error": "agent_name required"}), 400

    db = get_db()
    agent = db.execute(
        "SELECT id, agent_name, is_banned FROM agents WHERE agent_name = ?",
        (agent_name,),
    ).fetchone()
    if not agent:
        return jsonify({"error": f"Agent '{agent_name}' not found"}), 404

    if agent["is_banned"]:
        return jsonify({"ok": True, "already_banned": True, "agent": agent_name})

    db.execute(
        "UPDATE agents SET is_banned = 1, ban_reason = ?, banned_at = ? WHERE id = ?",
        (reason, time.time(), agent["id"]),
    )
    db.commit()
    app.logger.warning("ADMIN BAN: agent=%s reason='%s'", agent_name, reason)
    return jsonify({"ok": True, "banned": agent_name, "reason": reason})


@app.route("/api/admin/unban", methods=["POST"])
def admin_unban_agent():
    """Unban an agent by name. Requires admin key.

    POST JSON: {"agent_name": "fredrick"}
    """
    err = _require_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    agent_name = data.get("agent_name", "").strip()

    if not agent_name:
        return jsonify({"error": "agent_name required"}), 400

    db = get_db()
    db.execute(
        "UPDATE agents SET is_banned = 0, ban_reason = '', banned_at = 0 WHERE agent_name = ?",
        (agent_name,),
    )
    db.commit()
    app.logger.info("ADMIN UNBAN: agent=%s", agent_name)
    return jsonify({"ok": True, "unbanned": agent_name})


@app.route("/api/admin/nuke", methods=["POST"])
def admin_nuke_agent():
    """Ban an agent AND remove all their videos + comments. Nuclear option.

    POST JSON: {"agent_name": "fredrick", "reason": "spam bot"}
    """
    err = _require_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    agent_name = data.get("agent_name", "").strip()
    reason = data.get("reason", "Nuked by admin").strip()

    if not agent_name:
        return jsonify({"error": "agent_name required"}), 400

    db = get_db()
    agent = db.execute(
        "SELECT id, agent_name FROM agents WHERE agent_name = ?",
        (agent_name,),
    ).fetchone()
    if not agent:
        return jsonify({"error": f"Agent '{agent_name}' not found"}), 404

    agent_id = agent["id"]

    # Ban the agent
    db.execute(
        "UPDATE agents SET is_banned = 1, ban_reason = ?, banned_at = ? WHERE id = ?",
        (reason, time.time(), agent_id),
    )

    # Remove all their videos (mark as removed, delete files)
    videos = db.execute(
        "SELECT video_id, filename, thumbnail FROM videos WHERE agent_id = ?",
        (agent_id,),
    ).fetchall()

    removed_videos = 0
    for v in videos:
        # Delete video file
        vpath = VIDEO_DIR / v["filename"]
        vpath.unlink(missing_ok=True)
        # Delete thumbnail
        if v["thumbnail"]:
            tpath = THUMB_DIR / v["thumbnail"]
            tpath.unlink(missing_ok=True)
        removed_videos += 1

    # Delete video records
    db.execute("DELETE FROM videos WHERE agent_id = ?", (agent_id,))
    # Delete their comments
    removed_comments = db.execute(
        "SELECT changes()", ()
    ).fetchone()
    db.execute("DELETE FROM comments WHERE agent_id = ?", (agent_id,))
    # Delete their votes
    db.execute("DELETE FROM votes WHERE agent_id = ?", (agent_id,))

    db.commit()
    app.logger.warning(
        "ADMIN NUKE: agent=%s videos=%d reason='%s'",
        agent_name, removed_videos, reason,
    )
    return jsonify({
        "ok": True,
        "nuked": agent_name,
        "videos_removed": removed_videos,
        "reason": reason,
    })


@app.route("/api/admin/remove-video", methods=["POST"])
def admin_remove_video():
    """Remove a specific video by ID. Requires admin key.

    POST JSON: {"video_id": "abc123", "reason": "policy violation"}
    """
    err = _require_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    video_id = data.get("video_id", "").strip()
    reason = data.get("reason", "Removed by admin").strip()

    if not video_id:
        return jsonify({"error": "video_id required"}), 400

    db = get_db()
    video = db.execute(
        "SELECT id, filename, thumbnail, agent_id FROM videos WHERE video_id = ?",
        (video_id,),
    ).fetchone()
    if not video:
        return jsonify({"error": f"Video '{video_id}' not found"}), 404

    # Delete files
    vpath = VIDEO_DIR / video["filename"]
    vpath.unlink(missing_ok=True)
    if video["thumbnail"]:
        tpath = THUMB_DIR / video["thumbnail"]
        tpath.unlink(missing_ok=True)

    # Delete record
    db.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))
    db.commit()

    app.logger.warning("ADMIN REMOVE VIDEO: %s reason='%s'", video_id, reason)
    return jsonify({"ok": True, "removed": video_id, "reason": reason})


@app.route("/api/admin/scan-content", methods=["GET"])
def admin_scan_content():
    """Scan recent videos against the content blocklist. Requires admin key.

    Returns any flagged content. Does NOT auto-remove (use nuke/remove for that).
    Query params: hours=24 (how far back to scan)
    """
    err = _require_admin()
    if err:
        return err

    hours = min(168, max(1, request.args.get("hours", 24, type=int)))
    cutoff = time.time() - hours * 3600

    db = get_db()
    videos = db.execute(
        "SELECT v.video_id, v.title, v.description, v.tags, v.category, "
        "v.created_at, a.agent_name "
        "FROM videos v JOIN agents a ON v.agent_id = a.id "
        "WHERE v.created_at > ? ORDER BY v.created_at DESC",
        (cutoff,),
    ).fetchall()

    flagged = []
    for v in videos:
        tags = json.loads(v["tags"]) if v["tags"] else []
        term = _content_check(v["title"], v["description"], tags)
        if term:
            flagged.append({
                "video_id": v["video_id"],
                "title": v["title"],
                "agent": v["agent_name"],
                "matched_term": term,
                "category": v["category"],
            })

    return jsonify({
        "scanned": len(videos),
        "flagged": len(flagged),
        "results": flagged,
        "hours": hours,
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print(f"[BoTTube] Starting on port 8097 - v{APP_VERSION}")
    print(f"[BoTTube] DB: {DB_PATH}")
    print(f"[BoTTube] Videos: {VIDEO_DIR}")
    app.run(host="0.0.0.0", port=8097, debug=False)
