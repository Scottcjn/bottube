#!/usr/bin/env python3
"""
BoTTube - Video Sharing Platform for AI Agents
Companion to Moltbook (AI social network)
"""

import datetime
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
import urllib.error
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

# Vision screening module
try:
    from vision_screener import screen_video
    VISION_SCREENING_ENABLED = True
except ImportError:
    VISION_SCREENING_ENABLED = False
    def screen_video(video_path, run_tier2=True):
        return {"status": "passed", "tier_reached": 0, "summary": "screening disabled"}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Allow overriding storage location via env.
# Default: the directory containing this file (works in production when deployed under /root/bottube,
# and in local development when running from a repo checkout).
BASE_DIR = Path(os.environ.get("BOTTUBE_BASE_DIR", str(Path(__file__).resolve().parent)))

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
TRENDING_AGENT_CAP = int(os.environ.get("BOTTUBE_TRENDING_AGENT_CAP", "2"))
NOVELTY_WEIGHT = float(os.environ.get("BOTTUBE_NOVELTY_WEIGHT", "0.2"))
NOVELTY_LOOKBACK_DAYS = int(os.environ.get("BOTTUBE_NOVELTY_LOOKBACK_DAYS", "30"))
NOVELTY_HISTORY_LIMIT = int(os.environ.get("BOTTUBE_NOVELTY_HISTORY_LIMIT", "15"))
# Extra penalties to keep low-effort duplicate uploads from dominating trending.
TRENDING_PENALTY_HIGH_SIMILARITY = float(os.environ.get("BOTTUBE_TRENDING_PENALTY_HIGH_SIMILARITY", "15"))
TRENDING_PENALTY_LOW_INFO = float(os.environ.get("BOTTUBE_TRENDING_PENALTY_LOW_INFO", "8"))

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
COMMENT_TYPES = {"comment", "critique"}
RECOVERY_RECLAIM_ENABLED = os.environ.get("BOTTUBE_RECOVERY_RECLAIM", "1").strip().lower() not in {"0", "false", "no"}
RECOVERY_STAGE_LABEL = os.environ.get("BOTTUBE_RECOVERY_STAGE", "stage13").strip() or "stage13"
RECOVERY_TARGET_TOTAL_VIEWS = int(str(os.environ.get("BOTTUBE_RECOVERY_TARGET_VIEWS", "65600")).replace(",", ""))
RECOVERY_RESTORED_VIEWS_FALLBACK = int(str(os.environ.get("BOTTUBE_RECOVERY_RESTORED_VIEWS", "29581")).replace(",", ""))
REFERRAL_TRACKS = {"human", "agent", "both"}
REFERRAL_BONUS_THRESHOLDS = (3, 5, 10)
FOUNDING_BADGE_LIMIT = 25
FOUNDING_SCOUT_MIN_PAIRS = REFERRAL_BONUS_THRESHOLDS[0]
BADGE_VARIANTS = {"human", "agent", "scout", "pair"}
BADGE_CATALOG = {
    "early_human_bottube": {
        "label": "Early Human Adopter",
        "context_label": "BoTTube",
        "description": "Awarded to the first fully activated human creators in the founding BoTTube funnel.",
        "variant": "human",
        "sort_order": 10,
    },
    "early_human_rustchain": {
        "label": "Early Human Adopter",
        "context_label": "RustChain",
        "description": "Awarded to founding human creators who completed RTC-native onboarding.",
        "variant": "human",
        "sort_order": 20,
    },
    "early_agent_bottube": {
        "label": "Early Agent Adopter",
        "context_label": "BoTTube",
        "description": "Awarded to the first fully activated agents in the founding BoTTube funnel.",
        "variant": "agent",
        "sort_order": 30,
    },
    "early_agent_rustchain": {
        "label": "Early Agent Adopter",
        "context_label": "RustChain",
        "description": "Awarded to founding agents who completed RTC-native onboarding.",
        "variant": "agent",
        "sort_order": 40,
    },
    "founding_scout_human": {
        "label": "Founding Scout",
        "context_label": "Human Funnel",
        "description": "Awarded to referrers who activated the first wave of human creators.",
        "variant": "scout",
        "sort_order": 50,
    },
    "founding_scout_agent": {
        "label": "Founding Scout",
        "context_label": "Agent Funnel",
        "description": "Awarded to sponsors who activated the first wave of agent creators.",
        "variant": "scout",
        "sort_order": 60,
    },
    "founding_human_pair": {
        "label": "Founding Pair",
        "context_label": "Human Cohort",
        "description": "Reserved for founding human referral pairs.",
        "variant": "pair",
        "sort_order": 70,
    },
    "founding_agent_pair": {
        "label": "Founding Pair",
        "context_label": "Agent Cohort",
        "description": "Reserved for founding agent referral pairs.",
        "variant": "pair",
        "sort_order": 80,
    },
}

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


def _tokenize_text(text: str) -> set:
    tokens = _re_mod.findall(r"[a-z0-9]{3,}", (text or "").lower())
    return set(tokens)


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _safe_json_loads_list(raw) -> list:
    """Best-effort JSON list parsing for DB fields (prevents 500s on bad data)."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        v = json.loads(raw)
    except Exception:
        return []
    return v if isinstance(v, list) else []


def _safe_json_loads_dict(raw) -> dict:
    """Best-effort JSON dict parsing for DB fields (prevents 500s on bad data)."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw)
    except Exception:
        return {}
    return v if isinstance(v, dict) else {}


def compute_novelty_score(db, agent_id: int, title: str, description: str,
                          tags: list, scene_description: str = "") -> tuple[float, str]:
    """Compute novelty score (0-100) based on similarity to recent uploads."""
    text = f"{title} {description} {scene_description}"
    tokens = _tokenize_text(text)
    tag_set = {t.lower() for t in tags}

    since = time.time() - (NOVELTY_LOOKBACK_DAYS * 86400)
    rows = db.execute(
        """SELECT title, description, tags, scene_description
           FROM videos
           WHERE agent_id = ? AND created_at > ?
           ORDER BY created_at DESC
           LIMIT ?""",
        (agent_id, since, NOVELTY_HISTORY_LIMIT),
    ).fetchall()

    if not rows:
        return 100.0, ""

    max_sim = 0.0
    for row in rows:
        prev_text = f"{row['title']} {row['description']} {row['scene_description']}"
        prev_tokens = _tokenize_text(prev_text)
        prev_tags = set(_safe_json_loads_list(row["tags"]))
        sim = (0.7 * _jaccard(tokens, prev_tokens)) + (0.3 * _jaccard(tag_set, prev_tags))
        if sim > max_sim:
            max_sim = sim

    novelty = max(0.0, round((1.0 - max_sim) * 100.0, 1))
    flags = []
    if max_sim >= 0.7:
        flags.append("high_similarity")
    if not tokens and not tag_set:
        flags.append("low_info")
    return novelty, ",".join(flags)


# ---------------------------------------------------------------------------
# In-memory rate limiter (no external dependency)
# ---------------------------------------------------------------------------

_rate_buckets: dict = {}  # key -> list of timestamps
_rate_last_prune = 0.0

# Global rate limiting (human-friendly defaults).
# These limits exist to blunt scraping/abuse, but should not interfere with normal browsing.
#
# Key idea:
# - Do NOT count static/media asset requests (thumbnails/avatars/static) toward the global budget.
# - Prefer per-visitor cookie budgets so mobile/carrier NAT doesn't punish real users.
# - Keep a separate, stricter budget for requests that don't accept cookies (often scripts/scrapers).
_RL_WINDOW_SECS = int(os.environ.get("BOTTUBE_RL_WINDOW_SECS", "60"))
_RL_GLOBAL_RPM = int(os.environ.get("BOTTUBE_GLOBAL_RPM", "1200"))          # per visitor cookie (requests/min)
_RL_GLOBAL_IP_RPM = int(os.environ.get("BOTTUBE_GLOBAL_IP_RPM", "5000"))    # per IP hard-cap (requests/min)
# Mobile carrier NAT + privacy browsers can look like "no-cookie". Keep this generous.
_RL_NOCOOKIE_RPM = int(os.environ.get("BOTTUBE_NOCOOKIE_RPM", "2000"))      # per IP when no visitor cookie (requests/min)
_RL_SCRAPER_RPM = int(os.environ.get("BOTTUBE_SCRAPER_RPM", "60"))          # per IP for known scraper UAs (requests/min)

_RL_EXEMPT_PREFIXES = (
    "/static/",
    "/thumbnails/",
    "/avatars/",
    "/avatar/",
    "/badge/",
    "/stats/",
)
_RL_EXEMPT_PATHS = {
    "/favicon.ico",
    "/robots.txt",
    "/sitemap.xml",
    # Client-side telemetry/counters: not worth rate-limiting, and they distort visitor logs.
    "/api/bt-proof",
    "/api/footer-counters",
}


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


def _normalize_ref_code(raw: str) -> str:
    """Normalize and validate referral codes. Returns '' if invalid."""
    code = (raw or "").strip()
    if not code:
        return ""
    code = code.lower()
    if not re.fullmatch(r"[a-z0-9_-]{2,32}", code):
        return ""
    return code


def _normalize_referral_track(raw: str, default: str = "both") -> str:
    track = (raw or "").strip().lower()
    if track in REFERRAL_TRACKS:
        return track
    return default


def _referral_track_for_agent(row: sqlite3.Row | dict | None) -> str:
    if not row:
        return "agent"
    return "human" if int(row["is_human"] or 0) else "agent"


def _referral_track_allowed(allowed_track: str, invitee_track: str) -> bool:
    allowed = _normalize_referral_track(allowed_track, "both")
    if allowed == "both":
        return True
    return allowed == invitee_track


def _referral_request_hashes() -> tuple[str, str]:
    try:
        ip = _get_client_ip()
        fp = _fingerprint_ua(
            ip,
            ua=request.headers.get("User-Agent", ""),
            accept_language=request.headers.get("Accept-Language", ""),
        )
    except Exception:
        ip = ""
        fp = ""
    ip_hash = hashlib.sha256(ip.encode("utf-8")).hexdigest() if ip else ""
    fp_hash = hashlib.sha256(fp.encode("utf-8")).hexdigest() if fp else ""
    return ip_hash, fp_hash


def _referral_get_code_row(db: sqlite3.Connection, code: str):
    ref_code = _normalize_ref_code(code)
    if not ref_code:
        return None
    return db.execute(
        "SELECT code, agent_id, COALESCE(allowed_track, 'both') AS allowed_track FROM referral_codes WHERE code = ?",
        (ref_code,),
    ).fetchone()


def _referral_build_summary(db: sqlite3.Connection, agent_id: int, *, include_recent: bool = True) -> dict | None:
    row = db.execute(
        """
        SELECT code, hits, signups, first_uploads, created_at, COALESCE(allowed_track, 'both') AS allowed_track
        FROM referral_codes
        WHERE agent_id = ?
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (agent_id,),
    ).fetchone()
    if not row:
        return None

    invite_rows = db.execute(
        """
        SELECT
            ri.id,
            ri.invitee_track,
            ri.source,
            ri.signup_at,
            ri.profile_completed_at,
            ri.profile_completed_ref,
            ri.first_public_video_at,
            ri.first_public_video_ref,
            ri.first_rtc_native_action_at,
            ri.first_rtc_native_action_ref,
            ri.fully_activated_at,
            ri.review_status,
            ri.reviewed_at,
            ri.reviewer_note,
            a.agent_name,
            a.display_name,
            a.created_at AS invitee_created_at
        FROM referral_invites ri
        JOIN agents a ON a.id = ri.invitee_agent_id
        WHERE ri.referrer_agent_id = ?
        ORDER BY ri.signup_at DESC, ri.id DESC
        """,
        (agent_id,),
    ).fetchall()

    tracks = {
        "human": {"invited": 0, "profile_completed": 0, "first_public_video": 0, "first_rtc_native_action": 0, "fully_activated": 0},
        "agent": {"invited": 0, "profile_completed": 0, "first_public_video": 0, "first_rtc_native_action": 0, "fully_activated": 0},
    }
    milestones = {
        "profile_completed": 0,
        "first_public_video": 0,
        "first_rtc_native_action": 0,
        "fully_activated": 0,
    }
    pending_review_count = 0
    approved_pairs = 0
    countable_pairs = 0
    recent_invites = []

    for invite in invite_rows:
        track = invite["invitee_track"] if invite["invitee_track"] in ("human", "agent") else "agent"
        tracks[track]["invited"] += 1

        profile_done = float(invite["profile_completed_at"] or 0) > 0
        video_done = float(invite["first_public_video_at"] or 0) > 0
        rtc_done = float(invite["first_rtc_native_action_at"] or 0) > 0
        fully_done = float(invite["fully_activated_at"] or 0) > 0

        if profile_done:
            tracks[track]["profile_completed"] += 1
            milestones["profile_completed"] += 1
        if video_done:
            tracks[track]["first_public_video"] += 1
            milestones["first_public_video"] += 1
        if rtc_done:
            tracks[track]["first_rtc_native_action"] += 1
            milestones["first_rtc_native_action"] += 1
        if fully_done:
            tracks[track]["fully_activated"] += 1
            milestones["fully_activated"] += 1

        review_status = (invite["review_status"] or "pending").strip().lower() or "pending"
        if review_status == "pending":
            pending_review_count += 1
        if fully_done and review_status not in {"rejected", "void"}:
            countable_pairs += 1
        if fully_done and review_status == "approved":
            approved_pairs += 1

        if include_recent:
            recent_invites.append(
                {
                    "id": int(invite["id"]),
                    "agent_name": invite["agent_name"],
                    "display_name": invite["display_name"] or invite["agent_name"],
                    "track": track,
                    "source": invite["source"] or "",
                    "signup_at": float(invite["signup_at"] or 0),
                    "invitee_created_at": float(invite["invitee_created_at"] or 0),
                    "review_status": review_status,
                    "reviewed_at": float(invite["reviewed_at"] or 0),
                    "reviewer_note": invite["reviewer_note"] or "",
                    "milestones": {
                        "profile_completed": profile_done,
                        "first_public_video": video_done,
                        "first_rtc_native_action": rtc_done,
                        "fully_activated": fully_done,
                    },
                }
            )

    bonus_progress = [
        {
            "threshold": threshold,
            "current": countable_pairs,
            "approved": approved_pairs,
            "remaining": max(threshold - countable_pairs, 0),
            "reached": countable_pairs >= threshold,
        }
        for threshold in REFERRAL_BONUS_THRESHOLDS
    ]

    return {
        "code": row["code"],
        "allowed_track": _normalize_referral_track(row["allowed_track"], "both"),
        "created_at": float(row["created_at"] or 0),
        "hits": int(row["hits"] or 0),
        "signups": int(row["signups"] or 0),
        "first_uploads": int(row["first_uploads"] or 0),
        "ref_url": f"https://bottube.ai/r/{row['code']}",
        "signup_url": f"https://bottube.ai/signup?ref={row['code']}",
        "tracks": tracks,
        "milestones": milestones,
        "pending_review_count": pending_review_count,
        "fully_activated_pairs": countable_pairs,
        "approved_pairs": approved_pairs,
        "bonus_progress": bonus_progress,
        "recent_invites": recent_invites,
    }


def _referral_refresh_invite_state(db: sqlite3.Connection, invitee_agent_id: int) -> None:
    invite = db.execute(
        """
        SELECT
            ri.id,
            ri.profile_completed_at,
            ri.first_public_video_at,
            ri.first_rtc_native_action_at,
            ri.fully_activated_at,
            a.agent_name
        FROM referral_invites ri
        JOIN agents a ON a.id = ri.invitee_agent_id
        WHERE ri.invitee_agent_id = ?
        """,
        (invitee_agent_id,),
    ).fetchone()
    if not invite:
        return

    now = time.time()
    updates: dict[str, object] = {}
    profile_completed_at = float(invite["profile_completed_at"] or 0)
    first_public_video_at = float(invite["first_public_video_at"] or 0)
    first_rtc_native_action_at = float(invite["first_rtc_native_action_at"] or 0)
    fully_activated_at = float(invite["fully_activated_at"] or 0)

    if profile_completed_at <= 0 and _quest_progress_count(db, invitee_agent_id, "profile_complete") > 0:
        updates["profile_completed_at"] = now
        updates["profile_completed_ref"] = f"/agent/{invite['agent_name']}"
        profile_completed_at = now

    if first_public_video_at <= 0:
        first_video = db.execute(
            """
            SELECT video_id, created_at
            FROM videos
            WHERE agent_id = ? AND COALESCE(is_removed, 0) = 0
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (invitee_agent_id,),
        ).fetchone()
        if first_video:
            first_public_video_at = float(first_video["created_at"] or now)
            updates["first_public_video_at"] = first_public_video_at
            updates["first_public_video_ref"] = f"/watch/{first_video['video_id']}"

    if first_rtc_native_action_at <= 0:
        first_tip = db.execute(
            """
            SELECT id, video_id, created_at
            FROM tips
            WHERE from_agent_id = ? OR to_agent_id = ?
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (invitee_agent_id, invitee_agent_id),
        ).fetchone()
        if first_tip:
            first_rtc_native_action_at = float(first_tip["created_at"] or now)
            updates["first_rtc_native_action_at"] = first_rtc_native_action_at
            if first_tip["video_id"]:
                updates["first_rtc_native_action_ref"] = f"/watch/{first_tip['video_id']}"
            else:
                updates["first_rtc_native_action_ref"] = "/tips/dashboard"

    if fully_activated_at <= 0 and profile_completed_at > 0 and first_public_video_at > 0 and first_rtc_native_action_at > 0:
        updates["fully_activated_at"] = max(profile_completed_at, first_public_video_at, first_rtc_native_action_at, now)

    if not updates:
        return

    updates["updated_at"] = now
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    db.execute(
        f"UPDATE referral_invites SET {set_clause} WHERE invitee_agent_id = ?",
        list(updates.values()) + [invitee_agent_id],
    )


def _referral_mark_rtc_native_action(
    db: sqlite3.Connection,
    agent_id: int,
    *,
    evidence_ref: str,
    occurred_at: float | None = None,
) -> None:
    invite = db.execute(
        "SELECT first_rtc_native_action_at FROM referral_invites WHERE invitee_agent_id = ?",
        (agent_id,),
    ).fetchone()
    if not invite or float(invite["first_rtc_native_action_at"] or 0) > 0:
        return
    now = float(occurred_at or time.time())
    db.execute(
        """
        UPDATE referral_invites
        SET first_rtc_native_action_at = ?,
            first_rtc_native_action_ref = ?,
            updated_at = ?
        WHERE invitee_agent_id = ?
        """,
        (now, evidence_ref[:500], time.time(), agent_id),
    )
    _referral_refresh_invite_state(db, agent_id)


def _referral_touch_hit(db, code: str):
    """Increment referral hit counters (best-effort)."""
    if not code:
        return
    try:
        now = time.time()
        db.execute(
            "UPDATE referral_codes SET hits = hits + 1, last_hit_at = ? WHERE code = ?",
            (now, code),
        )
        db.commit()
    except Exception:
        # Do not break request flow on referral tracking failures.
        pass


def _referral_touch_hit_unique(db, code: str):
    """Increment referral hit counters once per (code,fingerprint) per 24h (best-effort)."""
    if not code:
        return
    try:
        ip = _get_client_ip()
        fp = _fingerprint_ua(
            ip,
            ua=request.headers.get("User-Agent", ""),
            accept_language=request.headers.get("Accept-Language", ""),
        )
        # Store only a hash; never store raw fingerprint strings.
        fp_hash = hashlib.sha256(fp.encode("utf-8")).hexdigest()
        now = time.time()
        cutoff = now - 86400
        row = db.execute(
            "SELECT last_hit_at FROM referral_hit_uniques WHERE code = ? AND fp_hash = ?",
            (code, fp_hash),
        ).fetchone()
        if row and float(row["last_hit_at"] or 0) > cutoff:
            return
        if row:
            db.execute(
                "UPDATE referral_hit_uniques SET last_hit_at = ? WHERE code = ? AND fp_hash = ?",
                (now, code, fp_hash),
            )
        else:
            db.execute(
                "INSERT OR IGNORE INTO referral_hit_uniques (code, fp_hash, last_hit_at) VALUES (?, ?, ?)",
                (code, fp_hash, now),
            )
        # Count unique-ish hits.
        db.execute(
            "UPDATE referral_codes SET hits = hits + 1, last_hit_at = ? WHERE code = ?",
            (now, code),
        )
        db.commit()
    except Exception:
        pass


def _referral_apply_signup(db, new_agent_id: int, code: str, *, source: str = "signup") -> dict:
    """Attach referral to an invitee and create milestone tracking state."""
    result = {"ok": False, "applied": False, "error": "missing_referral_code"}
    ref_code = _normalize_ref_code(code)
    if not ref_code:
        return result
    try:
        ref = _referral_get_code_row(db, ref_code)
        if not ref:
            return {"ok": False, "applied": False, "error": "referral_code_not_found"}
        invitee = db.execute(
            """
            SELECT id, agent_name, is_human, created_at, referred_by_code
            FROM agents
            WHERE id = ?
            """,
            (new_agent_id,),
        ).fetchone()
        if not invitee:
            return {"ok": False, "applied": False, "error": "invitee_not_found"}
        if int(ref["agent_id"]) == int(new_agent_id):
            return {"ok": False, "applied": False, "error": "self_referral"}

        invitee_track = _referral_track_for_agent(invitee)
        if not _referral_track_allowed(ref["allowed_track"], invitee_track):
            return {
                "ok": False,
                "applied": False,
                "error": "referral_track_not_allowed",
                "invitee_track": invitee_track,
                "allowed_track": _normalize_referral_track(ref["allowed_track"], "both"),
            }

        now = time.time()
        cur = db.execute(
            "UPDATE agents SET referred_by_code = ?, referred_at = ? WHERE id = ? AND COALESCE(referred_by_code, '') = ''",
            (ref_code, now, new_agent_id),
        )
        if int(getattr(cur, "rowcount", 0) or 0) <= 0:
            existing = db.execute(
                "SELECT referred_by_code FROM agents WHERE id = ?",
                (new_agent_id,),
            ).fetchone()
            return {
                "ok": False,
                "applied": False,
                "error": "already_referred",
                "code": _normalize_ref_code((existing["referred_by_code"] if existing else "") or ""),
            }

        ip_hash, fp_hash = _referral_request_hashes()
        db.execute(
            "UPDATE referral_codes SET signups = signups + 1, last_signup_at = ? WHERE code = ?",
            (now, ref_code),
        )
        db.execute(
            """
            INSERT OR IGNORE INTO referral_invites (
                referral_code,
                referrer_agent_id,
                invitee_agent_id,
                invitee_track,
                source,
                signup_at,
                invitee_created_at,
                signup_ip_hash,
                signup_fp_hash,
                review_status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                ref_code,
                int(ref["agent_id"]),
                new_agent_id,
                invitee_track,
                (source or "signup")[:64],
                now,
                float(invitee["created_at"] or 0),
                ip_hash,
                fp_hash,
                now,
                now,
            ),
        )
        _referral_refresh_invite_state(db, new_agent_id)
        db.commit()
        return {
            "ok": True,
            "applied": True,
            "code": ref_code,
            "invitee_track": invitee_track,
            "allowed_track": _normalize_referral_track(ref["allowed_track"], "both"),
        }
    except Exception as exc:
        return {"ok": False, "applied": False, "error": "referral_apply_failed", "details": str(exc)}


def _referral_mark_first_upload(db, agent_id: int):
    """If agent was referred, count their first upload exactly once (best-effort)."""
    try:
        row = db.execute(
            "SELECT referred_by_code, referral_first_upload_counted FROM agents WHERE id = ?",
            (agent_id,),
        ).fetchone()
        if not row:
            return
        code = _normalize_ref_code(row["referred_by_code"] or "")
        if not code:
            return
        if int(row["referral_first_upload_counted"] or 0) != 0:
            return
        now = time.time()
        db.execute(
            "UPDATE agents SET referral_first_upload_counted = 1 WHERE id = ?",
            (agent_id,),
        )
        db.execute(
            "UPDATE referral_codes SET first_uploads = first_uploads + 1, last_first_upload_at = ? WHERE code = ?",
            (now, code),
        )
        _referral_refresh_invite_state(db, agent_id)
        db.commit()
    except Exception:
        pass
def _badge_catalog_entry(badge_key: str) -> dict:
    meta = dict(BADGE_CATALOG.get(badge_key, {}))
    label = meta.get("label") or badge_key.replace("_", " ").title()
    context_label = meta.get("context_label") or "Founding"
    variant = meta.get("variant") or "scout"
    if variant not in BADGE_VARIANTS:
        variant = "scout"
    return {
        "badge_key": badge_key,
        "label": label,
        "context_label": context_label,
        "description": meta.get("description") or label,
        "variant": variant,
        "sort_order": int(meta.get("sort_order", 999)),
    }


def _default_badge_source_campaign(badge_key: str) -> str:
    if "_human_" in badge_key or badge_key.endswith("_human"):
        return "rustchain-bounties#1584"
    if "_agent_" in badge_key or badge_key.endswith("_agent"):
        return "rustchain-bounties#1585"
    return ""


def _badge_assignment_payload(row) -> dict:
    meta = _badge_catalog_entry((row["badge_key"] or "").strip())
    payload = {
        "id": int(row["id"]),
        "badge_key": meta["badge_key"],
        "label": meta["label"],
        "context_label": meta["context_label"],
        "display_name": f"{meta['label']} - {meta['context_label']}",
        "description": meta["description"],
        "variant": meta["variant"],
        "sort_order": meta["sort_order"],
        "cohort_number": int(row["cohort_number"] or 0),
        "source_campaign": row["source_campaign"] or "",
        "notes": row["notes"] or "",
        "metadata": _safe_json_loads_dict(row["metadata_json"]),
        "awarded_at": float(row["awarded_at"] or 0),
        "awarded_by": row["awarded_by"] or "",
        "is_active": bool(int(row["is_active"] or 0)),
        "removed_at": float(row["removed_at"] or 0),
        "removed_by": row["removed_by"] or "",
    }
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    if {"agent_id", "agent_name", "display_name"} <= keys:
        payload["agent"] = {
            "id": int(row["agent_id"]),
            "agent_name": row["agent_name"],
            "display_name": row["display_name"] or row["agent_name"],
            "is_human": bool(int(row["is_human"] or 0)) if "is_human" in keys else False,
        }
    return payload


def _badge_payload_sort_key(badge: dict) -> tuple:
    cohort = int(badge.get("cohort_number") or 0)
    cohort_sort = cohort if cohort > 0 else 9999
    return (
        int(badge.get("sort_order", 999)),
        cohort_sort,
        float(badge.get("awarded_at") or 0),
        int(badge.get("id") or 0),
    )


def _list_agent_badges(
    db: sqlite3.Connection,
    agent_id: int,
    *,
    include_inactive: bool = False,
) -> list[dict]:
    where = "" if include_inactive else "AND COALESCE(is_active, 1) = 1"
    rows = db.execute(
        f"""
        SELECT *
        FROM agent_badges
        WHERE agent_id = ? {where}
        ORDER BY awarded_at ASC, id ASC
        """,
        (agent_id,),
    ).fetchall()
    badges = [_badge_assignment_payload(row) for row in rows]
    badges.sort(key=_badge_payload_sort_key)
    return badges


def _badge_assignment_keyset(db: sqlite3.Connection, *, active_only: bool = True) -> set[tuple[int, str]]:
    where = "WHERE COALESCE(is_active, 1) = 1" if active_only else ""
    rows = db.execute(f"SELECT agent_id, badge_key FROM agent_badges {where}").fetchall()
    return {(int(row["agent_id"]), row["badge_key"]) for row in rows}


def _build_badge_candidates(db: sqlite3.Connection) -> list[dict]:
    assigned = _badge_assignment_keyset(db, active_only=True)
    candidates: list[dict] = []

    invite_rows = db.execute(
        """
        SELECT
            ri.id,
            ri.referral_code,
            ri.invitee_track,
            ri.fully_activated_at,
            inv.id AS invitee_agent_id,
            inv.agent_name AS invitee_agent_name,
            inv.display_name AS invitee_display_name,
            inv.is_human AS invitee_is_human,
            ref.agent_name AS referrer_agent_name,
            ref.display_name AS referrer_display_name
        FROM referral_invites ri
        JOIN agents inv ON inv.id = ri.invitee_agent_id
        JOIN agents ref ON ref.id = ri.referrer_agent_id
        WHERE COALESCE(ri.fully_activated_at, 0) > 0
          AND COALESCE(ri.review_status, 'pending') NOT IN ('rejected', 'void')
        ORDER BY ri.invitee_track ASC, ri.fully_activated_at ASC, ri.id ASC
        """
    ).fetchall()

    cohort_counts = {"human": 0, "agent": 0}
    for row in invite_rows:
        track = row["invitee_track"] if row["invitee_track"] in {"human", "agent"} else "agent"
        cohort_counts[track] += 1
        cohort_number = cohort_counts[track]
        if cohort_number > FOUNDING_BADGE_LIMIT:
            continue
        badge_keys = (
            ("early_human_bottube", "early_human_rustchain")
            if track == "human"
            else ("early_agent_bottube", "early_agent_rustchain")
        )
        source_campaign = _default_badge_source_campaign(badge_keys[0])
        for badge_key in badge_keys:
            if (int(row["invitee_agent_id"]), badge_key) in assigned:
                continue
            meta = _badge_catalog_entry(badge_key)
            candidates.append(
                {
                    "badge_key": badge_key,
                    "badge": {**meta, "cohort_number": cohort_number, "source_campaign": source_campaign},
                    "agent": {
                        "id": int(row["invitee_agent_id"]),
                        "agent_name": row["invitee_agent_name"],
                        "display_name": row["invitee_display_name"] or row["invitee_agent_name"],
                        "is_human": bool(int(row["invitee_is_human"] or 0)),
                    },
                    "cohort_number": cohort_number,
                    "source_campaign": source_campaign,
                    "reason": f"Founding {track} cohort #{cohort_number} fully activated via referral.",
                    "evidence": {
                        "invite_id": int(row["id"]),
                        "referral_code": row["referral_code"],
                        "fully_activated_at": float(row["fully_activated_at"] or 0),
                        "referrer_agent_name": row["referrer_agent_name"],
                        "referrer_display_name": row["referrer_display_name"] or row["referrer_agent_name"],
                    },
                }
            )

    scout_rows = db.execute(
        """
        SELECT
            ri.referrer_agent_id AS agent_id,
            ri.invitee_track,
            COUNT(*) AS pair_count,
            MIN(ri.fully_activated_at) AS first_fully_activated_at,
            MAX(ri.fully_activated_at) AS last_fully_activated_at,
            a.agent_name,
            a.display_name,
            a.is_human
        FROM referral_invites ri
        JOIN agents a ON a.id = ri.referrer_agent_id
        WHERE COALESCE(ri.fully_activated_at, 0) > 0
          AND COALESCE(ri.review_status, 'pending') NOT IN ('rejected', 'void')
        GROUP BY ri.referrer_agent_id, ri.invitee_track
        HAVING COUNT(*) >= ?
        ORDER BY COUNT(*) DESC, MIN(ri.fully_activated_at) ASC, ri.referrer_agent_id ASC
        """,
        (FOUNDING_SCOUT_MIN_PAIRS,),
    ).fetchall()

    for row in scout_rows:
        track = row["invitee_track"] if row["invitee_track"] in {"human", "agent"} else "agent"
        badge_key = "founding_scout_human" if track == "human" else "founding_scout_agent"
        agent_id = int(row["agent_id"])
        if (agent_id, badge_key) in assigned:
            continue
        pair_count = int(row["pair_count"] or 0)
        source_campaign = _default_badge_source_campaign(badge_key)
        meta = _badge_catalog_entry(badge_key)
        candidates.append(
            {
                "badge_key": badge_key,
                "badge": {**meta, "source_campaign": source_campaign},
                "agent": {
                    "id": agent_id,
                    "agent_name": row["agent_name"],
                    "display_name": row["display_name"] or row["agent_name"],
                    "is_human": bool(int(row["is_human"] or 0)),
                },
                "cohort_number": 0,
                "source_campaign": source_campaign,
                "reason": f"Reached {pair_count} fully activated {track} referral pairs.",
                "evidence": {
                    "pair_count": pair_count,
                    "bonus_thresholds_reached": [t for t in REFERRAL_BONUS_THRESHOLDS if pair_count >= t],
                    "first_fully_activated_at": float(row["first_fully_activated_at"] or 0),
                    "last_fully_activated_at": float(row["last_fully_activated_at"] or 0),
                    "invitee_track": track,
                },
            }
        )

    candidates.sort(
        key=lambda row: (
            int(row["badge"]["sort_order"]),
            int(row.get("cohort_number") or 0) or 9999,
            row["agent"]["agent_name"],
            row["badge_key"],
        )
    )
    return candidates


def _nocookie_fingerprint(ip: str, ua: str, accept_language: str) -> str:
    """
    Identify visitors who block cookies more granularly than just IP.

    Mobile carrier NAT and some privacy browsers can cause many real users to share a public IP while
    refusing cookies. If we rate-limit strictly by IP in that scenario, legitimate viewers get 429s.
    """
    basis = (ua or "").strip().lower() + "|" + (accept_language or "").strip().lower()
    if basis == "|":
        return ip
    h = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]
    return f"{ip}:{h}"

# RTC reward amounts
RTC_REWARD_UPLOAD = 0.05       # Uploading a video
RTC_REWARD_VIEW = 0.0001       # Per view (paid to video creator)
RTC_REWARD_COMMENT = 0.001     # Posting a comment (paid to commenter)
RTC_REWARD_LIKE_RECEIVED = 0.001  # Receiving a like (paid to video creator)
COMMENT_REWARD_DAILY_CAP = float(os.environ.get("BOTTUBE_COMMENT_REWARD_DAILY_CAP", "0.02"))
COMMENT_REWARD_TARGET_DAILY_CAP = float(os.environ.get("BOTTUBE_COMMENT_REWARD_TARGET_DAILY_CAP", "0.005"))
COMMENT_REWARD_HOLD_THRESHOLD = int(os.environ.get("BOTTUBE_COMMENT_REWARD_HOLD_THRESHOLD", "40"))
VIEW_REWARD_DAILY_CAP = float(os.environ.get("BOTTUBE_VIEW_REWARD_DAILY_CAP", "0.01"))
VIEW_REWARD_TARGET_DAILY_CAP = float(os.environ.get("BOTTUBE_VIEW_REWARD_TARGET_DAILY_CAP", "0.003"))
VIEW_REWARD_HOLD_THRESHOLD = int(os.environ.get("BOTTUBE_VIEW_REWARD_HOLD_THRESHOLD", "36"))
LIKE_REWARD_DAILY_CAP = float(os.environ.get("BOTTUBE_LIKE_REWARD_DAILY_CAP", "0.04"))
LIKE_REWARD_TARGET_DAILY_CAP = float(os.environ.get("BOTTUBE_LIKE_REWARD_TARGET_DAILY_CAP", "0.008"))
LIKE_REWARD_HOLD_THRESHOLD = int(os.environ.get("BOTTUBE_LIKE_REWARD_HOLD_THRESHOLD", "32"))
RTC_TIP_MIN = 0.001              # Minimum tip amount
RTC_TIP_MAX = 100.0              # Maximum tip per transaction

# Gamification: Streak bonus multipliers (consecutive days of activity)
STREAK_BONUS_MULTIPLIERS = {
    1: 1.0,    # No bonus
    3: 1.05,   # 5% bonus at 3 days
    7: 1.10,   # 10% bonus at 1 week
    14: 1.15,  # 15% bonus at 2 weeks
    30: 1.25,  # 25% bonus at 1 month
    60: 1.40,  # 40% bonus at 2 months
    90: 1.50,  # 50% bonus at 3 months
    180: 1.75, # 75% bonus at 6 months
    365: 2.0,  # 100% bonus at 1 year
}

# Gamification: Level thresholds (total XP required for each level)
# XP is earned from quest completions (1 XP per 1 RTC earned from quests)
LEVEL_THRESHOLDS = [
    (1, 0),       # Level 1: 0 XP (starting)
    (2, 50),      # Level 2: 50 XP
    (3, 150),     # Level 3: 150 XP
    (4, 300),     # Level 4: 300 XP
    (5, 500),     # Level 5: 500 XP
    (6, 800),     # Level 6: 800 XP
    (7, 1200),    # Level 7: 1200 XP
    (8, 1700),    # Level 8: 1700 XP
    (9, 2300),    # Level 9: 2300 XP
    (10, 3000),   # Level 10: 3000 XP
    (11, 4000),   # Level 11: 4000 XP
    (12, 5200),   # Level 12: 5200 XP
    (13, 6600),   # Level 13: 6600 XP
    (14, 8200),   # Level 14: 8200 XP
    (15, 10000),  # Level 15: 10000 XP (max)
]

# Anti-farm: Suspicious pattern thresholds
ANTI_FARM_CONFIG = {
    "self_interaction_window_secs": 300,  # 5 min window for self-view detection
    "rapid_comment_threshold": 10,         # Comments per hour before flagging
    "rapid_like_threshold": 15,            # Likes per hour before flagging
    "duplicate_comment_similarity": 0.85,  # Similarity threshold for duplicate detection
    "new_account_reward_cap": 0.5,         # Max daily RTC for accounts < 1 day old
    "new_account_age_secs": 86400,         # 24 hours
}

RUSTCHAIN_BASE_URL = os.environ.get("RUSTCHAIN_BASE_URL", "https://50.28.86.131").rstrip("/")

# ---------------------------------------------------------------------------
# i18n / Translations
# ---------------------------------------------------------------------------

TRANSLATIONS_DIR = BASE_DIR / "translations"
SUPPORTED_LOCALES = ["en", "es", "fr", "ja", "pt"]
DEFAULT_LOCALE = "en"
_translations = {}


def _load_translations():
    """Load all translation JSON files into memory."""
    for locale in SUPPORTED_LOCALES:
        fpath = TRANSLATIONS_DIR / f"{locale}.json"
        if fpath.exists():
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                _translations[locale] = data.get("strings", {})
    # Ensure English fallback always exists
    if "en" not in _translations:
        _translations["en"] = {}


def _detect_locale():
    """Detect preferred locale from session, query param, or Accept-Language header."""
    # 1. Explicit query param (?lang=es)
    lang = request.args.get("lang", "").strip().lower()
    if lang in SUPPORTED_LOCALES:
        session["locale"] = lang
        return lang
    # 2. Session cookie (persists user choice)
    lang = session.get("locale", "").strip().lower()
    if lang in SUPPORTED_LOCALES:
        return lang
    # 3. Accept-Language header
    accept = request.headers.get("Accept-Language", "")
    for part in accept.split(","):
        code = part.split(";")[0].strip().lower()
        # Match exact (e.g. "es") or prefix (e.g. "es-mx" -> "es")
        if code in SUPPORTED_LOCALES:
            return code
        prefix = code.split("-")[0]
        if prefix in SUPPORTED_LOCALES:
            return prefix
    return DEFAULT_LOCALE


def _translate(key, **kwargs):
    """Look up a translation key for the current locale, with English fallback."""
    locale = getattr(g, "locale", DEFAULT_LOCALE)
    text = _translations.get(locale, {}).get(key)
    if text is None:
        text = _translations.get("en", {}).get(key, key)
    if kwargs:
        for k, v in kwargs.items():
            text = text.replace("{" + k + "}", str(v))
    return text


_load_translations()

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

# JSON-aware 403 handler for AJAX requests
@app.errorhandler(403)
def handle_403(e):
    """Return JSON for API/AJAX 403 errors, HTML for browser requests."""
    if hasattr(e, "response") and e.response is not None:
        return e.response
    ct = request.headers.get("Content-Type", "")
    if request.is_json or "application/json" in ct or request.headers.get("X-CSRF-Token"):
        return jsonify({"error": "Forbidden", "csrf_error": True}), 403
    return "Forbidden", 403


# Google integrations (configured via env vars on VPS)
app.config["GA4_MEASUREMENT_ID"] = os.environ.get("GA4_MEASUREMENT_ID", "")
app.config["ADSENSE_PUBLISHER_ID"] = os.environ.get("ADSENSE_PUBLISHER_ID", "")
app.config["ADSENSE_VIDEO_SLOT"] = os.environ.get("ADSENSE_VIDEO_SLOT", "")
app.config["IMA_VAST_TAG"] = os.environ.get("IMA_VAST_TAG", "")
app.config["FCM_VAPID_KEY"] = os.environ.get("FCM_VAPID_KEY", "")
app.config["FIREBASE_PROJECT_ID"] = os.environ.get("FIREBASE_PROJECT_ID", "")

# URL prefix: when behind nginx at /bottube/ on shared IP, templates need prefixed URLs.
# When accessed via bottube.ai (own domain), prefix is empty.
# Dynamic per-request via before_request hook.
DOMAIN_PREFIX = ""  # bottube.ai serves at root
IP_PREFIX = os.environ.get("BOTTUBE_PREFIX", "/bottube").rstrip("/")
BOTTUBE_DOMAINS = {"bottube.ai", "www.bottube.ai"}
app.jinja_env.globals["P"] = IP_PREFIX  # default fallback
app.jinja_env.globals["MAX_DURATION"] = MAX_VIDEO_DURATION
app.jinja_env.globals["_"] = _translate
app.jinja_env.globals["SUPPORTED_LOCALES"] = SUPPORTED_LOCALES


def _build_recovery_notice(db=None):
    if not RECOVERY_RECLAIM_ENABLED:
        return None
    restored_views = RECOVERY_RESTORED_VIEWS_FALLBACK
    if db is not None:
        try:
            restored_views = int(
                db.execute(
                    """SELECT COALESCE(SUM(v.views), 0) FROM videos v
                       JOIN agents a ON v.agent_id = a.id
                       WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0"""
                ).fetchone()[0]
            )
        except sqlite3.Error:
            restored_views = RECOVERY_RESTORED_VIEWS_FALLBACK
    return {
        "enabled": True,
        "stage": RECOVERY_STAGE_LABEL,
        "restored_views": restored_views,
        "target_views": RECOVERY_TARGET_TOTAL_VIEWS,
        "remaining_views": max(RECOVERY_TARGET_TOTAL_VIEWS - restored_views, 0),
    }


@app.context_processor
def inject_recovery_notice():
    notice = None
    if RECOVERY_RECLAIM_ENABLED:
        try:
            notice = _build_recovery_notice(get_db())
        except Exception:
            notice = _build_recovery_notice(None)
    return {"recovery_notice": notice}


@app.before_request
def set_url_prefix():
    """Set URL prefix dynamically: empty for bottube.ai, /bottube for IP access."""
    host = request.host.split(":")[0].lower()
    canonical_host = os.getenv("BOTTUBE_CANONICAL_HOST", "bottube.ai").strip().lower()
    if os.getenv("BOTTUBE_WWW_REDIRECT", "1").strip().lower() not in {"0", "false", "no"}:
        if host == f"www.{canonical_host}":
            scheme = (
                "https"
                if (request.is_secure or request.headers.get("X-Forwarded-Proto") == "https")
                else request.scheme
            )
            url = f"{scheme}://{canonical_host}{request.full_path}"
            if url.endswith("?"):
                url = url[:-1]
            code = 301 if request.method in {"GET", "HEAD"} else 308
            return redirect(url, code=code)
    if host in BOTTUBE_DOMAINS:
        g.prefix = DOMAIN_PREFIX
    else:
        g.prefix = IP_PREFIX
    app.jinja_env.globals["P"] = g.prefix

    # i18n: detect locale for this request
    g.locale = _detect_locale()
    app.jinja_env.globals["locale"] = g.locale

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
            # Keep inline scripts for now (legacy templates), but allow GA/gtag when enabled.
            "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com https://stats.g.doubleclick.net; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "media-src 'self'; "
            "font-src 'self'; "
            "connect-src 'self' https://www.google-analytics.com https://region1.google-analytics.com https://stats.g.doubleclick.net https://www.googletagmanager.com; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
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
        # Return JSON for AJAX/API requests so JS can handle the error
        ct = request.headers.get("Content-Type", "")
        if request.is_json or "application/json" in ct or request.headers.get("X-CSRF-Token"):
            from flask import make_response

            resp = make_response(
                jsonify({"error": "Session expired. Please refresh the page.", "csrf_error": True}),
                403,
            )
            abort(resp)
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
    "HeadlessChrome": "Headless Chrome",
    "PhantomJS": "PhantomJS",
    "Playwright": "Playwright",
    "Puppeteer": "Puppeteer",
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
    # Don't rate-limit or log asset/media requests. These can be bursty (many thumbnails/avatars),
    # especially on mobile, and counting them leads to false-positive 429s.
    path = request.path or ""
    is_video_media = (
        request.method in {"GET", "HEAD"}
        and path.startswith("/api/videos/")
        and (path.endswith("/stream") or path.endswith("/captions"))
    )
    if (
        path in _RL_EXEMPT_PATHS
        or any(path.startswith(p) for p in _RL_EXEMPT_PREFIXES)
        or is_video_media
    ):
        return

    _log_visitor()

    # Scraper Detective — real-time bot classification
    ip = _get_client_ip()
    if SCRAPER_DETECTIVE_ENABLED and scraper_detective_inst.is_blocked(ip):
        return Response("Forbidden", status=403)
    if SCRAPER_DETECTIVE_ENABLED:
        scraper_detective_inst.record_request(
            ip, request.headers.get("User-Agent", ""), path,
            getattr(g, "visitor_id", ""), getattr(g, "is_new_visitor", False),
            request.headers.get("Referer", ""))

    # Rate limit scrapers more aggressively
    ua = request.headers.get("User-Agent", "")
    ua_lower = ua.lower()

    is_scraper = any(sig.lower() in ua_lower for sig in KNOWN_SCRAPERS)
    if is_scraper:
        if not _rate_limit(f"scraper:{ip}", _RL_SCRAPER_RPM, _RL_WINDOW_SECS):
            return Response("Rate limited", status=429)
    else:
        # General visitor rate limit: prefer per-visitor budgets (cookie) so carrier NAT doesn't
        # punish legitimate users; still keep a generous per-IP cap.
        if not _rate_limit(f"global_ip:{ip}", _RL_GLOBAL_IP_RPM, _RL_WINDOW_SECS):
            return Response("Rate limited", status=429)

        is_new = getattr(g, "is_new_visitor", False)
        visitor_id = getattr(g, "visitor_id", "")
        if is_new or not visitor_id:
            # No cookie yet (often scripts/scrapers). Keep a stricter per-IP cap.
            fp = _nocookie_fingerprint(ip, ua, request.headers.get("Accept-Language", ""))
            if not _rate_limit(f"global_nocookie:{fp}", _RL_NOCOOKIE_RPM, _RL_WINDOW_SECS):
                return Response("Rate limited", status=429)
        else:
            if not _rate_limit(f"global_vid:{visitor_id}", _RL_GLOBAL_RPM, _RL_WINDOW_SECS):
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


# ---------------------------------------------------------------------------
# Custom Error Handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(e):
    """Custom 404 page."""
    return render_template("404.html"), 404


@app.errorhandler(405)
def method_not_allowed(e):
    """405 with required Allow header per RFC 9110 Section 15.5.6."""
    allowed = e.valid_methods if hasattr(e, 'valid_methods') and e.valid_methods else []
    resp = jsonify({"error": "Method Not Allowed", "allowed": allowed})
    resp.status_code = 405
    if allowed:
        resp.headers["Allow"] = ", ".join(sorted(allowed))
    return resp


@app.errorhandler(500)
def internal_server_error(e):
    """Custom 500 page."""
    return render_template("500.html"), 500


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
    detected_type TEXT DEFAULT '',
    x_handle TEXT DEFAULT '',
    claim_token TEXT DEFAULT '',
    claimed INTEGER DEFAULT 0,
	    -- Wallet addresses for donations
	    rtc_address TEXT DEFAULT '',
	    -- RustChain on-chain wallet (RTC... Ed25519-derived address)
	    rtc_wallet TEXT DEFAULT '',
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
    novelty_score REAL DEFAULT 0,
    novelty_flags TEXT DEFAULT '',
    revision_of TEXT DEFAULT '',
    revision_note TEXT DEFAULT '',
    challenge_id TEXT DEFAULT '',
    submolt_crosspost TEXT DEFAULT '',
    attribution_id INTEGER DEFAULT NULL,
    syndication_chain TEXT DEFAULT '[]',
    license TEXT DEFAULT 'CC-BY-4.0',
    created_at REAL NOT NULL,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY,
    video_id TEXT NOT NULL,
    agent_id INTEGER NOT NULL,
    parent_id INTEGER DEFAULT NULL,
    content TEXT NOT NULL,
    comment_type TEXT DEFAULT 'comment',
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

CREATE TABLE IF NOT EXISTS reward_holds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_ref TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT DEFAULT 'pending',
    risk_score INTEGER DEFAULT 0,
    reasons TEXT DEFAULT '[]',
    created_at REAL NOT NULL,
    reviewed_at REAL DEFAULT 0,
    reviewer_note TEXT DEFAULT '',
    UNIQUE(agent_id, event_type, event_ref),
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS moderation_holds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    target_agent_id INTEGER,
    source TEXT DEFAULT '',
    reason TEXT NOT NULL,
    details TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    recommended_action TEXT DEFAULT 'coach',
    coach_note TEXT DEFAULT '',
    created_at REAL NOT NULL,
    reviewed_at REAL DEFAULT 0,
    reviewer_note TEXT DEFAULT '',
    UNIQUE(target_type, target_ref, source, reason),
    FOREIGN KEY (target_agent_id) REFERENCES agents(id)
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
CREATE INDEX IF NOT EXISTS idx_reward_holds_agent ON reward_holds(agent_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_moderation_holds_target ON moderation_holds(target_type, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_moderation_holds_agent ON moderation_holds(target_agent_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_subs_follower ON subscriptions(follower_id);
CREATE INDEX IF NOT EXISTS idx_subs_following ON subscriptions(following_id);
CREATE INDEX IF NOT EXISTS idx_notif_agent ON notifications(agent_id, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_videos_revision ON videos(revision_of);
CREATE INDEX IF NOT EXISTS idx_videos_challenge ON videos(challenge_id);

	-- RTC tips between users
	CREATE TABLE IF NOT EXISTS tips (
	    id INTEGER PRIMARY KEY,
	    from_agent_id INTEGER NOT NULL,
	    to_agent_id INTEGER NOT NULL,
	    video_id TEXT DEFAULT '',
	    amount REAL NOT NULL,
	    message TEXT DEFAULT '',
	    onchain INTEGER DEFAULT 0,
	    status TEXT DEFAULT 'confirmed',   -- confirmed | pending | voided
	    tx_hash TEXT,                     -- RustChain tx hash (pending ledger)
	    pending_id INTEGER,               -- RustChain pending_ledger id
	    confirms_at REAL,                 -- RustChain confirms_at (epoch seconds)
	    from_address TEXT DEFAULT '',     -- RustChain RTC... address
	    to_address TEXT DEFAULT '',       -- RustChain RTC... address
	    created_at REAL NOT NULL,
	    FOREIGN KEY (from_agent_id) REFERENCES agents(id),
	    FOREIGN KEY (to_agent_id) REFERENCES agents(id)
	);
	CREATE INDEX IF NOT EXISTS idx_tips_video ON tips(video_id, created_at DESC);
	CREATE INDEX IF NOT EXISTS idx_tips_to ON tips(to_agent_id, created_at DESC);
	CREATE INDEX IF NOT EXISTS idx_tips_status ON tips(status, confirms_at);
	CREATE UNIQUE INDEX IF NOT EXISTS idx_tips_tx_hash ON tips(tx_hash) WHERE tx_hash IS NOT NULL;

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

CREATE TABLE IF NOT EXISTS challenges (
    id INTEGER PRIMARY KEY,
    challenge_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    reward TEXT DEFAULT '',
    status TEXT DEFAULT 'upcoming', -- upcoming | active | closed
    start_at REAL DEFAULT 0,
    end_at REAL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_challenges_status ON challenges(status, start_at, end_at);

CREATE TABLE IF NOT EXISTS referral_codes (
    code TEXT PRIMARY KEY,
    agent_id INTEGER NOT NULL,
    created_at REAL NOT NULL,
    hits INTEGER DEFAULT 0,
    signups INTEGER DEFAULT 0,
    first_uploads INTEGER DEFAULT 0,
    last_hit_at REAL DEFAULT 0,
    last_signup_at REAL DEFAULT 0,
    last_first_upload_at REAL DEFAULT 0,
    allowed_track TEXT DEFAULT 'both',
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);
CREATE INDEX IF NOT EXISTS idx_referral_codes_agent ON referral_codes(agent_id);

CREATE TABLE IF NOT EXISTS referral_hit_uniques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    fp_hash TEXT NOT NULL,
    last_hit_at REAL NOT NULL,
    UNIQUE(code, fp_hash),
    FOREIGN KEY (code) REFERENCES referral_codes(code)
);
CREATE INDEX IF NOT EXISTS idx_referral_hit_code ON referral_hit_uniques(code);

CREATE TABLE IF NOT EXISTS referral_invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referral_code TEXT NOT NULL,
    referrer_agent_id INTEGER NOT NULL,
    invitee_agent_id INTEGER NOT NULL UNIQUE,
    invitee_track TEXT NOT NULL DEFAULT 'agent',
    source TEXT DEFAULT '',
    signup_at REAL NOT NULL,
    invitee_created_at REAL DEFAULT 0,
    signup_ip_hash TEXT DEFAULT '',
    signup_fp_hash TEXT DEFAULT '',
    profile_completed_at REAL DEFAULT 0,
    profile_completed_ref TEXT DEFAULT '',
    first_public_video_at REAL DEFAULT 0,
    first_public_video_ref TEXT DEFAULT '',
    first_rtc_native_action_at REAL DEFAULT 0,
    first_rtc_native_action_ref TEXT DEFAULT '',
    fully_activated_at REAL DEFAULT 0,
    review_status TEXT DEFAULT 'pending',
    reviewed_at REAL DEFAULT 0,
    reviewer_note TEXT DEFAULT '',
    suspicious_notes TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (referral_code) REFERENCES referral_codes(code),
    FOREIGN KEY (referrer_agent_id) REFERENCES agents(id),
    FOREIGN KEY (invitee_agent_id) REFERENCES agents(id)
);
CREATE INDEX IF NOT EXISTS idx_referral_invites_referrer ON referral_invites(referrer_agent_id, signup_at DESC);
CREATE INDEX IF NOT EXISTS idx_referral_invites_track ON referral_invites(invitee_track, review_status, signup_at DESC);
CREATE INDEX IF NOT EXISTS idx_referral_invites_code ON referral_invites(referral_code, signup_at DESC);

CREATE TABLE IF NOT EXISTS agent_badges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    badge_key TEXT NOT NULL,
    cohort_number INTEGER DEFAULT 0,
    source_campaign TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    awarded_at REAL NOT NULL,
    awarded_by TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    removed_at REAL DEFAULT 0,
    removed_by TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(agent_id, badge_key),
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_agent_badges_agent ON agent_badges(agent_id, is_active, awarded_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_badges_key ON agent_badges(badge_key, is_active, awarded_at DESC);
"""


def get_db():
    """Get thread-local database connection."""
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA busy_timeout=5000")
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

    # Migration: email notification preferences + unsubscribe token
    email_pref_migrations = {
        "email_notify_comments": "ALTER TABLE agents ADD COLUMN email_notify_comments INTEGER DEFAULT 1",
        "email_notify_replies": "ALTER TABLE agents ADD COLUMN email_notify_replies INTEGER DEFAULT 1",
        "email_notify_new_video": "ALTER TABLE agents ADD COLUMN email_notify_new_video INTEGER DEFAULT 1",
        "email_notify_tips": "ALTER TABLE agents ADD COLUMN email_notify_tips INTEGER DEFAULT 1",
        "email_notify_subscriptions": "ALTER TABLE agents ADD COLUMN email_notify_subscriptions INTEGER DEFAULT 1",
        "email_unsubscribe_token": "ALTER TABLE agents ADD COLUMN email_unsubscribe_token TEXT DEFAULT ''",
    }
    for col, sql in email_pref_migrations.items():
        if col not in existing_cols:
            conn.execute(sql)


    # Migration: webhook delivery counters/rate-limit metadata
    webhook_cols = {row[1] for row in conn.execute("PRAGMA table_info(webhooks)").fetchall()}
    webhook_migrations = {
        "event_window_start": "ALTER TABLE webhooks ADD COLUMN event_window_start REAL DEFAULT 0",
        "event_count": "ALTER TABLE webhooks ADD COLUMN event_count INTEGER DEFAULT 0",
    }
    for col, sql in webhook_migrations.items():
        if col not in webhook_cols:
            conn.execute(sql)

    # Miner install click tracking
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS miner_install_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            page TEXT NOT NULL,
            ip TEXT,
            created_at REAL NOT NULL
        )""")
        conn.commit()
    except Exception:
        pass

    # Generate unsubscribe tokens for agents that have email but no token yet
    conn.execute(
        "UPDATE agents SET email_unsubscribe_token = hex(randomblob(16)) "
        "WHERE email IS NOT NULL AND email != '' AND email_unsubscribe_token = ''"
    )

    # Migration: add is_banned + ban_reason to agents if missing
    agent_migrations = {
        "is_banned": "ALTER TABLE agents ADD COLUMN is_banned INTEGER DEFAULT 0",
        "ban_reason": "ALTER TABLE agents ADD COLUMN ban_reason TEXT DEFAULT ''",
        "banned_at": "ALTER TABLE agents ADD COLUMN banned_at REAL DEFAULT 0",
        "detected_type": "ALTER TABLE agents ADD COLUMN detected_type TEXT DEFAULT ''",
        # RustChain on-chain address (RTC... Ed25519-derived)
        "rtc_wallet": "ALTER TABLE agents ADD COLUMN rtc_wallet TEXT DEFAULT ''",
        # Referrals (best-effort growth tracking)
        "referred_by_code": "ALTER TABLE agents ADD COLUMN referred_by_code TEXT DEFAULT ''",
        "referred_at": "ALTER TABLE agents ADD COLUMN referred_at REAL DEFAULT 0",
        "referral_first_upload_counted": "ALTER TABLE agents ADD COLUMN referral_first_upload_counted INTEGER DEFAULT 0",
    }
    for col, sql in agent_migrations.items():
        if col not in existing_cols:
            conn.execute(sql)

    # Referral program table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS referral_codes (
            code TEXT PRIMARY KEY,
            agent_id INTEGER NOT NULL,
            created_at REAL NOT NULL,
            hits INTEGER DEFAULT 0,
            signups INTEGER DEFAULT 0,
            first_uploads INTEGER DEFAULT 0,
            last_hit_at REAL DEFAULT 0,
            last_signup_at REAL DEFAULT 0,
            last_first_upload_at REAL DEFAULT 0,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_referral_codes_agent ON referral_codes(agent_id)")
    referral_code_cols = {row[1] for row in conn.execute("PRAGMA table_info(referral_codes)").fetchall()}
    if "allowed_track" not in referral_code_cols:
        conn.execute("ALTER TABLE referral_codes ADD COLUMN allowed_track TEXT DEFAULT 'both'")

    # Referral unique hit tracking (privacy: store only hashed fingerprints)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS referral_hit_uniques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            fp_hash TEXT NOT NULL,
            last_hit_at REAL NOT NULL,
            UNIQUE(code, fp_hash),
            FOREIGN KEY (code) REFERENCES referral_codes(code)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_referral_hit_code ON referral_hit_uniques(code)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS referral_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referral_code TEXT NOT NULL,
            referrer_agent_id INTEGER NOT NULL,
            invitee_agent_id INTEGER NOT NULL UNIQUE,
            invitee_track TEXT NOT NULL DEFAULT 'agent',
            source TEXT DEFAULT '',
            signup_at REAL NOT NULL,
            invitee_created_at REAL DEFAULT 0,
            signup_ip_hash TEXT DEFAULT '',
            signup_fp_hash TEXT DEFAULT '',
            profile_completed_at REAL DEFAULT 0,
            profile_completed_ref TEXT DEFAULT '',
            first_public_video_at REAL DEFAULT 0,
            first_public_video_ref TEXT DEFAULT '',
            first_rtc_native_action_at REAL DEFAULT 0,
            first_rtc_native_action_ref TEXT DEFAULT '',
            fully_activated_at REAL DEFAULT 0,
            review_status TEXT DEFAULT 'pending',
            reviewed_at REAL DEFAULT 0,
            reviewer_note TEXT DEFAULT '',
            suspicious_notes TEXT DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (referral_code) REFERENCES referral_codes(code),
            FOREIGN KEY (referrer_agent_id) REFERENCES agents(id),
            FOREIGN KEY (invitee_agent_id) REFERENCES agents(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_referral_invites_referrer ON referral_invites(referrer_agent_id, signup_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_referral_invites_track ON referral_invites(invitee_track, review_status, signup_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_referral_invites_code ON referral_invites(referral_code, signup_at DESC)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            badge_key TEXT NOT NULL,
            cohort_number INTEGER DEFAULT 0,
            source_campaign TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            metadata_json TEXT DEFAULT '{}',
            awarded_at REAL NOT NULL,
            awarded_by TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            removed_at REAL DEFAULT 0,
            removed_by TEXT DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(agent_id, badge_key),
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_badges_agent ON agent_badges(agent_id, is_active, awarded_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_badges_key ON agent_badges(badge_key, is_active, awarded_at DESC)")
    badge_cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_badges)").fetchall()}
    badge_migrations = {
        "cohort_number": "ALTER TABLE agent_badges ADD COLUMN cohort_number INTEGER DEFAULT 0",
        "source_campaign": "ALTER TABLE agent_badges ADD COLUMN source_campaign TEXT DEFAULT ''",
        "notes": "ALTER TABLE agent_badges ADD COLUMN notes TEXT DEFAULT ''",
        "metadata_json": "ALTER TABLE agent_badges ADD COLUMN metadata_json TEXT DEFAULT '{}'",
        "awarded_by": "ALTER TABLE agent_badges ADD COLUMN awarded_by TEXT DEFAULT ''",
        "is_active": "ALTER TABLE agent_badges ADD COLUMN is_active INTEGER DEFAULT 1",
        "removed_at": "ALTER TABLE agent_badges ADD COLUMN removed_at REAL DEFAULT 0",
        "removed_by": "ALTER TABLE agent_badges ADD COLUMN removed_by TEXT DEFAULT ''",
        "updated_at": "ALTER TABLE agent_badges ADD COLUMN updated_at REAL DEFAULT 0",
    }
    for col, sql in badge_migrations.items():
        if col not in badge_cols:
            conn.execute(sql)

    now = time.time()
    conn.execute(
        """
        INSERT OR IGNORE INTO referral_invites (
            referral_code,
            referrer_agent_id,
            invitee_agent_id,
            invitee_track,
            source,
            signup_at,
            invitee_created_at,
            review_status,
            created_at,
            updated_at
        )
        SELECT
            a.referred_by_code,
            rc.agent_id,
            a.id,
            CASE WHEN COALESCE(a.is_human, 0) = 1 THEN 'human' ELSE 'agent' END,
            'legacy_backfill',
            CASE
                WHEN COALESCE(a.referred_at, 0) > 0 THEN a.referred_at
                WHEN COALESCE(a.created_at, 0) > 0 THEN a.created_at
                ELSE ?
            END,
            COALESCE(a.created_at, 0),
            'pending',
            ?,
            ?
        FROM agents a
        JOIN referral_codes rc ON rc.code = a.referred_by_code
        WHERE COALESCE(a.referred_by_code, '') != ''
        """,
        (now, now, now),
    )

    # Migration: Google OAuth columns on agents
    google_migrations = {
        "google_id": "ALTER TABLE agents ADD COLUMN google_id TEXT DEFAULT ''",
        "google_email": "ALTER TABLE agents ADD COLUMN google_email TEXT DEFAULT ''",
        "google_avatar": "ALTER TABLE agents ADD COLUMN google_avatar TEXT DEFAULT ''",
    }
    for col, sql in google_migrations.items():
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
    if "comment_type" not in comment_cols:
        conn.execute("ALTER TABLE comments ADD COLUMN comment_type TEXT DEFAULT 'comment'")

    # Migration: add novelty/revision/challenge fields to videos if missing
    video_cols = {row[1] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}
    if "novelty_score" not in video_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN novelty_score REAL DEFAULT 0")
    if "novelty_flags" not in video_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN novelty_flags TEXT DEFAULT ''")
    if "revision_of" not in video_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN revision_of TEXT DEFAULT ''")
    if "revision_note" not in video_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN revision_note TEXT DEFAULT ''")
    if "challenge_id" not in video_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN challenge_id TEXT DEFAULT ''")

    # Migration: push notification subscriptions table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # Migration: add vision screening fields to videos
    video_cols = {row[1] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}
    if "screening_status" not in video_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN screening_status TEXT DEFAULT 'legacy'")
    if "screening_details" not in video_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN screening_details TEXT DEFAULT ''")

    # Migration: create messages table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            from_agent TEXT NOT NULL,
            to_agent TEXT,
            subject TEXT DEFAULT '',
            body TEXT NOT NULL,
            read_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            message_type TEXT DEFAULT 'general'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_to ON messages(to_agent)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC)")

    # Migration: watch_history table (Phase 6)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watch_history (
            id INTEGER PRIMARY KEY,
            agent_id INTEGER,
            video_id TEXT NOT NULL,
            watched_at REAL NOT NULL,
            watch_duration_sec REAL DEFAULT 0,
            UNIQUE(agent_id, video_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watch_history_agent ON watch_history(agent_id, watched_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watch_history_video ON watch_history(video_id)")

    # Migration: reports table (Phase 7)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            video_id TEXT,
            comment_id INTEGER,
            reporter_agent_id INTEGER,
            reason TEXT NOT NULL,
            details TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at REAL NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_video ON reports(video_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status)")

    # Migration: RustChain on-chain tipping metadata
    try:
        tips_cols = {row[1] for row in conn.execute("PRAGMA table_info(tips)").fetchall()}
        tip_migrations = {
            "onchain": "ALTER TABLE tips ADD COLUMN onchain INTEGER DEFAULT 0",
            "status": "ALTER TABLE tips ADD COLUMN status TEXT DEFAULT 'confirmed'",
            "tx_hash": "ALTER TABLE tips ADD COLUMN tx_hash TEXT",
            "pending_id": "ALTER TABLE tips ADD COLUMN pending_id INTEGER",
            "confirms_at": "ALTER TABLE tips ADD COLUMN confirms_at REAL",
            "from_address": "ALTER TABLE tips ADD COLUMN from_address TEXT DEFAULT ''",
            "to_address": "ALTER TABLE tips ADD COLUMN to_address TEXT DEFAULT ''",
        }
        for col, sql in tip_migrations.items():
            if col not in tips_cols:
                conn.execute(sql)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_tips_status ON tips(status, confirms_at)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tips_tx_hash ON tips(tx_hash) WHERE tx_hash IS NOT NULL")
    except Exception:
        pass

    # Quest engine: lightweight onboarding progression with one-time RTC rewards.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quests (
            quest_key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'onboarding',
            reward_rtc REAL DEFAULT 0,
            goal_count INTEGER DEFAULT 1,
            metric_key TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_quests (
            agent_id INTEGER NOT NULL,
            quest_key TEXT NOT NULL,
            progress_count INTEGER DEFAULT 0,
            completed_at REAL DEFAULT 0,
            rewarded_at REAL DEFAULT 0,
            last_event_at REAL DEFAULT 0,
            metadata TEXT DEFAULT '{}',
            PRIMARY KEY (agent_id, quest_key),
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (quest_key) REFERENCES quests(quest_key)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_quests_agent ON agent_quests(agent_id, completed_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_quests_rewarded ON agent_quests(rewarded_at DESC)")

    # Syndication queue for distributing uploads to external platforms
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS syndication_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            video_title TEXT NOT NULL,
            agent_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL,
            target_platform TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 0,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            error_message TEXT DEFAULT '',
            metadata TEXT DEFAULT '{}',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            processed_at REAL DEFAULT NULL,
            completed_at REAL DEFAULT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_state ON syndication_queue(state, priority DESC, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_video ON syndication_queue(video_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_agent ON syndication_queue(agent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_platform ON syndication_queue(target_platform, state)")

    # Issue #311: Syndication attribution & tracking
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS syndication_attribution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL UNIQUE,
            agent_id INTEGER NOT NULL,
            original_creator TEXT NOT NULL,
            license TEXT DEFAULT 'CC-BY-4.0',
            source_url TEXT DEFAULT '',
            attribution_type TEXT DEFAULT 'original',
            chain TEXT DEFAULT '[]',
            custom_attribution TEXT DEFAULT '{}',
            created_at REAL NOT NULL,
            FOREIGN KEY (video_id) REFERENCES videos(video_id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_attr_video ON syndication_attribution(video_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_attr_creator ON syndication_attribution(original_creator)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS syndication_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            agent_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            external_url TEXT NOT NULL,
            external_id TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            error TEXT DEFAULT '',
            synced_at REAL,
            created_at REAL NOT NULL,
            FOREIGN KEY (video_id) REFERENCES videos(video_id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_log_video ON syndication_log(video_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_log_platform ON syndication_log(platform)")

    # Issue #311: Initialize syndication tables from media_prep module
    try:
        from media_prep import init_syndication_tables
        init_syndication_tables(conn)
    except ImportError:
        pass  # media_prep module not available

    conn.commit()
    _sync_default_quests(conn)
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


def _is_rustchain_rtc_address(addr: str) -> bool:
    """RustChain signed transfers require RTC + 40 hex chars (43 chars total)."""
    a = (addr or "").strip()
    return a.startswith("RTC") and len(a) == 43


def _rustchain_post_json(path: str, payload: dict, timeout: float = 10.0):
    """POST JSON to the RustChain node and return (status_code, parsed_json)."""
    url = f"{RUSTCHAIN_BASE_URL}{path}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.getcode(), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {"error": raw[:200] if raw else "rustchain_http_error"}
        return e.code, data
    except Exception as e:
        return 0, {"error": "rustchain_unreachable", "details": str(e)}


def _sync_pending_tips(db: sqlite3.Connection) -> None:
    """Best-effort: mark tips as confirmed once their RustChain confirms_at has passed."""
    try:
        now = time.time()
        db.execute(
            "UPDATE tips SET status = 'confirmed' "
            "WHERE COALESCE(status, 'confirmed') = 'pending' "
            "AND COALESCE(confirms_at, 0) > 0 AND confirms_at <= ?",
            (now,),
        )
    except Exception:
        pass


DEFAULT_QUESTS = [
    # Onboarding quests (one-time)
    {
        "quest_key": "profile_complete",
        "title": "Finish your profile",
        "description": "Add both a bio and avatar so other creators can recognize you.",
        "category": "onboarding",
        "reward_rtc": 3.0,
        "goal_count": 1,
        "metric_key": "profile_complete",
        "sort_order": 10,
    },
    {
        "quest_key": "first_upload",
        "title": "Publish your first video",
        "description": "Ship one public video to enter the creator feed.",
        "category": "creator",
        "reward_rtc": 8.0,
        "goal_count": 1,
        "metric_key": "first_upload",
        "sort_order": 20,
    },
    {
        "quest_key": "first_comment",
        "title": "Join the conversation",
        "description": "Leave one comment on a video without duplicating spam.",
        "category": "engagement",
        "reward_rtc": 2.0,
        "goal_count": 1,
        "metric_key": "first_comment",
        "sort_order": 30,
    },
    {
        "quest_key": "first_follow",
        "title": "Follow another creator",
        "description": "Subscribe to one creator to unlock your follow feed.",
        "category": "engagement",
        "reward_rtc": 2.0,
        "goal_count": 1,
        "metric_key": "first_follow",
        "sort_order": 40,
    },
    # Creator milestone quests (one-time)
    {
        "quest_key": "five_uploads",
        "title": "Consistent Creator",
        "description": "Publish 5 public videos to establish your presence.",
        "category": "creator",
        "reward_rtc": 15.0,
        "goal_count": 5,
        "metric_key": "total_uploads",
        "sort_order": 50,
    },
    {
        "quest_key": "ten_uploads",
        "title": "Prolific Producer",
        "description": "Publish 10 public videos and become a regular creator.",
        "category": "creator",
        "reward_rtc": 25.0,
        "goal_count": 10,
        "metric_key": "total_uploads",
        "sort_order": 60,
    },
    {
        "quest_key": "hundred_views",
        "title": "First Audience",
        "description": "Accumulate 100 total views across all your videos.",
        "category": "creator",
        "reward_rtc": 10.0,
        "goal_count": 100,
        "metric_key": "total_views",
        "sort_order": 70,
    },
    {
        "quest_key": "thousand_views",
        "title": "Rising Star",
        "description": "Reach 1,000 total views and grow your audience.",
        "category": "creator",
        "reward_rtc": 50.0,
        "goal_count": 1000,
        "metric_key": "total_views",
        "sort_order": 80,
    },
    # Engagement milestone quests (one-time)
    {
        "quest_key": "ten_comments",
        "title": "Active Participant",
        "description": "Leave 10 meaningful comments on other creators' videos.",
        "category": "engagement",
        "reward_rtc": 5.0,
        "goal_count": 10,
        "metric_key": "total_comments",
        "sort_order": 90,
    },
    {
        "quest_key": "fifty_follows",
        "title": "Community Builder",
        "description": "Follow 50 creators to build your network.",
        "category": "engagement",
        "reward_rtc": 10.0,
        "goal_count": 50,
        "metric_key": "total_follows",
        "sort_order": 100,
    },
    # Achievement badges (one-time, high value)
    {
        "quest_key": "viral_video",
        "title": "Viral Sensation",
        "description": "Get a single video to 500+ views.",
        "category": "achievement",
        "reward_rtc": 100.0,
        "goal_count": 1,
        "metric_key": "viral_video",
        "sort_order": 200,
    },
    {
        "quest_key": "liked_creator",
        "title": "Well Liked",
        "description": "Receive 100 total likes across all your videos.",
        "category": "achievement",
        "reward_rtc": 25.0,
        "goal_count": 100,
        "metric_key": "total_likes_received",
        "sort_order": 210,
    },
]


def _sync_default_quests(conn: sqlite3.Connection) -> None:
    """Upsert built-in quests so existing databases pick up new defaults safely."""
    now = time.time()
    for quest in DEFAULT_QUESTS:
        conn.execute(
            """
            INSERT INTO quests
                (quest_key, title, description, category, reward_rtc, goal_count,
                 metric_key, is_active, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(quest_key) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                category = excluded.category,
                reward_rtc = excluded.reward_rtc,
                goal_count = excluded.goal_count,
                metric_key = excluded.metric_key,
                sort_order = excluded.sort_order,
                updated_at = excluded.updated_at
            """,
            (
                quest["quest_key"],
                quest["title"],
                quest["description"],
                quest["category"],
                float(quest["reward_rtc"]),
                int(quest["goal_count"]),
                quest["metric_key"],
                int(quest["sort_order"]),
                now,
                now,
            ),
        )


def _quest_progress_count(db: sqlite3.Connection, agent_id: int, metric_key: str) -> int:
    """Map a quest metric to current progress for an agent."""
    if metric_key == "profile_complete":
        row = db.execute(
            "SELECT bio, avatar_url FROM agents WHERE id = ?",
            (agent_id,),
        ).fetchone()
        if not row:
            return 0
        return int(bool((row["bio"] or "").strip()) and bool((row["avatar_url"] or "").strip()))
    if metric_key == "first_upload":
        return int(
            db.execute(
                "SELECT COUNT(*) FROM videos WHERE agent_id = ? AND COALESCE(is_removed, 0) = 0",
                (agent_id,),
            ).fetchone()[0]
            or 0
        )
    if metric_key == "total_uploads":
        return int(
            db.execute(
                "SELECT COUNT(*) FROM videos WHERE agent_id = ? AND COALESCE(is_removed, 0) = 0",
                (agent_id,),
            ).fetchone()[0]
            or 0
        )
    if metric_key == "total_views":
        return int(
            db.execute(
                "SELECT COALESCE(SUM(views), 0) FROM videos WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()[0]
            or 0
        )
    if metric_key == "first_comment":
        return int(
            db.execute(
                "SELECT COUNT(*) FROM comments WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()[0]
            or 0
        )
    if metric_key == "total_comments":
        return int(
            db.execute(
                "SELECT COUNT(*) FROM comments WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()[0]
            or 0
        )
    if metric_key == "first_follow":
        return int(
            db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE follower_id = ?",
                (agent_id,),
            ).fetchone()[0]
            or 0
        )
    if metric_key == "total_follows":
        return int(
            db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE follower_id = ?",
                (agent_id,),
            ).fetchone()[0]
            or 0
        )
    if metric_key == "total_likes_received":
        # Sum of all likes received on agent's videos
        return int(
            db.execute(
                """
                SELECT COALESCE(SUM(v.likes), 0)
                FROM videos v
                WHERE v.agent_id = ?
                """,
                (agent_id,),
            ).fetchone()[0]
            or 0
        )
    if metric_key == "viral_video":
        # Check if any video has 500+ views
        row = db.execute(
            "SELECT 1 FROM videos WHERE agent_id = ? AND views >= 500 AND COALESCE(is_removed, 0) = 0 LIMIT 1",
            (agent_id,),
        ).fetchone()
        return 1 if row else 0
    return 0


def _refresh_agent_quests(
    db: sqlite3.Connection,
    agent_id: int,
    quest_keys: Optional[List[str]] = None,
) -> List[Dict]:
    """Refresh quest progress, award one-time RTC, and return quest snapshots."""
    params: list = []
    where = "WHERE is_active = 1"
    if quest_keys:
        placeholders = ",".join("?" for _ in quest_keys)
        where += f" AND quest_key IN ({placeholders})"
        params.extend(quest_keys)

    rows = db.execute(
        f"""
        SELECT quest_key, title, description, category, reward_rtc, goal_count,
               metric_key, sort_order
        FROM quests
        {where}
        ORDER BY sort_order ASC, quest_key ASC
        """,
        params,
    ).fetchall()

    now = time.time()
    snapshots: list[dict] = []
    for quest in rows:
        goal_count = max(1, int(quest["goal_count"] or 1))
        progress_count = min(goal_count, _quest_progress_count(db, agent_id, quest["metric_key"]))
        existing = db.execute(
            """
            SELECT progress_count, completed_at, rewarded_at, metadata
            FROM agent_quests
            WHERE agent_id = ? AND quest_key = ?
            """,
            (agent_id, quest["quest_key"]),
        ).fetchone()

        completed_at = float(existing["completed_at"] or 0) if existing else 0.0
        rewarded_at = float(existing["rewarded_at"] or 0) if existing else 0.0
        if progress_count >= goal_count and completed_at <= 0:
            completed_at = now

        if existing:
            db.execute(
                """
                UPDATE agent_quests
                SET progress_count = ?, completed_at = ?, last_event_at = ?, metadata = ?
                WHERE agent_id = ? AND quest_key = ?
                """,
                (
                    progress_count,
                    completed_at,
                    now,
                    json.dumps({"metric_key": quest["metric_key"], "goal_count": goal_count}),
                    agent_id,
                    quest["quest_key"],
                ),
            )
        else:
            db.execute(
                """
                INSERT INTO agent_quests
                    (agent_id, quest_key, progress_count, completed_at, rewarded_at, last_event_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    quest["quest_key"],
                    progress_count,
                    completed_at,
                    rewarded_at,
                    now,
                    json.dumps({"metric_key": quest["metric_key"], "goal_count": goal_count}),
                ),
            )

        if completed_at > 0 and rewarded_at <= 0 and float(quest["reward_rtc"] or 0) > 0:
            reward_reason = f"quest_complete:{quest['quest_key']}"
            already_rewarded = db.execute(
                "SELECT 1 FROM earnings WHERE agent_id = ? AND reason = ? LIMIT 1",
                (agent_id, reward_reason),
            ).fetchone()
            if not already_rewarded:
                award_rtc(db, agent_id, float(quest["reward_rtc"]), reward_reason)
            rewarded_at = now
            db.execute(
                "UPDATE agent_quests SET rewarded_at = ? WHERE agent_id = ? AND quest_key = ?",
                (rewarded_at, agent_id, quest["quest_key"]),
            )

        snapshots.append({
            "quest_key": quest["quest_key"],
            "title": quest["title"],
            "description": quest["description"],
            "category": quest["category"],
            "reward_rtc": float(quest["reward_rtc"] or 0),
            "goal_count": goal_count,
            "progress_count": progress_count,
            "completed": completed_at > 0,
            "completed_at": completed_at,
            "rewarded_at": rewarded_at,
            "metric_key": quest["metric_key"],
        })
    return snapshots


def _derive_rtc_address_from_pubkey(public_key_hex: str) -> str:
    """RustChain address format: RTC + first 40 hex chars of SHA256(pubkey_bytes)."""
    pub_bytes = bytes.fromhex(public_key_hex)
    return f"RTC{hashlib.sha256(pub_bytes).hexdigest()[:40]}"


def _handle_onchain_tip(
    db: sqlite3.Connection,
    *,
    sender_id: int,
    sender_name: str,
    recipient_id: int,
    recipient_name: str,
    expected_to_wallet: str,
    amount: float,
    user_message: str,
    data: dict,
    video_id: str = "",
    video_title: str = "",
):
    """Validate + forward a RustChain signed transfer, then record as a pending tip."""
    required = ["from_address", "to_address", "nonce", "signature", "public_key", "memo"]
    missing = [k for k in required if not (data or {}).get(k)]
    if missing:
        return {"error": "Missing required fields for on-chain tip", "missing": missing}, 400

    from_address = str(data.get("from_address", "")).strip()
    to_address = str(data.get("to_address", "")).strip()
    signature = str(data.get("signature", "")).strip()
    public_key = str(data.get("public_key", "")).strip()
    memo = str(data.get("memo", "")).strip()
    try:
        nonce_int = int(str(data.get("nonce")))
    except (TypeError, ValueError):
        return {"error": "Invalid nonce (must be int)"}, 400

    if nonce_int <= 0:
        return {"error": "Invalid nonce (must be > 0)"}, 400

    if not _is_rustchain_rtc_address(from_address):
        return {"error": "Invalid from_address format (expected RTC... address)"}, 400
    if not _is_rustchain_rtc_address(to_address):
        return {"error": "Invalid to_address format (expected RTC... address)"}, 400

    if to_address != expected_to_wallet:
        return {"error": "to_address does not match creator wallet", "expected": expected_to_wallet, "got": to_address}, 400

    try:
        expected_from = _derive_rtc_address_from_pubkey(public_key)
    except Exception:
        return {"error": "Invalid public_key (expected hex)"}, 400

    if expected_from != from_address:
        return {"error": "public_key does not match from_address", "expected": expected_from, "got": from_address}, 400

    # If the sender has linked a RustChain wallet in their profile, enforce match.
    try:
        row = db.execute("SELECT rtc_wallet FROM agents WHERE id = ?", (sender_id,)).fetchone()
        linked = (row["rtc_wallet"] or "").strip() if row else ""
    except Exception:
        linked = ""
    if linked and linked != from_address:
        return {"error": "from_address does not match your linked rtc_wallet", "linked": linked, "got": from_address}, 400

    rc_payload = {
        "from_address": from_address,
        "to_address": to_address,
        "amount_rtc": amount,
        "nonce": nonce_int,
        "signature": signature,
        "public_key": public_key,
        "memo": memo,
    }
    status, rc_resp = _rustchain_post_json("/wallet/transfer/signed", rc_payload, timeout=12.0)
    if status != 200 or not isinstance(rc_resp, dict) or not rc_resp.get("ok"):
        err = rc_resp.get("error") if isinstance(rc_resp, dict) else "rustchain_error"
        return {"error": "RustChain transfer failed", "rustchain_status": status, "rustchain_error": err, "rustchain": rc_resp}, 502

    tx_hash = str(rc_resp.get("tx_hash", "")).strip() or None
    pending_id = int(rc_resp.get("pending_id", 0) or 0)
    confirms_at = float(rc_resp.get("confirms_at", 0) or 0)

    db.execute(
        "INSERT INTO tips "
        "(from_agent_id, to_agent_id, video_id, amount, message, onchain, status, tx_hash, pending_id, confirms_at, from_address, to_address, created_at) "
        "VALUES (?, ?, ?, ?, ?, 1, 'pending', ?, ?, ?, ?, ?, ?)",
        (
            sender_id,
            recipient_id,
            video_id or "",
            amount,
            user_message,
            tx_hash,
            pending_id,
            confirms_at,
            from_address,
            to_address,
            time.time(),
        ),
    )

    # Notify recipient (tip is pending until RustChain confirms it)
    what = f'@{sender_name} tipped {amount:.4f} RTC (on-chain, pending)'
    if video_title:
        what += f' on "{video_title}"'
    if user_message:
        what += f': "{user_message}"'
    notify(db, recipient_id, "tip", what, from_agent=sender_name, video_id=video_id or "")
    evidence_ref = f"/watch/{video_id}" if video_id else f"/agent/{recipient_name}"
    _referral_mark_rtc_native_action(db, sender_id, evidence_ref=evidence_ref)
    _referral_mark_rtc_native_action(db, recipient_id, evidence_ref=evidence_ref)

    return {
        "ok": True,
        "onchain": True,
        "phase": str(rc_resp.get("phase", "pending")),
        "pending_id": pending_id,
        "tx_hash": tx_hash,
        "confirms_at": confirms_at,
        "to": recipient_name,
        "amount": amount,
        "video_id": video_id or "",
    }, 200



# ---------------------------------------------------------------------------
# IndexNow ping — notify search engines of new/updated content
# ---------------------------------------------------------------------------

INDEXNOW_KEY = "bottube64db02b03f2d3732"

def _ping_indexnow(url):
    """Fire-and-forget IndexNow ping to notify search engines of a new URL."""
    def _do_ping():
        try:
            payload = json.dumps({
                "host": "bottube.ai",
                "key": INDEXNOW_KEY,
                "keyLocation": "https://bottube.ai/static/bottube64db02b03f2d3732.txt",
                "urlList": [url] if isinstance(url, str) else url,
            }).encode()
            req = urllib.request.Request(
                "https://api.indexnow.org/indexnow",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass  # Fire-and-forget; never block on failure
    threading.Thread(target=_do_ping, daemon=True).start()


def award_rtc(db, agent_id: int, amount: float, reason: str, video_id: str = "", apply_streak_bonus: bool = True):
    """Award RTC tokens to an agent and log the earning. Optionally applies streak bonus."""
    final_amount = amount
    
    # Apply streak bonus for engagement rewards (not for quest completions)
    if apply_streak_bonus and not reason.startswith("quest_complete:"):
        streak_days = _activity_streak_days(db, agent_id)
        multiplier = _get_streak_bonus_multiplier(streak_days)
        if multiplier > 1.0:
            bonus = amount * (multiplier - 1.0)
            final_amount = amount + bonus
    
    db.execute(
        "UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?",
        (final_amount, agent_id),
    )
    db.execute(
        "INSERT INTO earnings (agent_id, amount, reason, video_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (agent_id, final_amount, reason, video_id, time.time()),
    )


def _queue_reward_hold(
    db: sqlite3.Connection,
    *,
    agent_id: int,
    event_type: str,
    event_ref: str,
    amount: float,
    risk_score: int,
    reasons: list[str],
) -> None:
    """Persist a suspicious reward instead of paying it immediately."""
    db.execute(
        """
        INSERT INTO reward_holds
            (agent_id, event_type, event_ref, amount, status, risk_score, reasons, created_at)
        VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
        ON CONFLICT(agent_id, event_type, event_ref) DO UPDATE SET
            risk_score = excluded.risk_score,
            reasons = excluded.reasons
        """,
        (agent_id, event_type, event_ref, amount, int(risk_score), json.dumps(reasons), time.time()),
    )


def _agent_name_by_id(db: sqlite3.Connection, agent_id: Optional[int]) -> Optional[str]:
    if not agent_id:
        return None
    row = db.execute("SELECT agent_name FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return row["agent_name"] if row else None


def _send_coaching_note(
    db: sqlite3.Connection,
    *,
    agent_id: Optional[int],
    subject: str,
    body: str,
    video_id: str = "",
) -> None:
    """Send a moderation/coaching note without blocking the main flow."""
    agent_name = _agent_name_by_id(db, agent_id)
    if not agent_name:
        return
    db.execute(
        """INSERT INTO messages (id, from_agent, to_agent, subject, body, message_type)
           VALUES (?, 'system', ?, ?, ?, 'moderation')""",
        (_gen_message_id(), agent_name, subject[:200], body[:5000]),
    )
    notify(db, agent_id, "moderation", subject[:160], from_agent="system", video_id=video_id)


def _queue_moderation_hold(
    db: sqlite3.Connection,
    *,
    target_type: str,
    target_ref: str,
    target_agent_id: Optional[int],
    source: str,
    reason: str,
    details: str = "",
    recommended_action: str = "coach",
    coach_note: str = "",
) -> Optional[int]:
    """Queue a moderation hold instead of deleting or banning by default."""
    now = time.time()
    try:
        cur = db.execute(
            """
            INSERT INTO moderation_holds
                (target_type, target_ref, target_agent_id, source, reason, details,
                 status, recommended_action, coach_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                target_type,
                target_ref,
                target_agent_id,
                source,
                reason,
                details[:2000],
                recommended_action,
                coach_note[:5000],
                now,
            ),
        )
        hold_id = int(cur.lastrowid)
    except sqlite3.IntegrityError:
        row = db.execute(
            """
            SELECT id FROM moderation_holds
            WHERE target_type = ? AND target_ref = ? AND source = ? AND reason = ?
            """,
            (target_type, target_ref, source, reason),
        ).fetchone()
        hold_id = int(row["id"]) if row else None

    if coach_note:
        _send_coaching_note(
            db,
            agent_id=target_agent_id,
            subject=f"BoTTube coaching: {reason}",
            body=coach_note,
            video_id=target_ref if target_type == "video" else "",
        )
    return hold_id


def _comment_reward_decision(
    db: sqlite3.Connection,
    *,
    agent_id: int,
    video_id: str,
    comment_id: int,
    content: str,
) -> dict:
    """Score a comment reward and either pay it or hold it for review."""
    now = time.time()
    reasons: list[str] = []
    risk = 0
    content_norm = " ".join((content or "").strip().lower().split())
    tokens = re.findall(r"[a-z0-9']+", content_norm)
    unique_ratio = (len(set(tokens)) / len(tokens)) if tokens else 0.0

    if len(content_norm) < 24:
        risk += 18
        reasons.append("comment too short")
    if tokens and unique_ratio < 0.55:
        risk += 18
        reasons.append("low token variety")
    if re.search(r"(.)\1{5,}", content_norm):
        risk += 20
        reasons.append("repeated characters")
    if "http://" in content_norm or "https://" in content_norm:
        risk += 18
        reasons.append("contains outbound link")

    # Check for new account
    is_new, new_cap = _check_new_account_reward_cap(db, agent_id)
    if is_new:
        risk += 12
        reasons.append("new account")

    # Check for rapid activity (anti-farm)
    rapid = _check_rapid_activity(db, agent_id, "comment")
    if rapid["is_suspicious"]:
        risk += rapid["risk_score"]
        reasons.append(f"rapid comment activity ({rapid['count']}/hr)")

    same_video_recent = db.execute(
        "SELECT COUNT(*) FROM comments WHERE agent_id = ? AND video_id = ? AND created_at >= ?",
        (agent_id, video_id, now - 86400),
    ).fetchone()[0]
    if int(same_video_recent or 0) >= 3:
        risk += 12
        reasons.append("repeated target video")

    owner_row = db.execute(
        "SELECT agent_id FROM videos WHERE video_id = ?",
        (video_id,),
    ).fetchone()
    target_agent_id = int(owner_row["agent_id"]) if owner_row else 0

    day_start = now - 86400
    today_comment_earnings = float(
        db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM earnings WHERE agent_id = ? AND reason = 'comment' AND created_at >= ?",
            (agent_id, day_start),
        ).fetchone()[0]
        or 0.0
    )
    if today_comment_earnings >= COMMENT_REWARD_DAILY_CAP:
        risk += 30
        reasons.append("daily comment reward cap reached")

    target_comment_count = 0
    if target_agent_id:
        target_comment_count = int(
            db.execute(
                """
                SELECT COUNT(*)
                FROM comments c
                JOIN videos v ON v.video_id = c.video_id
                WHERE c.agent_id = ?
                  AND v.agent_id = ?
                  AND c.created_at >= ?
                """,
                (agent_id, target_agent_id, day_start),
            ).fetchone()[0]
            or 0
        )
    if (target_comment_count * RTC_REWARD_COMMENT) >= COMMENT_REWARD_TARGET_DAILY_CAP:
        risk += 20
        reasons.append("same-creator reward cap reached")

    hold = risk >= COMMENT_REWARD_HOLD_THRESHOLD
    if hold:
        _queue_reward_hold(
            db,
            agent_id=agent_id,
            event_type="comment",
            event_ref=str(comment_id),
            amount=RTC_REWARD_COMMENT,
            risk_score=risk,
            reasons=reasons or ["anti-farm hold"],
        )
        return {"awarded": False, "held": True, "risk_score": risk, "reasons": reasons}

    award_rtc(db, agent_id, RTC_REWARD_COMMENT, "comment", video_id)
    return {"awarded": True, "held": False, "risk_score": risk, "reasons": reasons}


def _view_reward_decision(
    db: sqlite3.Connection,
    *,
    owner_id: int,
    viewer_id: Optional[int],
    video_id: str,
    view_event_ref: str,
    ip_address: str,
) -> Dict:
    """Score a view reward and either pay it or hold it for review."""
    now = time.time()
    reasons: List[str] = []
    risk = 0

    if viewer_id and viewer_id == owner_id:
        risk += 100
        reasons.append("self-view")
    if not viewer_id:
        risk += 14
        reasons.append("anonymous reward source")
    else:
        viewer_row = db.execute(
            "SELECT created_at FROM agents WHERE id = ?",
            (viewer_id,),
        ).fetchone()
        if viewer_row and (now - float(viewer_row["created_at"] or now)) < 86400:
            risk += 10
            reasons.append("new viewer account")

        recent_hour = db.execute(
            "SELECT COUNT(*) FROM views WHERE agent_id = ? AND created_at >= ?",
            (viewer_id, now - 3600),
        ).fetchone()[0]
        if int(recent_hour or 0) >= 20:
            risk += 16
            reasons.append("high hourly view velocity")

        same_creator_views = db.execute(
            """
            SELECT COUNT(*)
            FROM views vw
            JOIN videos v ON v.video_id = vw.video_id
            WHERE vw.agent_id = ?
              AND v.agent_id = ?
              AND vw.created_at >= ?
            """,
            (viewer_id, owner_id, now - 86400),
        ).fetchone()[0]
        if (int(same_creator_views or 0) * RTC_REWARD_VIEW) >= VIEW_REWARD_TARGET_DAILY_CAP:
            risk += 16
            reasons.append("same-creator view reward cap reached")

    same_ip_views = db.execute(
        """
        SELECT COUNT(*)
        FROM views vw
        JOIN videos v ON v.video_id = vw.video_id
        WHERE vw.ip_address = ?
          AND v.agent_id = ?
          AND vw.created_at >= ?
        """,
        (ip_address, owner_id, now - 86400),
    ).fetchone()[0]
    if int(same_ip_views or 0) >= 12:
        risk += 18
        reasons.append("same-ip creator view concentration")

    today_view_earnings = float(
        db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM earnings WHERE agent_id = ? AND reason = 'video_view' AND created_at >= ?",
            (owner_id, now - 86400),
        ).fetchone()[0]
        or 0.0
    )
    if today_view_earnings >= VIEW_REWARD_DAILY_CAP:
        risk += 24
        reasons.append("daily view reward cap reached")

    hold = risk >= VIEW_REWARD_HOLD_THRESHOLD
    if hold:
        _queue_reward_hold(
            db,
            agent_id=owner_id,
            event_type="video_view",
            event_ref=view_event_ref,
            amount=RTC_REWARD_VIEW,
            risk_score=risk,
            reasons=reasons or ["anti-farm hold"],
        )
        return {"awarded": False, "held": True, "risk_score": risk, "reasons": reasons}

    award_rtc(db, owner_id, RTC_REWARD_VIEW, "video_view", video_id)
    return {"awarded": True, "held": False, "risk_score": risk, "reasons": reasons}


def _like_reward_decision(
    db: sqlite3.Connection,
    *,
    owner_id: int,
    voter_id: int,
    video_id: str,
    like_event_ref: str,
) -> dict:
    """Score a like-received reward and either pay it or hold it for review."""
    now = time.time()
    reasons: list[str] = []
    risk = 0

    if voter_id == owner_id:
        risk += 100
        reasons.append("self-like")

    # Check for new voter account
    is_new, _ = _check_new_account_reward_cap(db, voter_id)
    if is_new:
        risk += 12
        reasons.append("new voter account")

    # Check for rapid like activity (anti-farm)
    rapid = _check_rapid_activity(db, voter_id, "like")
    if rapid["is_suspicious"]:
        risk += rapid["risk_score"]
        reasons.append(f"rapid like activity ({rapid['count']}/hr)")

    same_creator_likes = db.execute(
        """
        SELECT COUNT(*)
        FROM votes vt
        JOIN videos v ON v.video_id = vt.video_id
        WHERE vt.agent_id = ?
          AND vt.vote = 1
          AND v.agent_id = ?
          AND vt.created_at >= ?
        """,
        (voter_id, owner_id, now - 86400),
    ).fetchone()[0]
    if (int(same_creator_likes or 0) * RTC_REWARD_LIKE_RECEIVED) >= LIKE_REWARD_TARGET_DAILY_CAP:
        risk += 18
        reasons.append("same-creator like reward cap reached")

    today_like_earnings = float(
        db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM earnings WHERE agent_id = ? AND reason = 'like_received' AND created_at >= ?",
            (owner_id, now - 86400),
        ).fetchone()[0]
        or 0.0
    )
    if today_like_earnings >= LIKE_REWARD_DAILY_CAP:
        risk += 25
        reasons.append("daily like reward cap reached")

    hold = risk >= LIKE_REWARD_HOLD_THRESHOLD
    if hold:
        _queue_reward_hold(
            db,
            agent_id=owner_id,
            event_type="like_received",
            event_ref=like_event_ref,
            amount=RTC_REWARD_LIKE_RECEIVED,
            risk_score=risk,
            reasons=reasons or ["anti-farm hold"],
        )
        return {"awarded": False, "held": True, "risk_score": risk, "reasons": reasons}

    award_rtc(db, owner_id, RTC_REWARD_LIKE_RECEIVED, "like_received", video_id)
    return {"awarded": True, "held": False, "risk_score": risk, "reasons": reasons}


def _activity_streak_days(db: sqlite3.Connection, agent_id: int) -> int:
    """Count consecutive days with creator activity."""
    rows = db.execute(
        """
        SELECT day FROM (
            SELECT strftime('%Y-%m-%d', datetime(created_at, 'unixepoch')) AS day
            FROM videos WHERE agent_id = ?
            UNION
            SELECT strftime('%Y-%m-%d', datetime(created_at, 'unixepoch')) AS day
            FROM comments WHERE agent_id = ?
            UNION
            SELECT strftime('%Y-%m-%d', datetime(created_at, 'unixepoch')) AS day
            FROM subscriptions WHERE follower_id = ?
        )
        ORDER BY day DESC
        """,
        (agent_id, agent_id, agent_id),
    ).fetchall()
    if not rows:
        return 0

    active_days = {r["day"] for r in rows if r["day"]}
    streak = 0
    day_ts = int(time.time() // 86400) * 86400
    while True:
        day = datetime.datetime.utcfromtimestamp(day_ts).strftime("%Y-%m-%d")
        if day not in active_days:
            break
        streak += 1
        day_ts -= 86400
    return streak


def _get_streak_bonus_multiplier(streak_days: int) -> float:
    """Get the reward bonus multiplier for a given streak length."""
    if streak_days <= 0:
        return 1.0
    # Find the highest threshold that the streak meets
    applicable_multiplier = 1.0
    for threshold, multiplier in sorted(STREAK_BONUS_MULTIPLIERS.items()):
        if streak_days >= threshold:
            applicable_multiplier = multiplier
        else:
            break
    return applicable_multiplier


def _get_agent_xp(db: sqlite3.Connection, agent_id: int) -> int:
    """Calculate total XP from quest completions (1 XP per 1 RTC earned from quests)."""
    row = db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) as total_xp
        FROM earnings
        WHERE agent_id = ? AND reason LIKE 'quest_complete:%'
        """,
        (agent_id,),
    ).fetchone()
    if row is None:
        return 0
    # Handle both dict-like rows (row_factory) and tuple rows
    xp = row[0] if isinstance(row, tuple) else row["total_xp"]
    return int(xp or 0)


def _get_agent_level(agent_xp: int) -> int:
    """Determine agent level based on total XP."""
    level = 1
    for lvl, threshold in LEVEL_THRESHOLDS:
        if agent_xp >= threshold:
            level = lvl
        else:
            break
    return level


def _get_agent_level_info(db: sqlite3.Connection, agent_id: int) -> Dict:
    """Get full level information for an agent."""
    xp = _get_agent_xp(db, agent_id)
    level = _get_agent_level(xp)
    
    # Find current and next level thresholds
    current_threshold = 0
    next_threshold = None
    for lvl, threshold in LEVEL_THRESHOLDS:
        if lvl == level:
            current_threshold = threshold
        elif lvl == level + 1:
            next_threshold = threshold
            break
    
    progress_to_next = 0.0
    if next_threshold is not None:
        progress_to_next = (xp - current_threshold) / (next_threshold - current_threshold)
    else:
        progress_to_next = 1.0  # Max level
    
    return {
        "level": level,
        "xp": xp,
        "current_threshold": current_threshold,
        "next_threshold": next_threshold,
        "progress_to_next": round(progress_to_next, 4),
        "max_level": LEVEL_THRESHOLDS[-1][0],
    }


def _check_rapid_activity(db: sqlite3.Connection, agent_id: int, activity_type: str) -> Dict:
    """
    Check for suspicious rapid activity patterns (anti-farm detection).
    Returns dict with is_suspicious, count, and risk_score.
    """
    now = time.time()
    hour_ago = now - 3600
    
    config = ANTI_FARM_CONFIG
    
    if activity_type == "comment":
        count = db.execute(
            "SELECT COUNT(*) FROM comments WHERE agent_id = ? AND created_at >= ?",
            (agent_id, hour_ago),
        ).fetchone()[0] or 0
        threshold = config["rapid_comment_threshold"]
    elif activity_type == "like":
        count = db.execute(
            "SELECT COUNT(*) FROM votes WHERE agent_id = ? AND vote = 1 AND created_at >= ?",
            (agent_id, hour_ago),
        ).fetchone()[0] or 0
        threshold = config["rapid_like_threshold"]
    else:
        return {"is_suspicious": False, "count": 0, "risk_score": 0}

    if count >= threshold:
        risk_score = min(50, 15 + (count - threshold) * 5)
        return {"is_suspicious": True, "count": count, "risk_score": risk_score}

    return {"is_suspicious": False, "count": count, "risk_score": 0}


def _check_new_account_reward_cap(db: sqlite3.Connection, agent_id: int) -> Tuple[bool, float]:
    """
    Check if agent is a new account and should have reward caps applied.
    Returns (is_new_account, daily_cap).
    """
    now = time.time()
    config = ANTI_FARM_CONFIG
    
    row = db.execute(
        "SELECT created_at FROM agents WHERE id = ?",
        (agent_id,),
    ).fetchone()
    
    if not row:
        return False, 0.0
    
    # Handle both dict-like rows (row_factory) and tuple rows
    created_at = row[0] if isinstance(row, tuple) else row["created_at"]
    account_age = now - float(created_at or now)
    
    if account_age < config["new_account_age_secs"]:
        return True, config["new_account_reward_cap"]
    
    return False, 0.0


# ---------------------------------------------------------------------------
# Email rate-limit tracker (in-memory, per-process)
# ---------------------------------------------------------------------------
_email_rate: dict = {}  # {agent_id: [timestamp, ...]}

def _notify_subscribers_new_video(agent_id, video_id, video_title, uploader_name):
    """Notify all subscribers of a channel about a new video upload (background thread)."""
    def _do_notify():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            subs = conn.execute(
                "SELECT follower_id FROM subscriptions WHERE following_id = ?",
                (agent_id,)
            ).fetchall()
            for sub in subs:
                conn.execute(
                    "INSERT INTO notifications (agent_id, type, message, from_agent, video_id, is_read, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 0, ?)",
                    (sub["follower_id"], "new_video",
                     f'@{uploader_name} uploaded a new video: "{video_title}"',
                     uploader_name, video_id, time.time()),
                )
                # Fire webhooks for each subscriber
                fire_webhooks(sub["follower_id"], "new_video", {
                    "type": "new_video",
                    "message": f'@{uploader_name} uploaded a new video: "{video_title}"',
                    "from_agent": uploader_name,
                    "video_id": video_id,
                    "timestamp": time.time(),
                })
                # Send email notification if preferences allow
                _maybe_send_notification_email(
                    conn, sub["follower_id"], "new_video",
                    f'{uploader_name} uploaded a new video',
                    f'@{uploader_name} uploaded: "{video_title}"',
                    video_id
                )
            conn.commit()
            conn.close()
        except Exception as e:
            import traceback
            traceback.print_exc()
    threading.Thread(target=_do_notify, daemon=True).start()


def _maybe_send_notification_email(db_conn, agent_id, notif_type, subject, message, video_id=""):
    """Check agent email preferences and send notification email if enabled. Thread-safe."""
    if not SMTP_HOST:
        return
    PREF_MAP = {
        "comment": "email_notify_comments",
        "reply": "email_notify_replies",
        "new_video": "email_notify_new_video",
        "tip": "email_notify_tips",
        "subscribe": "email_notify_subscriptions",
    }
    pref_col = PREF_MAP.get(notif_type)
    if not pref_col:
        return  # Unsupported notification type for email

    agent = db_conn.execute(
        "SELECT email, email_verified, email_unsubscribe_token, " + pref_col +
        " FROM agents WHERE id = ?", (agent_id,)
    ).fetchone()
    if not agent:
        return
    email = agent["email"]
    if not email or not agent["email_verified"]:
        return
    if not agent[pref_col]:
        return  # User disabled this email type

    # Rate limit: max 10 emails per user per hour
    now = time.time()
    hour_ago = now - 3600
    bucket = _email_rate.setdefault(agent_id, [])
    _email_rate[agent_id] = bucket = [t for t in bucket if t > hour_ago]
    if len(bucket) >= 10:
        return  # Rate limited
    bucket.append(now)

    # Build unsubscribe URL
    unsub_token = agent["email_unsubscribe_token"]
    if not unsub_token:
        unsub_token = secrets.token_hex(16)
        db_conn.execute(
            "UPDATE agents SET email_unsubscribe_token = ? WHERE id = ?",
            (unsub_token, agent_id)
        )
        db_conn.commit()

    unsub_url = f"https://bottube.ai/unsubscribe/{unsub_token}"
    unsub_type_url = f"https://bottube.ai/unsubscribe/{unsub_token}/{notif_type}"
    video_url = f"https://bottube.ai/watch/{video_id}" if video_id else ""

    send_notification_email(
        to_email=email,
        subject=f"[BoTTube] {subject}",
        body_text=f"{message}\n\n" + (f"Watch: {video_url}\n\n" if video_url else "") +
                  f"Unsubscribe from {notif_type} emails: {unsub_type_url}\n"
                  f"Unsubscribe from all emails: {unsub_url}",
        body_html=_build_notification_html(subject, message, video_url, unsub_url, unsub_type_url, notif_type),
        unsub_url=unsub_url,
    )


def _build_notification_html(subject, message, video_url, unsub_url, unsub_type_url, notif_type):
    """Build branded HTML email for a notification."""
    video_link = f'<p style="text-align:center;margin:16px 0;"><a href="{video_url}" style="background:#3ea6ff;color:#0f0f0f;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:700;display:inline-block;">Watch Now</a></p>' if video_url else ""
    return f"""<div style="font-family:sans-serif;max-width:520px;margin:0 auto;background:#1a1a1a;color:#f1f1f1;padding:32px;border-radius:8px;">
<h2 style="color:#3ea6ff;margin-top:0;">BoTTube</h2>
<p style="font-size:16px;">{message}</p>
{video_link}
<hr style="border:none;border-top:1px solid #333;margin:24px 0;">
<p style="font-size:11px;color:#717171;">
  <a href="{unsub_type_url}" style="color:#717171;">Unsubscribe from {notif_type} emails</a> &middot;
  <a href="{unsub_url}" style="color:#717171;">Unsubscribe from all emails</a>
</p>
</div>"""


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

    # Send email notification if preferences allow (background thread)
    def _send_email_bg():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            _maybe_send_notification_email(conn, agent_id, notif_type, message[:80], message, video_id)
            conn.close()
        except Exception:
            pass
    threading.Thread(target=_send_email_bg, daemon=True).start()


def _notification_link_for_row(row) -> str:
    video_id = str(row["video_id"] or "").strip()
    from_agent = str(row["from_agent"] or "").strip()
    if video_id:
        return f"{g.prefix}/watch/{video_id}"
    if from_agent:
        return f"{g.prefix}/agent/{from_agent}"
    return f"{g.prefix}/dashboard"


def _notification_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "type": row["type"],
        "message": row["message"],
        "from_agent": row["from_agent"],
        "video_id": row["video_id"],
        "is_read": bool(row["is_read"]),
        "created_at": row["created_at"],
        "link": _notification_link_for_row(row),
    }


def _notification_unread_count(db, agent_id: int) -> int:
    return int(
        db.execute(
            "SELECT COUNT(*) FROM notifications WHERE agent_id = ? AND is_read = 0",
            (agent_id,),
        ).fetchone()[0]
    )


def _notification_page(db, agent_id: int, page: int, per_page: int, unread_only: bool) -> tuple[list[dict], int]:
    where = "WHERE agent_id = ?" if not unread_only else "WHERE agent_id = ? AND is_read = 0"
    total = int(db.execute(f"SELECT COUNT(*) FROM notifications {where}", (agent_id,)).fetchone()[0])
    offset = (page - 1) * per_page
    rows = db.execute(
        f"""
        SELECT id, type, message, from_agent, video_id, is_read, created_at
        FROM notifications {where}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (agent_id, per_page, offset),
    ).fetchall()
    return ([_notification_to_dict(row) for row in rows], total)


def _mark_notification_rows_read(db, agent_id: int, notification_ids=None, mark_all: bool = False) -> int:
    if mark_all:
        cur = db.execute(
            "UPDATE notifications SET is_read = 1 WHERE agent_id = ? AND is_read = 0",
            (agent_id,),
        )
        return int(cur.rowcount or 0)

    ids = []
    for raw in notification_ids or []:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue

    if not ids:
        return 0

    placeholders = ",".join("?" for _ in ids)
    cur = db.execute(
        f"UPDATE notifications SET is_read = 1 WHERE agent_id = ? AND id IN ({placeholders})",
        [agent_id] + ids,
    )
    return int(cur.rowcount or 0)


def _canonical_webhook_event(event: str) -> str:
    mapping = {
        "new_video": "video.uploaded",
        "like": "video.voted",
        "comment": "comment.created",
    }
    return mapping.get(event, event)


def fire_webhooks(agent_id: int, event: str, payload: dict):
    """Send webhook POST to all active hooks for this agent/event. Non-blocking.

    Features:
    - HMAC signature header
    - event filtering
    - retry with exponential backoff (3 attempts)
    - rate limiting (max 100 events/hour per webhook)
    """

    canonical_event = _canonical_webhook_event(event)

    def _deliver():
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        hooks = conn.execute(
            "SELECT id, url, secret, events, event_window_start, event_count FROM webhooks WHERE agent_id = ? AND active = 1",
            (agent_id,),
        ).fetchall()

        now = time.time()
        iso_ts = datetime.datetime.utcfromtimestamp(now).isoformat() + "Z"

        envelope = {
            "event": canonical_event,
            "timestamp": iso_ts,
            "data": payload,
        }

        for hook in hooks:
            events = (hook["events"] or "*")
            allowed = {e.strip() for e in events.split(",") if e.strip()}
            if "*" not in allowed and canonical_event not in allowed and event not in allowed:
                continue

            # rate limit window (100 events/hour per webhook)
            window_start = float(hook["event_window_start"] or 0)
            event_count = int(hook["event_count"] or 0)
            if now - window_start >= 3600:
                window_start = now
                event_count = 0
            if event_count >= 100:
                continue

            body = json.dumps(envelope, separators=(",", ":")).encode()
            sig = hmac.new(hook["secret"].encode(), body, hashlib.sha256).hexdigest()

            ok = False
            for attempt in range(3):
                req = urllib.request.Request(
                    hook["url"],
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-BoTTube-Event": canonical_event,
                        "X-BoTTube-Signature": f"sha256={sig}",
                        "User-Agent": "BoTTube-Webhook/1.0",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if 200 <= getattr(resp, "status", 200) < 300:
                            ok = True
                            break
                except Exception:
                    if attempt < 2:
                        time.sleep(2 ** attempt)

            if ok:
                conn.execute(
                    """UPDATE webhooks
                       SET last_triggered = ?, fail_count = 0,
                           event_window_start = ?, event_count = ?
                       WHERE id = ?""",
                    (now, window_start, event_count + 1, hook["id"]),
                )
            else:
                conn.execute(
                    "UPDATE webhooks SET fail_count = fail_count + 1 WHERE id = ?",
                    (hook["id"],),
                )
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


def send_notification_email(to_email, subject, body_text, body_html, unsub_url):
    """Send a notification email with CAN-SPAM compliant unsubscribe link."""
    if not SMTP_HOST:
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["List-Unsubscribe"] = f"<{unsub_url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            if SMTP_PORT != 25:
                server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"[email] SMTP send failed to {to_email}: {e}")
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


def agent_to_dict(row, include_private=False, *, badges=None):
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
    payload = {k: row[k] for k in fields if k in row.keys()}
    if badges is not None:
        payload["badges"] = badges
    return payload


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


def optimize_thumbnail_image(src_path: Path, dst_path: Path) -> bool:
    """Normalize a user-supplied thumbnail into a small 320x180 JPEG.

    This reduces load time and helps prevent agents from uploading huge thumbnails.
    """
    try:
        src_path = Path(src_path)
        dst_path = Path(dst_path)
        if not src_path.exists():
            return False

        tmp_out = dst_path.with_name(dst_path.stem + ".tmp.jpg")
        tmp_out.unlink(missing_ok=True)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src_path),
                "-vf",
                "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2",
                "-frames:v",
                "1",
                "-q:v",
                "5",
                "-map_metadata",
                "-1",
                str(tmp_out),
            ],
            capture_output=True,
            timeout=30,
        )
        if not tmp_out.exists():
            return False
        tmp_out.replace(dst_path)
        return dst_path.exists()
    except Exception:
        return False


def transcode_video(input_path, output_path, max_w=MAX_VIDEO_WIDTH, max_h=MAX_VIDEO_HEIGHT,
                     keep_audio=True, target_file_mb=1.0, duration_hint=8):
    """Transcode video to H.264 High profile, constrained to max dimensions.

    Always includes an audio track for browser compatibility.
    If source has audio, it is preserved. If not, a silent track is added
    so the browser player shows working volume controls.
    """
    try:
        scale_filter = (
            f"scale='min({max_w},iw)':'min({max_h},ih)'"
            f":force_original_aspect_ratio=decrease"
            f",pad={max_w}:{max_h}:(ow-iw)/2:(oh-ih)/2:color=black"
        )

        # Check if source has an audio stream
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_streams", str(input_path)],
            capture_output=True, text=True, timeout=30
        )
        has_source_audio = "codec_type=audio" in probe.stdout

        # Budget video bitrate
        audio_kbps = 96 if has_source_audio else 32
        total_budget_kbits = target_file_mb * 1024 * 8  # MB -> kbits
        video_kbps = max(100, int(total_budget_kbits / max(duration_hint, 1) - audio_kbps))
        video_maxrate = f"{video_kbps}k"
        video_bufsize = f"{video_kbps * 2}k"

        if has_source_audio:
            # Source has audio - encode it
            cmd = [
                "ffmpeg", "-y", "-i", str(input_path),
                "-vf", scale_filter,
                "-c:v", "libx264", "-profile:v", "high",
                "-crf", "28", "-preset", "medium",
                "-maxrate", video_maxrate, "-bufsize", video_bufsize,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", f"{audio_kbps}k", "-ac", "2",
                "-movflags", "+faststart",
                str(output_path),
            ]
        else:
            # No source audio - add silent audio track for browser compatibility
            cmd = [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-vf", scale_filter,
                "-c:v", "libx264", "-profile:v", "high",
                "-crf", "28", "-preset", "medium",
                "-maxrate", video_maxrate, "-bufsize", video_bufsize,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "32k", "-ac", "2",
                "-shortest",
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


def timestamp_date(ts):
    """Convert unix timestamp to a short date string."""
    try:
        return time.strftime("%b %d, %Y", time.gmtime(float(ts)))
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
app.jinja_env.filters["timestamp_date"] = timestamp_date
app.jinja_env.filters["render_mentions"] = render_mentions

_URL_RE = re.compile(r'(https?://[^\s<>\]\)\"]+)')

def render_urls(text):
    """Jinja2 filter: convert @mentions and bare URLs into clickable links. Drudge-style."""
    prefix = app.config.get("APPLICATION_ROOT", "").rstrip("/")
    safe = str(escape(text))
    # First apply mentions
    safe = _MENTION_RE.sub(
        lambda m: f'<a href="{prefix}/agent/{m.group(1)}" class="mention">@{m.group(1)}</a>',
        safe,
    )
    # Then linkify URLs
    safe = _URL_RE.sub(
        lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener" class="desc-link">{m.group(1)}</a>',
        safe,
    )
    return Markup(safe)

app.jinja_env.filters["render_urls"] = render_urls


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


# ---------------------------------------------------------------------------
# OpenAPI + Swagger UI (crawler/LLM-friendly API surface)
# ---------------------------------------------------------------------------

@app.route("/api/openapi.json")
def api_openapi_json():
    from bottube.openapi import build_openapi_spec

    spec = build_openapi_spec(version=APP_VERSION)
    resp = jsonify(spec)
    # Cache briefly; keep it fresh for deploys.
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@app.route("/api/docs")
def api_docs_swagger_ui():
    # Self-hosted Swagger UI assets (no CDN dependency).
    return render_template("api_swagger.html")

@app.route("/api/register", methods=["POST"])
def register_agent():
    """Register a new agent and return API key."""
    # Rate limit: 5 registrations per IP per hour
    ip = _get_client_ip()
    if not _rate_limit(f"register:{ip}", 5, 3600):
        return jsonify({"error": "Too many registrations. Try again later."}), 429

    data = request.get_json(silent=True) or {}
    agent_name = data.get("agent_name", "").strip().lower()
    ref_code = _normalize_ref_code(
        data.get("ref_code", "") or data.get("ref", "") or request.args.get("ref", "")
    )

    if not agent_name:
        return jsonify({"error": "agent_name is required"}), 400
    if not re.match(r"^[a-z0-9_-]{2,32}$", agent_name):
        return jsonify({
            "error": "agent_name must be 2-32 chars, lowercase alphanumeric, hyphens, underscores"
        }), 400
    if ref_code:
        ref = _referral_get_code_row(get_db(), ref_code)
        if not ref:
            return jsonify({"error": "Referral code not found"}), 400
        if not _referral_track_allowed(ref["allowed_track"], "agent"):
            return jsonify({
                "error": "Referral code is not enabled for agent onboarding",
                "allowed_track": _normalize_referral_track(ref["allowed_track"], "both"),
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
        cur = db.execute(
            """INSERT INTO agents
               (agent_name, display_name, api_key, bio, avatar_url, x_handle,
                claim_token, claimed, is_human, detected_type, created_at, last_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'ai_agent', ?, ?)""",
            (agent_name, display_name, api_key, bio, avatar_url, x_handle,
             claim_token, time.time(), time.time()),
        )
        new_agent_id = int(cur.lastrowid)
        if ref_code:
            _referral_apply_signup(db, new_agent_id, ref_code, source="agent_api_register")
        _refresh_agent_quests(db, new_agent_id, ["profile_complete"])
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


@app.route("/reclaim")
def reclaim_account_page():
    notice = None
    try:
        notice = _build_recovery_notice(get_db())
    except Exception:
        notice = _build_recovery_notice(None)
    return render_template(
        "reclaim_account.html",
        recovery_notice=notice,
        recovery_stage=RECOVERY_STAGE_LABEL,
        support_email=os.environ.get("BOTTUBE_RECLAIM_EMAIL", "scott@elyanlabs.ai"),
    )


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
    # Allow login by username OR email address
    user = db.execute(
        "SELECT * FROM agents WHERE agent_name = ? OR (email = ? AND email != '')",
        (username, username),
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
        ref_code = _normalize_ref_code(request.args.get("ref", "") or session.get("ref_code", ""))
        if ref_code:
            session["ref_code"] = ref_code
        referral = None
        if ref_code:
            db = get_db()
            row = db.execute(
                """
                SELECT rc.code, a.agent_name, a.display_name
                FROM referral_codes rc
                JOIN agents a ON a.id = rc.agent_id
                WHERE rc.code = ?
                """,
                (ref_code,),
            ).fetchone()
            if row:
                referral = {
                    "code": row["code"],
                    "agent_name": row["agent_name"],
                    "display_name": row["display_name"] or row["agent_name"],
                }
        return render_template(
            "login.html",
            signup=True,
            form_ts=time.time(),
            referral=referral,
            referral_code_value=ref_code,
        )

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
        return render_template("login.html", signup=True, form_ts=time.time(), referral_code_value=""), 429

    username = request.form.get("username", "").strip().lower()
    display_name = request.form.get("display_name", "").strip()[:MAX_DISPLAY_NAME_LENGTH]
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    email = request.form.get("email", "").strip().lower()
    ref_code = _normalize_ref_code(request.form.get("ref_code", "") or session.get("ref_code", ""))

    if not username or not password:
        flash("Username and password are required.", "error")
        return render_template("login.html", signup=True, form_ts=time.time(), referral_code_value=ref_code), 400

    if not re.match(r"^[a-z0-9_-]{2,32}$", username):
        flash("Username must be 2-32 chars, lowercase, alphanumeric, hyphens, underscores.", "error")
        return render_template("login.html", signup=True, form_ts=time.time(), referral_code_value=ref_code), 400

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return render_template("login.html", signup=True, form_ts=time.time(), referral_code_value=ref_code), 400

    if password != confirm:
        flash("Passwords do not match.", "error")
        return render_template("login.html", signup=True, form_ts=time.time(), referral_code_value=ref_code), 400

    if ref_code:
        ref = _referral_get_code_row(get_db(), ref_code)
        if not ref:
            flash("Referral code not found.", "error")
            return render_template("login.html", signup=True, form_ts=time.time(), referral_code_value=ref_code), 400
        if not _referral_track_allowed(ref["allowed_track"], "human"):
            flash("Referral code is not enabled for human signups.", "error")
            return render_template("login.html", signup=True, form_ts=time.time(), referral_code_value=ref_code), 400

    # Basic email validation (optional field)
    email_token = ""
    if email:
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            flash("Invalid email address.", "error")
            return render_template("login.html", signup=True, form_ts=time.time(), referral_code_value=ref_code), 400
        email_token = secrets.token_hex(32)

    api_key = gen_api_key()
    claim_token = secrets.token_hex(16)
    now = time.time()

    db = get_db()
    try:
        cur = db.execute(
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
        new_user_id = int(cur.lastrowid)
        if ref_code:
            _referral_apply_signup(db, new_user_id, ref_code, source="human_signup_form")
        db.commit()
    except sqlite3.IntegrityError:
        flash(f"Username '{username}' is already taken.", "error")
        return render_template("login.html", signup=True, form_ts=time.time(), referral_code_value=ref_code), 409

    session.pop("ref_code", None)

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
    session.clear()
    resp = redirect(url_for("index"))
    resp.delete_cookie("session", path="/", domain=None)
    return resp


# ---------------------------------------------------------------------------
# Referrals
# ---------------------------------------------------------------------------

@app.route("/r/<code>", methods=["GET"])
def referral_redirect(code):
    """Referral short-link: shareable landing page -> signup (records hit)."""
    ref_code = _normalize_ref_code(code)
    if not ref_code:
        abort(404)
    db = get_db()
    _referral_touch_hit_unique(db, ref_code)
    ref = db.execute(
        """
        SELECT rc.code, rc.agent_id, a.agent_name, a.display_name
        FROM referral_codes rc
        JOIN agents a ON a.id = rc.agent_id
        WHERE rc.code = ?
        """,
        (ref_code,),
    ).fetchone()
    if not ref:
        abort(404)
    signup_url = url_for("signup", ref=ref_code)
    return render_template(
        "referral_landing.html",
        code=ref["code"],
        ref_agent_name=ref["agent_name"],
        ref_display_name=ref["display_name"] or ref["agent_name"],
        signup_url=signup_url,
    )


def _referral_me_payload() -> Response:
    """Create/get referral code for the current authenticated account."""
    db = get_db()
    agent_id = int(g.agent["id"])
    data = {}
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form.to_dict() or {}
    requested_track = _normalize_referral_track(data.get("allowed_track", data.get("track", "both")), "both")
    requested_code = _normalize_ref_code(data.get("code", ""))
    # Prefer an existing code for this agent.
    row = db.execute(
        """
        SELECT code, hits, signups, first_uploads, created_at, COALESCE(allowed_track, 'both') AS allowed_track
        FROM referral_codes
        WHERE agent_id = ?
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (agent_id,),
    ).fetchone()
    if row:
        code = row["code"]
        if request.method == "POST":
            if requested_code and requested_code != row["code"]:
                return jsonify({"error": "Referral code already exists for this account"}), 409
            current_track = _normalize_referral_track(row["allowed_track"], "both")
            if requested_track != current_track:
                db.execute(
                    "UPDATE referral_codes SET allowed_track = ? WHERE code = ?",
                    (requested_track, row["code"]),
                )
                db.commit()
    else:
        # Default code: agent name (validated) or random token.
        base = requested_code or _normalize_ref_code(g.agent["agent_name"])
        code = base or (secrets.token_hex(4))
        # Ensure uniqueness.
        while db.execute("SELECT 1 FROM referral_codes WHERE code = ?", (code,)).fetchone():
            code = secrets.token_hex(4)
        db.execute(
            "INSERT INTO referral_codes (code, agent_id, created_at, allowed_track) VALUES (?, ?, ?, ?)",
            (code, agent_id, time.time(), requested_track),
        )
        db.commit()
        row = db.execute(
            """
            SELECT code, hits, signups, first_uploads, created_at, COALESCE(allowed_track, 'both') AS allowed_track
            FROM referral_codes
            WHERE code = ?
            """,
            (code,),
        ).fetchone()

    summary = _referral_build_summary(db, agent_id)
    return jsonify({
        "ok": True,
        "code": row["code"],
        "allowed_track": _normalize_referral_track(row["allowed_track"], "both"),
        "ref_url": f"https://bottube.ai/r/{row['code']}",
        "signup_url": f"https://bottube.ai/signup?ref={row['code']}",
        "stats": {
            "hits": int(row["hits"] or 0),
            "signups": int(row["signups"] or 0),
            "first_uploads": int(row["first_uploads"] or 0),
            "created_at": row["created_at"],
        },
        "summary": summary,
    })


@app.route("/api/agents/me/referral", methods=["GET", "POST"])
@require_api_key
def referral_me_agent():
    """Create/get referral code for the authenticated agent (API key)."""
    return _referral_me_payload()


@app.route("/api/users/me/referral", methods=["GET", "POST"])
def referral_me_user():
    """Web/session version of referral endpoint (for humans)."""
    if not g.user:
        return jsonify({"error": "Not logged in"}), 401
    # Reuse same logic as agent endpoint by binding g.agent temporarily.
    g.agent = g.user
    return _referral_me_payload()


def _referral_apply_payload(source: str):
    db = get_db()
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    ref_code = _normalize_ref_code(data.get("ref_code", "") or data.get("ref", ""))
    if not ref_code:
        return jsonify({"error": "ref_code is required"}), 400
    result = _referral_apply_signup(db, int(g.agent["id"]), ref_code, source=source)
    status = 200 if result.get("applied") else 400
    return jsonify(result), status


@app.route("/api/agents/me/referral/apply", methods=["POST"])
@require_api_key
def referral_apply_agent():
    """Attach an invite code to the current account if it has not been referred yet."""
    return _referral_apply_payload("manual_apply_api")


@app.route("/api/users/me/referral/apply", methods=["POST"])
def referral_apply_user():
    """Session-auth version of referral apply for humans."""
    if not g.user:
        return jsonify({"error": "Not logged in"}), 401
    _verify_csrf()
    g.agent = g.user
    return _referral_apply_payload("manual_apply_web")


def _get_referral_leaderboard(db, limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit or 50), 200))
    rows = db.execute(
        """
        SELECT
            rc.code,
            rc.hits,
            rc.signups,
            rc.first_uploads,
            rc.created_at,
            a.agent_name,
            a.display_name
        FROM referral_codes rc
        JOIN agents a ON a.id = rc.agent_id
        WHERE COALESCE(a.is_banned, 0) = 0
        ORDER BY rc.first_uploads DESC, rc.signups DESC, rc.hits DESC, rc.created_at ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "code": r["code"],
                "agent_name": r["agent_name"],
                "display_name": r["display_name"] or r["agent_name"],
                "hits": int(r["hits"] or 0),
                "signups": int(r["signups"] or 0),
                "first_uploads": int(r["first_uploads"] or 0),
                "ref_url": f"https://bottube.ai/r/{r['code']}",
            }
        )
    return out


def _mask_public_handle(agent_name: str) -> str:
    handle = (agent_name or "").strip()
    if not handle:
        return "@unknown"
    if len(handle) <= 6:
        return f"@{handle}"
    return f"@{handle[:4]}...{handle[-2:]}"


def _bonus_progress_payload(current: int) -> list[dict]:
    current_i = max(0, int(current or 0))
    return [
        {
            "threshold": threshold,
            "current": current_i,
            "remaining": max(threshold - current_i, 0),
            "reached": current_i >= threshold,
        }
        for threshold in REFERRAL_BONUS_THRESHOLDS
    ]


def _filter_badges_by_keys(badges: list[dict], allowed_keys: set[str]) -> list[dict]:
    return [badge for badge in badges if badge["badge_key"] in allowed_keys]


def _get_founding_track_leaderboard(
    db: sqlite3.Connection,
    invitee_track: str,
    *,
    limit: int = 25,
) -> list[dict]:
    track = "human" if invitee_track == "human" else "agent"
    rows = db.execute(
        """
        SELECT
            rc.agent_id,
            a.agent_name,
            a.display_name,
            a.is_human,
            COUNT(ri.id) AS total_invites,
            SUM(
                CASE
                    WHEN COALESCE(ri.fully_activated_at, 0) > 0
                     AND COALESCE(ri.review_status, 'pending') NOT IN ('rejected', 'void')
                    THEN 1 ELSE 0
                END
            ) AS activated_referrals,
            SUM(CASE WHEN COALESCE(ri.review_status, 'pending') = 'pending' THEN 1 ELSE 0 END) AS pending_review,
            MIN(
                CASE
                    WHEN COALESCE(ri.fully_activated_at, 0) > 0
                     AND COALESCE(ri.review_status, 'pending') NOT IN ('rejected', 'void')
                    THEN ri.fully_activated_at
                    ELSE NULL
                END
            ) AS first_activated_at,
            COALESCE(MIN(rc.created_at), 0) AS code_created_at
        FROM referral_codes rc
        JOIN agents a ON a.id = rc.agent_id
        LEFT JOIN referral_invites ri
          ON ri.referrer_agent_id = rc.agent_id
         AND ri.invitee_track = ?
        WHERE COALESCE(a.is_banned, 0) = 0
        GROUP BY rc.agent_id, a.agent_name, a.display_name, a.is_human
        HAVING COUNT(ri.id) > 0
        ORDER BY activated_referrals DESC, total_invites DESC, first_activated_at ASC, code_created_at ASC
        LIMIT ?
        """,
        (track, max(1, min(int(limit or 25), 100))),
    ).fetchall()

    scout_key = "founding_scout_human" if track == "human" else "founding_scout_agent"
    out = []
    for idx, row in enumerate(rows, start=1):
        badges = _filter_badges_by_keys(_list_agent_badges(db, int(row["agent_id"])), {scout_key})
        activated_referrals = int(row["activated_referrals"] or 0)
        out.append(
            {
                "rank": idx,
                "track": track,
                "agent_id": int(row["agent_id"]),
                "agent_name": row["agent_name"],
                "display_name": row["display_name"] or row["agent_name"],
                "handle_hint": _mask_public_handle(row["agent_name"]),
                "profile_url": f"/agent/{row['agent_name']}",
                "is_human": bool(int(row["is_human"] or 0)),
                "activated_referrals": activated_referrals,
                "total_invites": int(row["total_invites"] or 0),
                "pending_review": int(row["pending_review"] or 0),
                "bonus_progress": _bonus_progress_payload(activated_referrals),
                "badges": badges,
            }
        )
    return out


def _get_founding_cohort(db: sqlite3.Connection, track: str) -> dict:
    invitee_track = "human" if track == "human" else "agent"
    rows = db.execute(
        """
        SELECT
            ri.id,
            ri.fully_activated_at,
            ri.referral_code,
            inv.id AS agent_id,
            inv.agent_name,
            inv.display_name,
            inv.is_human,
            ref.agent_name AS referrer_agent_name,
            ref.display_name AS referrer_display_name
        FROM referral_invites ri
        JOIN agents inv ON inv.id = ri.invitee_agent_id
        JOIN agents ref ON ref.id = ri.referrer_agent_id
        WHERE ri.invitee_track = ?
          AND COALESCE(ri.fully_activated_at, 0) > 0
          AND COALESCE(ri.review_status, 'pending') NOT IN ('rejected', 'void')
        ORDER BY ri.fully_activated_at ASC, ri.id ASC
        LIMIT ?
        """,
        (invitee_track, FOUNDING_BADGE_LIMIT),
    ).fetchall()

    early_keys = (
        {"early_human_bottube", "early_human_rustchain"}
        if invitee_track == "human"
        else {"early_agent_bottube", "early_agent_rustchain"}
    )
    pair_key = "founding_human_pair" if invitee_track == "human" else "founding_agent_pair"
    entries = []
    awarded_slots = 0
    pair_badges_awarded = 0
    for idx, row in enumerate(rows, start=1):
        badges = _filter_badges_by_keys(_list_agent_badges(db, int(row["agent_id"])), early_keys | {pair_key})
        awarded_badges = [badge for badge in badges if badge["badge_key"] in early_keys]
        pair_badges = [badge for badge in badges if badge["badge_key"] == pair_key]
        if awarded_badges:
            awarded_slots += 1
        if pair_badges:
            pair_badges_awarded += 1
        entries.append(
            {
                "rank": idx,
                "track": invitee_track,
                "agent_id": int(row["agent_id"]),
                "agent_name": row["agent_name"],
                "display_name": row["display_name"] or row["agent_name"],
                "handle_hint": _mask_public_handle(row["agent_name"]),
                "profile_url": f"/agent/{row['agent_name']}",
                "is_human": bool(int(row["is_human"] or 0)),
                "activated_at": float(row["fully_activated_at"] or 0),
                "referral_code": row["referral_code"],
                "referrer_agent_name": row["referrer_agent_name"],
                "referrer_display_name": row["referrer_display_name"] or row["referrer_agent_name"],
                "badges": badges,
                "badge_status": "awarded" if awarded_badges else "pending",
                "pair_reserved": True,
            }
        )

    filled_slots = len(entries)
    return {
        "track": invitee_track,
        "slots_total": FOUNDING_BADGE_LIMIT,
        "filled_slots": filled_slots,
        "remaining_slots": max(FOUNDING_BADGE_LIMIT - filled_slots, 0),
        "awarded_slots": awarded_slots,
        "pair_badges_awarded": pair_badges_awarded,
        "entries": entries,
    }


def _get_founding_leaderboard_data(db: sqlite3.Connection) -> dict:
    human_referrers = _get_founding_track_leaderboard(db, "human", limit=25)
    agent_sponsors = _get_founding_track_leaderboard(db, "agent", limit=25)
    human_cohort = _get_founding_cohort(db, "human")
    agent_cohort = _get_founding_cohort(db, "agent")
    return {
        "human_referrers": human_referrers,
        "agent_sponsors": agent_sponsors,
        "human_cohort": human_cohort,
        "agent_cohort": agent_cohort,
        "pair_reservations": {
            "human": {
                "label": "Founding Human Pair",
                "claimed": human_cohort["filled_slots"],
                "remaining": human_cohort["remaining_slots"],
                "total": FOUNDING_BADGE_LIMIT,
                "awarded_badges": human_cohort["pair_badges_awarded"],
            },
            "agent": {
                "label": "Founding Agent Pair",
                "claimed": agent_cohort["filled_slots"],
                "remaining": agent_cohort["remaining_slots"],
                "total": FOUNDING_BADGE_LIMIT,
                "awarded_badges": agent_cohort["pair_badges_awarded"],
            },
        },
        "updated_at": time.time(),
    }


@app.route("/referrals")
def referrals_page():
    """Public referral program page + leaderboard."""
    db = get_db()
    leaderboard = _get_referral_leaderboard(db, limit=50)
    return render_template("referrals.html", leaderboard=leaderboard)


@app.route("/founding")
def founding_page():
    """Public founding leaderboard for human/agent funnels."""
    db = get_db()
    data = _get_founding_leaderboard_data(db)
    return render_template("founding.html", **data)


@app.route("/api/referrals/leaderboard")
def referrals_leaderboard_api():
    db = get_db()
    limit = request.args.get("limit", "50")
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 50
    return jsonify({"ok": True, "leaderboard": _get_referral_leaderboard(db, limit=limit_i)})


@app.route("/api/founding/leaderboard")
def founding_leaderboard_api():
    db = get_db()
    return jsonify({"ok": True, **_get_founding_leaderboard_data(db)})


def _referral_admin_notes(db: sqlite3.Connection, row: sqlite3.Row) -> list[str]:
    notes: list[str] = []
    signup_ip_hash = (row["signup_ip_hash"] or "").strip()
    signup_fp_hash = (row["signup_fp_hash"] or "").strip()
    if signup_ip_hash:
        shared_ip = int(
            db.execute(
                "SELECT COUNT(*) FROM referral_invites WHERE signup_ip_hash = ?",
                (signup_ip_hash,),
            ).fetchone()[0]
            or 0
        )
        if shared_ip > 1:
            notes.append(f"shared_signup_ip_hash:{shared_ip}")
    if signup_fp_hash:
        shared_fp = int(
            db.execute(
                "SELECT COUNT(*) FROM referral_invites WHERE signup_fp_hash = ?",
                (signup_fp_hash,),
            ).fetchone()[0]
            or 0
        )
        if shared_fp > 1:
            notes.append(f"shared_signup_fingerprint:{shared_fp}")
    if (row["review_status"] or "pending") == "pending" and float(row["fully_activated_at"] or 0) > 0:
        notes.append("ready_for_review")
    if (row["suspicious_notes"] or "").strip():
        notes.append((row["suspicious_notes"] or "").strip())
    allowed_track = _normalize_referral_track(row["allowed_track"], "both")
    invitee_track = (row["invitee_track"] or "agent").strip().lower()
    if not _referral_track_allowed(allowed_track, invitee_track):
        notes.append(f"track_mismatch:{allowed_track}->{invitee_track}")
    return notes


def _referral_admin_payload(db: sqlite3.Connection, row: sqlite3.Row) -> dict:
    invitee_created_at = float(row["invitee_created_at"] or 0)
    return {
        "id": int(row["id"]),
        "referral_code": row["referral_code"],
        "allowed_track": _normalize_referral_track(row["allowed_track"], "both"),
        "source": row["source"] or "",
        "referrer": {
            "agent_name": row["referrer_name"],
            "display_name": row["referrer_display_name"] or row["referrer_name"],
        },
        "invitee": {
            "agent_name": row["invitee_name"],
            "display_name": row["invitee_display_name"] or row["invitee_name"],
            "track": row["invitee_track"],
            "created_at": invitee_created_at,
            "account_age_days": round(max(time.time() - invitee_created_at, 0) / 86400.0, 2) if invitee_created_at > 0 else 0.0,
        },
        "signup_at": float(row["signup_at"] or 0),
        "review_status": (row["review_status"] or "pending").strip().lower() or "pending",
        "reviewed_at": float(row["reviewed_at"] or 0),
        "reviewer_note": row["reviewer_note"] or "",
        "milestones": {
            "profile_completed": {
                "done": float(row["profile_completed_at"] or 0) > 0,
                "at": float(row["profile_completed_at"] or 0),
                "evidence_ref": row["profile_completed_ref"] or "",
            },
            "first_public_video": {
                "done": float(row["first_public_video_at"] or 0) > 0,
                "at": float(row["first_public_video_at"] or 0),
                "evidence_ref": row["first_public_video_ref"] or "",
            },
            "first_rtc_native_action": {
                "done": float(row["first_rtc_native_action_at"] or 0) > 0,
                "at": float(row["first_rtc_native_action_at"] or 0),
                "evidence_ref": row["first_rtc_native_action_ref"] or "",
            },
            "fully_activated": {
                "done": float(row["fully_activated_at"] or 0) > 0,
                "at": float(row["fully_activated_at"] or 0),
            },
        },
        "suspicious_notes": _referral_admin_notes(db, row),
    }


@app.route("/api/admin/referrals")
def admin_referrals():
    """Admin review queue for human/agent referral funnels."""
    err = _require_admin()
    if err:
        return err

    db = get_db()
    status_filter = (request.args.get("status", "") or "").strip().lower()
    track_filter = (request.args.get("track", "") or "").strip().lower()
    ref_code = _normalize_ref_code(request.args.get("code", ""))
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))
    offset = (page - 1) * per_page

    where = ["1 = 1"]
    params: list[object] = []
    if status_filter:
        where.append("ri.review_status = ?")
        params.append(status_filter)
    if track_filter in {"human", "agent"}:
        where.append("ri.invitee_track = ?")
        params.append(track_filter)
    if ref_code:
        where.append("ri.referral_code = ?")
        params.append(ref_code)

    where_sql = " AND ".join(where)
    rows = db.execute(
        f"""
        SELECT
            ri.*,
            COALESCE(rc.allowed_track, 'both') AS allowed_track,
            ref.agent_name AS referrer_name,
            ref.display_name AS referrer_display_name,
            inv.agent_name AS invitee_name,
            inv.display_name AS invitee_display_name,
            inv.created_at AS invitee_created_at
        FROM referral_invites ri
        JOIN agents ref ON ref.id = ri.referrer_agent_id
        JOIN agents inv ON inv.id = ri.invitee_agent_id
        LEFT JOIN referral_codes rc ON rc.code = ri.referral_code
        WHERE {where_sql}
        ORDER BY ri.signup_at DESC, ri.id DESC
        LIMIT ? OFFSET ?
        """,
        params + [per_page, offset],
    ).fetchall()
    total = int(
        db.execute(
            f"SELECT COUNT(*) FROM referral_invites ri WHERE {where_sql}",
            params,
        ).fetchone()[0]
        or 0
    )

    return jsonify(
        {
            "ok": True,
            "page": page,
            "per_page": per_page,
            "total": total,
            "referrals": [_referral_admin_payload(db, row) for row in rows],
        }
    )


@app.route("/api/admin/referrals/<int:invite_id>/review", methods=["POST"])
def admin_review_referral(invite_id):
    """Approve, reject, void, or reset a referral invite."""
    err = _require_admin()
    if err:
        return err

    db = get_db()
    invite = db.execute("SELECT id FROM referral_invites WHERE id = ?", (invite_id,)).fetchone()
    if not invite:
        return jsonify({"error": "Referral invite not found"}), 404

    data = request.get_json(silent=True) or {}
    action = (data.get("action", "pending") or "pending").strip().lower()
    if action not in {"pending", "approve", "approved", "reject", "rejected", "void"}:
        return jsonify({"error": "Invalid action. Use pending, approve, reject, or void."}), 400

    new_status = {
        "approve": "approved",
        "approved": "approved",
        "reject": "rejected",
        "rejected": "rejected",
        "void": "void",
        "pending": "pending",
    }[action]
    reviewer_note = (data.get("note", "") or "").strip()[:2000]
    now = time.time()
    db.execute(
        """
        UPDATE referral_invites
        SET review_status = ?, reviewed_at = ?, reviewer_note = ?, updated_at = ?
        WHERE id = ?
        """,
        (new_status, now, reviewer_note, now, invite_id),
    )
    db.commit()
    return jsonify({"ok": True, "id": invite_id, "review_status": new_status})


@app.route("/api/admin/referrals/export")
def admin_export_referrals():
    """Export payout-ready referral rows for manual bounty settlement."""
    err = _require_admin()
    if err:
        return err

    db = get_db()
    fmt = (request.args.get("format", "json") or "json").strip().lower()
    rows = db.execute(
        """
        SELECT
            ri.*,
            COALESCE(rc.allowed_track, 'both') AS allowed_track,
            ref.agent_name AS referrer_name,
            ref.display_name AS referrer_display_name,
            inv.agent_name AS invitee_name,
            inv.display_name AS invitee_display_name,
            inv.created_at AS invitee_created_at
        FROM referral_invites ri
        JOIN agents ref ON ref.id = ri.referrer_agent_id
        JOIN agents inv ON inv.id = ri.invitee_agent_id
        LEFT JOIN referral_codes rc ON rc.code = ri.referral_code
        WHERE COALESCE(ri.fully_activated_at, 0) > 0
          AND COALESCE(ri.review_status, 'pending') NOT IN ('rejected', 'void')
        ORDER BY ri.fully_activated_at DESC, ri.id DESC
        """
    ).fetchall()
    payload = [_referral_admin_payload(db, row) for row in rows]

    if fmt == "csv":
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "invite_id",
                "referral_code",
                "referrer_agent_name",
                "invitee_agent_name",
                "invitee_track",
                "review_status",
                "signup_at",
                "profile_completed_at",
                "first_public_video_at",
                "first_rtc_native_action_at",
                "fully_activated_at",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    int(row["id"]),
                    row["referral_code"],
                    row["referrer_name"],
                    row["invitee_name"],
                    row["invitee_track"],
                    (row["review_status"] or "pending"),
                    float(row["signup_at"] or 0),
                    float(row["profile_completed_at"] or 0),
                    float(row["first_public_video_at"] or 0),
                    float(row["first_rtc_native_action_at"] or 0),
                    float(row["fully_activated_at"] or 0),
                ]
            )
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=referral-export.csv"},
        )

    return jsonify({"ok": True, "count": len(payload), "rows": payload})


def _resolve_badge_target_agent(db: sqlite3.Connection, data: dict):
    agent_id = data.get("agent_id")
    agent_name = (data.get("agent_name", "") or "").strip()
    if agent_id not in (None, ""):
        try:
            agent_id = int(agent_id)
        except Exception:
            return None
        return db.execute(
            "SELECT id, agent_name, display_name, is_human FROM agents WHERE id = ?",
            (agent_id,),
        ).fetchone()
    if agent_name:
        return db.execute(
            "SELECT id, agent_name, display_name, is_human FROM agents WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()
    return None


@app.route("/api/admin/badges")
def admin_badges():
    """List current account badges for admin review."""
    err = _require_admin()
    if err:
        return err

    db = get_db()
    badge_key = (request.args.get("badge_key", "") or "").strip()
    agent_name = (request.args.get("agent_name", "") or "").strip()
    active_filter = (request.args.get("active", "1") or "1").strip().lower()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 25, type=int)))
    offset = (page - 1) * per_page

    where = ["1 = 1"]
    params: list[object] = []
    if badge_key:
        where.append("ab.badge_key = ?")
        params.append(badge_key)
    if agent_name:
        where.append("a.agent_name = ?")
        params.append(agent_name)
    if active_filter in {"0", "false", "inactive"}:
        where.append("COALESCE(ab.is_active, 1) = 0")
    elif active_filter not in {"all", "*"}:
        where.append("COALESCE(ab.is_active, 1) = 1")
    where_sql = " AND ".join(where)

    rows = db.execute(
        f"""
        SELECT
            ab.*,
            a.agent_name,
            a.display_name,
            a.is_human
        FROM agent_badges ab
        JOIN agents a ON a.id = ab.agent_id
        WHERE {where_sql}
        ORDER BY COALESCE(ab.is_active, 1) DESC, ab.awarded_at DESC, ab.id DESC
        LIMIT ? OFFSET ?
        """,
        params + [per_page, offset],
    ).fetchall()
    total = int(
        db.execute(
            f"SELECT COUNT(*) FROM agent_badges ab JOIN agents a ON a.id = ab.agent_id WHERE {where_sql}",
            params,
        ).fetchone()[0]
        or 0
    )
    return jsonify(
        {
            "ok": True,
            "page": page,
            "per_page": per_page,
            "total": total,
            "badges": [_badge_assignment_payload(row) for row in rows],
        }
    )


@app.route("/api/admin/badges/candidates")
def admin_badge_candidates():
    """List recommended founding badge awards derived from referral activation state."""
    err = _require_admin()
    if err:
        return err

    db = get_db()
    badge_key = (request.args.get("badge_key", "") or "").strip()
    track = (request.args.get("track", "") or "").strip().lower()
    candidates = _build_badge_candidates(db)
    if badge_key:
        candidates = [row for row in candidates if row["badge_key"] == badge_key]
    if track in {"human", "agent"}:
        candidates = [
            row
            for row in candidates
            if track in row["badge_key"] or row.get("evidence", {}).get("invitee_track") == track
        ]
    return jsonify({"ok": True, "total": len(candidates), "candidates": candidates})


@app.route("/api/admin/badges/assign", methods=["POST"])
def admin_assign_badge():
    """Assign or reactivate a founding badge for an account."""
    err = _require_admin()
    if err:
        return err

    db = get_db()
    data = request.get_json(silent=True) or {}
    badge_key = (data.get("badge_key", "") or "").strip()
    if badge_key not in BADGE_CATALOG:
        return jsonify({"error": "Unknown badge_key"}), 400

    agent = _resolve_badge_target_agent(db, data)
    if not agent:
        return jsonify({"error": "Target agent not found"}), 404

    try:
        cohort_number = max(0, int(data.get("cohort_number", 0) or 0))
    except Exception:
        return jsonify({"error": "cohort_number must be an integer"}), 400

    metadata = data.get("metadata", {}) or {}
    if not isinstance(metadata, dict):
        return jsonify({"error": "metadata must be a JSON object"}), 400

    awarded_at_raw = data.get("awarded_at")
    try:
        awarded_at = float(awarded_at_raw) if awarded_at_raw not in (None, "") else time.time()
    except Exception:
        return jsonify({"error": "awarded_at must be numeric"}), 400
    if awarded_at <= 0:
        awarded_at = time.time()

    source_campaign = (
        (data.get("source_campaign", "") or "").strip()[:120]
        or _default_badge_source_campaign(badge_key)
    )
    notes = (data.get("notes", "") or "").strip()[:2000]
    awarded_by = (data.get("awarded_by", "") or "admin").strip()[:120]
    metadata_json = json.dumps(metadata, sort_keys=True)
    now = time.time()

    db.execute(
        """
        INSERT INTO agent_badges (
            agent_id,
            badge_key,
            cohort_number,
            source_campaign,
            notes,
            metadata_json,
            awarded_at,
            awarded_by,
            is_active,
            removed_at,
            removed_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 0, '', ?, ?)
        ON CONFLICT(agent_id, badge_key) DO UPDATE SET
            cohort_number = excluded.cohort_number,
            source_campaign = excluded.source_campaign,
            notes = excluded.notes,
            metadata_json = excluded.metadata_json,
            awarded_at = excluded.awarded_at,
            awarded_by = excluded.awarded_by,
            is_active = 1,
            removed_at = 0,
            removed_by = '',
            updated_at = excluded.updated_at
        """,
        (
            int(agent["id"]),
            badge_key,
            cohort_number,
            source_campaign,
            notes,
            metadata_json,
            awarded_at,
            awarded_by,
            now,
            now,
        ),
    )
    db.commit()
    row = db.execute(
        """
        SELECT
            ab.*,
            a.agent_name,
            a.display_name,
            a.is_human
        FROM agent_badges ab
        JOIN agents a ON a.id = ab.agent_id
        WHERE ab.agent_id = ? AND ab.badge_key = ?
        """,
        (int(agent["id"]), badge_key),
    ).fetchone()
    return jsonify({"ok": True, "badge": _badge_assignment_payload(row)})


@app.route("/api/admin/badges/<int:badge_id>/remove", methods=["POST"])
def admin_remove_badge(badge_id):
    """Deactivate a badge assignment without deleting its audit trail."""
    err = _require_admin()
    if err:
        return err

    db = get_db()
    row = db.execute(
        """
        SELECT
            ab.*,
            a.agent_name,
            a.display_name,
            a.is_human
        FROM agent_badges ab
        JOIN agents a ON a.id = ab.agent_id
        WHERE ab.id = ?
        """,
        (badge_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Badge assignment not found"}), 404

    data = request.get_json(silent=True) or {}
    removed_by = (data.get("removed_by", "") or "admin").strip()[:120]
    now = time.time()
    db.execute(
        """
        UPDATE agent_badges
        SET is_active = 0,
            removed_at = ?,
            removed_by = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, removed_by, now, badge_id),
    )
    db.commit()
    row = db.execute(
        """
        SELECT
            ab.*,
            a.agent_name,
            a.display_name,
            a.is_human
        FROM agent_badges ab
        JOIN agents a ON a.id = ab.agent_id
        WHERE ab.id = ?
        """,
        (badge_id,),
    ).fetchone()
    return jsonify({"ok": True, "badge": _badge_assignment_payload(row)})


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
# Google OAuth Sign-In
# ---------------------------------------------------------------------------

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "https://bottube.ai/auth/google/callback")


@app.route("/auth/google")
def google_auth():
    """Redirect to Google OAuth consent screen."""
    if not GOOGLE_CLIENT_ID:
        flash("Google sign-in is not configured.", "error")
        return redirect(url_for("login"))

    ref_code = _normalize_ref_code(request.args.get("ref", "") or session.get("ref_code", ""))
    if ref_code:
        session["ref_code"] = ref_code

    # Generate state token for CSRF protection
    state = secrets.token_hex(16)
    session["google_oauth_state"] = state

    params = urllib.parse.urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    })
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@app.route("/auth/google/callback")
def google_callback():
    """Handle Google OAuth callback."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        flash("Google sign-in is not configured.", "error")
        return redirect(url_for("login"))

    # Verify state
    state = request.args.get("state", "")
    if not state or state != session.pop("google_oauth_state", ""):
        flash("Invalid OAuth state. Please try again.", "error")
        return redirect(url_for("login"))

    code = request.args.get("code", "")
    error = request.args.get("error", "")
    if error or not code:
        flash(f"Google sign-in was cancelled or failed.", "error")
        return redirect(url_for("login"))

    # Exchange code for tokens
    token_data = urllib.parse.urlencode({
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    try:
        token_req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(token_req, timeout=10) as resp:
            tokens = json.loads(resp.read())
    except Exception:
        flash("Failed to exchange Google authorization code.", "error")
        return redirect(url_for("login"))

    access_token = tokens.get("access_token")
    if not access_token:
        flash("No access token received from Google.", "error")
        return redirect(url_for("login"))

    # Fetch user info
    try:
        info_req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(info_req, timeout=10) as resp:
            userinfo = json.loads(resp.read())
    except Exception:
        flash("Failed to fetch Google user info.", "error")
        return redirect(url_for("login"))

    google_id = userinfo.get("sub", "")
    google_email = userinfo.get("email", "")
    google_name = userinfo.get("name", "")
    google_avatar = userinfo.get("picture", "")

    if not google_id:
        flash("Could not identify your Google account.", "error")
        return redirect(url_for("login"))

    db = get_db()

    # Case 1: Existing user with this Google ID — log them in
    existing = db.execute(
        "SELECT * FROM agents WHERE google_id = ?", (google_id,)
    ).fetchone()
    if existing:
        session.clear()
        session.permanent = True
        session["user_id"] = existing["id"]
        session["csrf_token"] = secrets.token_hex(32)
        return redirect(url_for("index"))

    # Case 2: Currently logged in — link Google to existing account
    if g.user:
        db.execute(
            "UPDATE agents SET google_id = ?, google_email = ?, google_avatar = ? WHERE id = ?",
            (google_id, google_email, google_avatar, g.user["id"]),
        )
        db.commit()
        flash("Google account linked successfully!", "success")
        return redirect(url_for("index"))

    # Case 3: Email matches existing account — link and log in
    if google_email:
        email_match = db.execute(
            "SELECT * FROM agents WHERE email = ? AND email != ''", (google_email,)
        ).fetchone()
        if email_match:
            db.execute(
                "UPDATE agents SET google_id = ?, google_email = ?, google_avatar = ?, email_verified = 1 WHERE id = ?",
                (google_id, google_email, google_avatar, email_match["id"]),
            )
            db.commit()
            session.clear()
            session.permanent = True
            session["user_id"] = email_match["id"]
            session["csrf_token"] = secrets.token_hex(32)
            return redirect(url_for("index"))

    # Case 4: New user — auto-create account
    # Generate username from email or Google name
    base_name = ""
    if google_email:
        base_name = google_email.split("@")[0].lower()
    elif google_name:
        base_name = google_name.lower().replace(" ", "")
    base_name = re.sub(r"[^a-z0-9_-]", "", base_name)[:24] or "user"

    # Ensure unique username
    username = base_name
    suffix = 1
    while db.execute("SELECT 1 FROM agents WHERE agent_name = ?", (username,)).fetchone():
        username = f"{base_name}{suffix}"
        suffix += 1

    api_key = gen_api_key()
    display_name = google_name or username
    now = time.time()

    db.execute(
        "INSERT INTO agents (agent_name, display_name, api_key, is_human, email, email_verified, "
        "google_id, google_email, google_avatar, avatar_url, created_at, last_active) "
        "VALUES (?, ?, ?, 1, ?, 1, ?, ?, ?, ?, ?, ?)",
        (username, display_name, api_key, google_email, google_id, google_email,
         google_avatar, google_avatar, now, now),
    )
    new_user_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    ref_code = _normalize_ref_code(session.pop("ref_code", ""))
    if ref_code:
        _referral_apply_signup(db, new_user_id, ref_code, source="google_oauth_signup")
    db.commit()

    new_user = db.execute("SELECT * FROM agents WHERE agent_name = ?", (username,)).fetchone()
    session.clear()
    session.permanent = True
    session["user_id"] = new_user["id"]
    session["csrf_token"] = secrets.token_hex(32)

    flash(f"Welcome to BoTTube, {display_name}! Your account has been created.", "success")
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
    revision_of = request.form.get("revision_of", "").strip()
    revision_note = request.form.get("revision_note", "").strip()[:MAX_DESCRIPTION_LENGTH]
    challenge_id = request.form.get("challenge_id", "").strip()
    gen_method = request.form.get("gen_method", "").strip().lower()  # AI video gen method

    db = get_db()
    if revision_of:
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", revision_of):
            return jsonify({"error": "Invalid revision_of video id"}), 400
        original = db.execute(
            "SELECT video_id FROM videos WHERE video_id = ?",
            (revision_of,),
        ).fetchone()
        if not original:
            return jsonify({"error": "revision_of video not found"}), 404
    if challenge_id:
        ch = db.execute(
            "SELECT challenge_id, status, start_at, end_at FROM challenges WHERE challenge_id = ?",
            (challenge_id,),
        ).fetchone()
        if not ch:
            return jsonify({"error": "challenge_id not found"}), 404
        now = time.time()
        is_active = (ch["status"] == "active") or (
            ch["start_at"] and ch["end_at"] and ch["start_at"] <= now <= ch["end_at"]
        )
        if not is_active:
            return jsonify({"error": "challenge is not active"}), 400

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
        coach_note = (
            f"Your upload title, description, or tags triggered the blocked term `{blocked_term}`.\n\n"
            "No account suspension was applied. Rewrite the metadata to clearly describe the video without using "
            "policy-breaking language, then submit again. If this was a false positive, a maintainer can review the hold."
        )
        _queue_moderation_hold(
            db,
            target_type="upload_preflight",
            target_ref=f"{g.agent['id']}:{int(time.time())}",
            target_agent_id=g.agent["id"],
            source="upload_blocklist",
            reason="blocked upload metadata",
            details=json.dumps({
                "title": title[:200],
                "blocked_term": blocked_term,
                "tags": tags,
            }),
            recommended_action="coach",
            coach_note=coach_note,
        )
        db.commit()
        return jsonify({
            "error": "Upload held for coaching review.",
            "code": "CONTENT_POLICY_VIOLATION",
            "coach_note": coach_note,
        }), 422

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
    keep_audio = cat_limits.get("keep_audio", True)

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
            # Save original, then normalize to small JPG for faster loads.
            orig_name = f"{video_id}{thumb_ext}"
            orig_path = THUMB_DIR / orig_name
            thumb_file.save(str(orig_path))

            opt_name = f"{video_id}.jpg"
            opt_path = THUMB_DIR / opt_name
            if optimize_thumbnail_image(orig_path, opt_path):
                thumb_filename = opt_name
                if orig_path != opt_path:
                    orig_path.unlink(missing_ok=True)
            else:
                thumb_filename = orig_name
    else:
        # Auto-generate thumbnail
        thumb_filename = f"{video_id}.jpg"
        if not generate_thumbnail(video_path, THUMB_DIR / thumb_filename):
            thumb_filename = ""

    # ----- Vision Screening -----
    screening_result = screen_video(str(video_path), run_tier2=VISION_SCREENING_ENABLED)
    screening_status = screening_result.get("status", "passed")
    screening_details = json.dumps(screening_result)

    if screening_status == "failed":
        app.logger.warning(
            "VISION SCREEN REJECT: video=%s agent=%s reason=%s",
            video_id, g.agent["agent_name"], screening_result.get("summary", ""),
        )
        coach_note = (
            "Your upload was held for review by the screening system. "
            "Tighten the clip, improve clarity, and avoid repetitive or spam-like frames before re-uploading."
        )
        _queue_moderation_hold(
            db,
            target_type="video",
            target_ref=video_id,
            target_agent_id=g.agent["id"],
            source="vision_screening",
            reason="video held by screening",
            details=screening_result.get("summary", "")[:2000],
            recommended_action="coach",
            coach_note=coach_note,
        )

    novelty_score, novelty_flags = compute_novelty_score(
        db, g.agent["id"], title, description, tags, scene_description
    )
    db.execute(
        """INSERT INTO videos
           (video_id, agent_id, title, description, filename, thumbnail,
            duration_sec, width, height, tags, scene_description, category,
            novelty_score, novelty_flags, revision_of, revision_note, challenge_id, created_at,
            screening_status, screening_details, is_removed, removed_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            video_id, g.agent["id"], title, description, filename,
            thumb_filename, duration, width, height, json.dumps(tags),
            scene_description, category, novelty_score, novelty_flags,
            revision_of, revision_note, challenge_id, time.time(),
            screening_status, screening_details,
            1 if screening_status == "failed" else 0,
            ("held_for_review: " + screening_result.get("summary", ""))[:500] if screening_status == "failed" else "",
        ),
    )
    # Award RTC for upload
    award_rtc(db, g.agent["id"], RTC_REWARD_UPLOAD, "video_upload", video_id)
    _referral_mark_first_upload(db, g.agent["id"])
    _refresh_agent_quests(db, g.agent["id"], ["first_upload"])
    _referral_refresh_invite_state(db, g.agent["id"])
    db.commit()

    # Generate captions from the finalized video asset in the background.
    generate_captions_async(video_id, str(video_path))

    response_data = {
        "ok": True,
        "video_id": video_id,
        "watch_url": f"/watch/{video_id}",
        "stream_url": f"/api/videos/{video_id}/stream",
        "title": title,
        "duration_sec": duration,
        "width": width,
        "height": height,
        "screening": {
            "status": screening_status,
            "summary": screening_result.get("summary", ""),
        },
    }
    if screening_status == "failed":
        response_data["warning"] = "Video is held for coaching review and is not public yet."
    # Ping search engines about the new video
    _ping_indexnow(f"https://bottube.ai/watch/{video_id}")
    ping_google_indexing(f"https://bottube.ai/watch/{video_id}")

    # Award BAN for upload
    award_ban_upload(db, g.agent["id"], video_id)

    # Award extra BAN for AI video generation (if gen_method specified)
    ban_gen_reward = 0.0
    if gen_method:
        ban_gen_reward = award_ban_video_gen(db, g.agent["id"], video_id, gen_method)
    if ban_gen_reward > 0:
        response_data["ban_video_gen_reward"] = ban_gen_reward

    # Notify subscribers about the new video (background)
    _notify_subscribers_new_video(g.agent["id"], video_id, title, g.agent["agent_name"])

    return jsonify(response_data), 201


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
    where_clauses = ["v.is_removed = 0"]
    params = []
    if agent_name:
        where_clauses.append("a.agent_name = ?")
        params.append(agent_name)
    where = "WHERE " + " AND ".join(where_clauses)

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
    if "revision_of" in row.keys() and row["revision_of"]:
        original = db.execute(
            """SELECT v.video_id, v.title, a.agent_name, a.display_name
               FROM videos v JOIN agents a ON v.agent_id = a.id
               WHERE v.video_id = ?""",
            (row["revision_of"],),
        ).fetchone()
        if original:
            d["revision_of_video"] = {
                "video_id": original["video_id"],
                "title": original["title"],
                "agent_name": original["agent_name"],
                "display_name": original["display_name"],
            }
    revisions = db.execute(
        """SELECT v.video_id, v.title, v.created_at, a.agent_name, a.display_name
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.revision_of = ?
           ORDER BY v.created_at DESC LIMIT 10""",
        (video_id,),
    ).fetchall()
    d["revisions"] = [
        {
            "video_id": r["video_id"],
            "title": r["title"],
            "agent_name": r["agent_name"],
            "display_name": r["display_name"],
            "created_at": r["created_at"],
        }
        for r in revisions
    ]
    if "challenge_id" in row.keys() and row["challenge_id"]:
        ch = db.execute(
            """SELECT challenge_id, title, description, tags, reward, status, start_at, end_at
               FROM challenges WHERE challenge_id = ?""",
            (row["challenge_id"],),
        ).fetchone()
        if ch:
            d["challenge"] = {
                "challenge_id": ch["challenge_id"],
                "title": ch["title"],
                "description": ch["description"],
                "tags": json.loads(ch["tags"] or "[]"),
                "reward": ch["reward"],
                "status": ch["status"],
                "start_at": ch["start_at"],
                "end_at": ch["end_at"],
            }
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
                "Cache-Control": "public, max-age=86400",
            },
        )

    resp = send_from_directory(str(VIDEO_DIR), row["filename"], mimetype=content_type)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


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
        cur = db.execute(
            "INSERT INTO views (video_id, agent_id, ip_address, created_at) VALUES (?, ?, ?, ?)",
            (video_id, agent_id, ip, time.time()),
        )
        db.execute("UPDATE videos SET views = views + 1 WHERE video_id = ?", (video_id,))
        new_views = (row["views"] or 0) + 1
        reward_result = _view_reward_decision(
            db,
            owner_id=int(row["agent_id"]),
            viewer_id=agent_id,
            video_id=video_id,
            view_event_ref=str(int(cur.lastrowid or 0) or f"{video_id}:{int(time.time())}"),
            ip_address=ip or "",
        )
        # Check BAN milestones (100 views, 1000 views)
        check_view_milestones(db, row["agent_id"], video_id, new_views)
        # Record watch history
        if agent_id:
            db.execute(
                """INSERT INTO watch_history (agent_id, video_id, watched_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(agent_id, video_id) DO UPDATE SET watched_at = excluded.watched_at""",
                (agent_id, video_id, time.time()),
            )
        db.commit()
    else:
        reward_result = {"awarded": False, "held": False, "risk_score": 0, "reasons": ["deduplicated recent view"]}

    d = video_to_dict(row)
    d["agent_name"] = row["agent_name"]
    d["display_name"] = row["display_name"]
    d["views"] = row["views"] + 1
    d["reward"] = reward_result
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
        """SELECT c.content, c.comment_type, a.agent_name, c.created_at
           FROM comments c JOIN agents a ON c.agent_id = a.id
           WHERE c.video_id = ?
           ORDER BY c.created_at ASC LIMIT 50""",
        (video_id,),
    ).fetchall()

    comment_list = [
        {
            "agent": c["agent_name"],
            "text": c["content"],
            "comment_type": c["comment_type"] or "comment",
            "at": c["created_at"],
        }
        for c in comments
    ]

    tags = _safe_json_loads_list(row["tags"])

    return jsonify({
        "video_id": row["video_id"],
        "title": row["title"],
        "description": row["description"],
        "scene_description": row["scene_description"] or "(No scene description provided by uploader)",
        "novelty_score": row["novelty_score"] if "novelty_score" in row.keys() else 0,
        "agent_name": row["agent_name"],
        "display_name": row["display_name"],
        "duration_sec": row["duration_sec"],
        "resolution": f"{row['width']}x{row['height']}" if row["width"] else "unknown",
        "views": row["views"],
        "likes": row["likes"],
        "dislikes": row["dislikes"],
        "tags": tags,
        "revision_of": row["revision_of"] if "revision_of" in row.keys() else "",
        "challenge_id": row["challenge_id"] if "challenge_id" in row.keys() else "",
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
    comment_type = (data.get("comment_type") or "comment").strip().lower()
    if not content:
        return jsonify({"error": "content is required"}), 400
    if comment_type not in COMMENT_TYPES:
        return jsonify({"error": f"comment_type must be one of {sorted(COMMENT_TYPES)}"}), 400
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

    cur = db.execute(
        """INSERT INTO comments (video_id, agent_id, parent_id, content, comment_type, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (video_id, g.agent["id"], parent_id, content, comment_type, time.time()),
    )
    reward_result = _comment_reward_decision(
        db,
        agent_id=g.agent["id"],
        video_id=video_id,
        comment_id=int(cur.lastrowid),
        content=content,
    )
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
    _refresh_agent_quests(db, g.agent["id"], ["first_comment"])
    db.commit()

    return jsonify({
        "ok": True,
        "comment_id": int(cur.lastrowid),
        "reward": {
            "awarded": bool(reward_result["awarded"]),
            "held": bool(reward_result["held"]),
            "risk_score": int(reward_result["risk_score"]),
            "reasons": reward_result["reasons"],
        },
        "agent_name": g.agent["agent_name"],
        "content": content,
        "comment_type": comment_type,
        "video_id": video_id,
        "rtc_earned": RTC_REWARD_COMMENT if reward_result["awarded"] else 0.0,
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
    comment_type = (data.get("comment_type") or "comment").strip().lower()
    if not content:
        return jsonify({"error": "content is required"}), 400
    if comment_type not in COMMENT_TYPES:
        return jsonify({"error": f"comment_type must be one of {sorted(COMMENT_TYPES)}"}), 400
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
        """INSERT INTO comments (video_id, agent_id, parent_id, content, comment_type, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (video_id, g.user["id"], parent_id, content, comment_type, time.time()),
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
        "avatar_url": g.user.get("avatar_url", ""),
        "content": content,
        "comment_type": comment_type,
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
            "comment_type": row["comment_type"] if "comment_type" in row.keys() else "comment",
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
            "comment_type": row["comment_type"] if "comment_type" in row.keys() else "comment",
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
        category=cat,  # some templates expect `category` instead of `cat`
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
    reward_result = {"awarded": False, "held": False, "risk_score": 0, "reasons": []}

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
            reward_result = _like_reward_decision(
                db,
                owner_id=int(video["agent_id"]),
                voter_id=int(g.agent["id"]),
                video_id=video_id,
                like_event_ref=f"{video_id}:{g.agent['id']}",
            )
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
        "reward": reward_result,
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
    reward_result = {"awarded": False, "held": False, "risk_score": 0, "reasons": []}

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
            reward_result = _like_reward_decision(
                db,
                owner_id=int(video["agent_id"]),
                voter_id=int(g.user["id"]),
                video_id=video_id,
                like_event_ref=f"{video_id}:{g.user['id']}",
            )
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
        "reward": reward_result,
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
    """Search videos by title, description, tags, or agent.

    Optional filters (issue #188):
      category  - comma-separated category IDs (e.g. "retro,science-tech")
      after     - ISO date or Unix timestamp lower bound
      before    - ISO date or Unix timestamp upper bound
      min_views - minimum view count (engagement threshold)
      sort      - views|likes|recent|trending (default: views)
    """
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

    # Build dynamic WHERE clauses
    search_conditions = [
        "v.title LIKE ?",
        "v.description LIKE ?",
        "v.tags LIKE ?",
        "a.agent_name LIKE ?",
    ]
    params = [like_q, like_q, like_q, like_q]
    caption_video_ids = find_caption_video_ids(q, limit=500)
    if caption_video_ids:
        placeholders = ",".join("?" for _ in caption_video_ids)
        search_conditions.append(f"v.video_id IN ({placeholders})")
        params.extend(caption_video_ids)

    conditions = [
        "v.is_removed = 0",
        "COALESCE(a.is_banned, 0) = 0",
        f"({' OR '.join(search_conditions)})",
    ]

    # Category filter (comma-separated)
    cat_param = request.args.get("category", "").strip()
    if cat_param:
        cats = [c.strip() for c in cat_param.split(",") if c.strip()]
        if cats:
            placeholders = ",".join("?" for _ in cats)
            conditions.append(f"v.category IN ({placeholders})")
            params.extend(cats)

    # Date range filters
    def _parse_ts(val):
        """Parse ISO date string or Unix timestamp."""
        if not val:
            return None
        try:
            return float(val)
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                import calendar, datetime as _dt
                return calendar.timegm(_dt.datetime.strptime(val, fmt).timetuple())
            except ValueError:
                continue
        return None

    after_ts = _parse_ts(request.args.get("after", ""))
    if after_ts is not None:
        conditions.append("v.created_at >= ?")
        params.append(after_ts)

    before_ts = _parse_ts(request.args.get("before", ""))
    if before_ts is not None:
        conditions.append("v.created_at <= ?")
        params.append(before_ts)

    # Engagement threshold
    min_views = request.args.get("min_views", 0, type=int)
    if min_views > 0:
        conditions.append("v.views >= ?")
        params.append(min_views)

    where = " AND ".join(conditions)

    # Sort (whitelist to prevent injection)
    SORT_MAP = {
        "views": "v.views DESC, v.created_at DESC",
        "likes": "v.likes DESC, v.created_at DESC",
        "recent": "v.created_at DESC",
        "trending": "(v.views + v.likes * 3) DESC, v.created_at DESC",
    }
    sort_key = request.args.get("sort", "views").lower()
    order_by = SORT_MAP.get(sort_key, SORT_MAP["views"])

    total = db.execute(
        f"SELECT COUNT(*) FROM videos v JOIN agents a ON v.agent_id = a.id WHERE {where}",
        params,
    ).fetchone()[0]

    rows = db.execute(
        f"""SELECT v.*, a.agent_name, a.display_name, a.avatar_url
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE {where}
           ORDER BY {order_by}
           LIMIT ? OFFSET ?""",
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
        "query": q,
        "videos": videos,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": math.ceil(total / per_page) if total else 0,
        "filters": {
            "category": cat_param or None,
            "after": after_ts,
            "before": before_ts,
            "min_views": min_views if min_views > 0 else None,
            "sort": sort_key,
        },
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
    agent_badges = _list_agent_badges(db, int(agent["id"]))
    return jsonify({
        "agent": agent_to_dict(agent, include_private=is_self, badges=agent_badges),
        "videos": video_list,
        "video_count": len(video_list),
    })


# ---------------------------------------------------------------------------
# Creator Analytics (issue #189)
# ---------------------------------------------------------------------------

@app.route("/api/agents/<agent_name>/analytics")
def get_agent_analytics(agent_name):
    """Time-series analytics for a creator: views, engagement, subscribers."""
    db = get_db()
    agent = db.execute(
        "SELECT id, agent_name, display_name FROM agents WHERE agent_name = ?",
        (agent_name,),
    ).fetchone()
    if not agent:
        return jsonify({"error": "Agent not found"}), 404

    aid = agent["id"]
    days = min(90, max(1, request.args.get("days", 30, type=int)))
    now = time.time()
    cutoff = now - days * 86400

    # Daily view counts across all creator's videos
    daily_views = db.execute(
        """SELECT date(vw.created_at, 'unixepoch') AS day, COUNT(*) AS cnt
           FROM views vw
           JOIN videos v ON vw.video_id = v.video_id
           WHERE v.agent_id = ? AND vw.created_at >= ?
           GROUP BY day ORDER BY day""",
        (aid, cutoff),
    ).fetchall()

    # Totals
    totals = db.execute(
        """SELECT COUNT(*) AS videos,
                  COALESCE(SUM(v.views), 0) AS total_views,
                  COALESCE(SUM(v.likes), 0) AS total_likes,
                  COALESCE(SUM(v.dislikes), 0) AS total_dislikes
           FROM videos v WHERE v.agent_id = ? AND v.is_removed = 0""",
        (aid,),
    ).fetchone()

    # Subscriber count & recent growth
    sub_total = db.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE following_id = ?", (aid,)
    ).fetchone()[0]

    sub_recent = db.execute(
        """SELECT date(created_at, 'unixepoch') AS day, COUNT(*) AS cnt
           FROM subscriptions WHERE following_id = ? AND created_at >= ?
           GROUP BY day ORDER BY day""",
        (aid, cutoff),
    ).fetchall()

    # Comment count on creator's videos
    comment_count = db.execute(
        """SELECT COUNT(*) FROM comments c
           JOIN videos v ON c.video_id = v.video_id
           WHERE v.agent_id = ? AND c.created_at >= ?""",
        (aid, cutoff),
    ).fetchone()[0]

    # Top videos by views in period
    top_videos = db.execute(
        """SELECT v.video_id, v.title, v.views, v.likes,
                  (SELECT COUNT(*) FROM views vw
                   WHERE vw.video_id = v.video_id AND vw.created_at >= ?) AS recent_views
           FROM videos v WHERE v.agent_id = ? AND v.is_removed = 0
           ORDER BY recent_views DESC LIMIT 5""",
        (cutoff, aid),
    ).fetchall()

    engagement_rate = 0.0
    if totals["total_views"] > 0:
        engagement_rate = round(
            (totals["total_likes"] + comment_count) / totals["total_views"] * 100, 2
        )

    return jsonify({
        "agent": agent_name,
        "period_days": days,
        "totals": {
            "videos": totals["videos"],
            "views": totals["total_views"],
            "likes": totals["total_likes"],
            "dislikes": totals["total_dislikes"],
            "subscribers": sub_total,
            "engagement_rate_pct": engagement_rate,
        },
        "daily_views": [{"date": r["day"], "views": r["cnt"]} for r in daily_views],
        "subscriber_growth": [{"date": r["day"], "new_subs": r["cnt"]} for r in sub_recent],
        "comments_in_period": comment_count,
        "top_videos": [
            {"video_id": r["video_id"], "title": r["title"],
             "total_views": r["views"], "likes": r["likes"],
             "views_in_period": r["recent_views"]}
            for r in top_videos
        ],
    })


@app.route("/api/videos/<video_id>/analytics")
def get_video_analytics(video_id):
    """Per-video analytics: daily views, engagement breakdown."""
    db = get_db()
    video = db.execute(
        "SELECT * FROM videos WHERE video_id = ? AND is_removed = 0", (video_id,)
    ).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    days = min(90, max(1, request.args.get("days", 30, type=int)))
    now = time.time()
    cutoff = now - days * 86400

    # Daily views
    daily_views = db.execute(
        """SELECT date(created_at, 'unixepoch') AS day, COUNT(*) AS cnt
           FROM views WHERE video_id = ? AND created_at >= ?
           GROUP BY day ORDER BY day""",
        (video_id, cutoff),
    ).fetchall()

    # Comments in period
    comments = db.execute(
        """SELECT COUNT(*) AS cnt,
                  COUNT(DISTINCT agent_id) AS unique_commenters
           FROM comments WHERE video_id = ? AND created_at >= ?""",
        (video_id, cutoff),
    ).fetchone()

    # Watch duration stats (if available)
    watch_stats = db.execute(
        """SELECT COUNT(*) AS watchers,
                  ROUND(AVG(watch_duration_sec), 1) AS avg_duration,
                  ROUND(MAX(watch_duration_sec), 1) AS max_duration
           FROM watch_history WHERE video_id = ?""",
        (video_id,),
    ).fetchone()

    # Engagement rate
    engagement_rate = 0.0
    if video["views"] > 0:
        engagement_rate = round(
            (video["likes"] + comments["cnt"]) / video["views"] * 100, 2
        )

    return jsonify({
        "video_id": video_id,
        "title": video["title"],
        "period_days": days,
        "totals": {
            "views": video["views"],
            "likes": video["likes"],
            "dislikes": video["dislikes"],
            "comments": comments["cnt"],
            "unique_commenters": comments["unique_commenters"],
            "engagement_rate_pct": engagement_rate,
        },
        "daily_views": [{"date": r["day"], "views": r["cnt"]} for r in daily_views],
        "watch_stats": {
            "unique_watchers": watch_stats["watchers"],
            "avg_duration_sec": watch_stats["avg_duration"],
            "max_duration_sec": watch_stats["max_duration"],
        } if watch_stats["watchers"] else None,
        "uploaded_at": video["created_at"],
        "category": video["category"],
    })


# ---------------------------------------------------------------------------
# Agent Social Graph (issue #190)
# ---------------------------------------------------------------------------

@app.route("/api/agents/<agent_name>/interactions")
def get_agent_interactions(agent_name):
    """Who interacted with this agent and how (comments, likes, subscriptions)."""
    db = get_db()
    agent = db.execute(
        "SELECT id, agent_name, display_name FROM agents WHERE agent_name = ?",
        (agent_name,),
    ).fetchone()
    if not agent:
        return jsonify({"error": "Agent not found"}), 404

    aid = agent["id"]
    limit = min(50, max(1, request.args.get("limit", 20, type=int)))

    # Agents who commented on this agent's videos
    commenters = db.execute(
        """SELECT a2.agent_name, a2.display_name, a2.avatar_url,
                  COUNT(*) AS comment_count,
                  MAX(c.created_at) AS last_at
           FROM comments c
           JOIN videos v ON c.video_id = v.video_id
           JOIN agents a2 ON c.agent_id = a2.id
           WHERE v.agent_id = ? AND c.agent_id != ?
           GROUP BY a2.id ORDER BY comment_count DESC LIMIT ?""",
        (aid, aid, limit),
    ).fetchall()

    # Agents who liked this agent's videos
    likers = db.execute(
        """SELECT a2.agent_name, a2.display_name, a2.avatar_url,
                  COUNT(*) AS like_count,
                  MAX(vt.created_at) AS last_at
           FROM votes vt
           JOIN videos v ON vt.video_id = v.video_id
           JOIN agents a2 ON vt.agent_id = a2.id
           WHERE v.agent_id = ? AND vt.vote = 1 AND vt.agent_id != ?
           GROUP BY a2.id ORDER BY like_count DESC LIMIT ?""",
        (aid, aid, limit),
    ).fetchall()

    # Subscribers (followers of this agent)
    followers = db.execute(
        """SELECT a2.agent_name, a2.display_name, a2.avatar_url,
                  s.created_at AS subscribed_at
           FROM subscriptions s
           JOIN agents a2 ON s.follower_id = a2.id
           WHERE s.following_id = ?
           ORDER BY s.created_at DESC LIMIT ?""",
        (aid, limit),
    ).fetchall()

    # Who this agent interacts with most (outgoing)
    interacts_with = db.execute(
        """SELECT a2.agent_name, a2.display_name, a2.avatar_url,
                  COALESCE(cm.cnt, 0) AS comments_given,
                  COALESCE(lk.cnt, 0) AS likes_given,
                  COALESCE(cm.cnt, 0) + COALESCE(lk.cnt, 0) AS total
           FROM agents a2
           LEFT JOIN (
               SELECT v.agent_id AS target, COUNT(*) AS cnt
               FROM comments c JOIN videos v ON c.video_id = v.video_id
               WHERE c.agent_id = ? AND v.agent_id != ?
               GROUP BY v.agent_id
           ) cm ON a2.id = cm.target
           LEFT JOIN (
               SELECT v.agent_id AS target, COUNT(*) AS cnt
               FROM votes vt JOIN videos v ON vt.video_id = v.video_id
               WHERE vt.agent_id = ? AND vt.vote = 1 AND v.agent_id != ?
               GROUP BY v.agent_id
           ) lk ON a2.id = lk.target
           WHERE COALESCE(cm.cnt, 0) + COALESCE(lk.cnt, 0) > 0
           ORDER BY total DESC LIMIT ?""",
        (aid, aid, aid, aid, limit),
    ).fetchall()

    def _row_list(rows, extra_fields):
        result = []
        for r in rows:
            d = {"agent_name": r["agent_name"], "display_name": r["display_name"],
                 "avatar_url": r["avatar_url"]}
            for f in extra_fields:
                d[f] = r[f]
            result.append(d)
        return result

    return jsonify({
        "agent": agent_name,
        "incoming": {
            "commenters": _row_list(commenters, ["comment_count", "last_at"]),
            "likers": _row_list(likers, ["like_count", "last_at"]),
            "followers": _row_list(followers, ["subscribed_at"]),
        },
        "outgoing": _row_list(interacts_with, ["comments_given", "likes_given", "total"]),
    })


@app.route("/api/social/graph")
def social_graph():
    """Platform-wide social graph: top interacting pairs and network density."""
    db = get_db()
    limit = min(50, max(1, request.args.get("limit", 20, type=int)))

    # Top interacting pairs (bidirectional: comments + likes between agents)
    pairs = db.execute(
        """SELECT
               a1.agent_name AS from_agent, a1.display_name AS from_display,
               a2.agent_name AS to_agent, a2.display_name AS to_display,
               COALESCE(cm.cnt, 0) AS comments,
               COALESCE(lk.cnt, 0) AS likes,
               COALESCE(cm.cnt, 0) + COALESCE(lk.cnt, 0) AS strength
           FROM (
               SELECT c.agent_id AS src, v.agent_id AS dst, COUNT(*) AS cnt
               FROM comments c JOIN videos v ON c.video_id = v.video_id
               WHERE c.agent_id != v.agent_id
               GROUP BY c.agent_id, v.agent_id
           ) cm
           LEFT JOIN (
               SELECT vt.agent_id AS src, v.agent_id AS dst, COUNT(*) AS cnt
               FROM votes vt JOIN videos v ON vt.video_id = v.video_id
               WHERE vt.agent_id != v.agent_id AND vt.vote = 1
               GROUP BY vt.agent_id, v.agent_id
           ) lk ON cm.src = lk.src AND cm.dst = lk.dst
           JOIN agents a1 ON cm.src = a1.id
           JOIN agents a2 ON cm.dst = a2.id
           ORDER BY strength DESC LIMIT ?""",
        (limit,),
    ).fetchall()

    # Network stats
    total_agents = db.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    total_subs = db.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]
    active_commenters = db.execute(
        "SELECT COUNT(DISTINCT agent_id) FROM comments"
    ).fetchone()[0]
    active_likers = db.execute(
        "SELECT COUNT(DISTINCT agent_id) FROM votes WHERE vote = 1"
    ).fetchone()[0]

    # Most connected agents (by unique interaction partners)
    most_connected = db.execute(
        """SELECT a.agent_name, a.display_name, a.avatar_url,
                  COUNT(DISTINCT partner) AS connections
           FROM (
               SELECT c.agent_id AS self, v.agent_id AS partner
               FROM comments c JOIN videos v ON c.video_id = v.video_id
               WHERE c.agent_id != v.agent_id
               UNION
               SELECT v.agent_id AS self, c.agent_id AS partner
               FROM comments c JOIN videos v ON c.video_id = v.video_id
               WHERE c.agent_id != v.agent_id
               UNION
               SELECT follower_id AS self, following_id AS partner FROM subscriptions
               UNION
               SELECT following_id AS self, follower_id AS partner FROM subscriptions
           ) edges
           JOIN agents a ON edges.self = a.id
           GROUP BY a.id ORDER BY connections DESC LIMIT 10""",
    ).fetchall()

    return jsonify({
        "network": {
            "total_agents": total_agents,
            "total_subscriptions": total_subs,
            "active_commenters": active_commenters,
            "active_likers": active_likers,
        },
        "top_pairs": [
            {"from": r["from_agent"], "from_display": r["from_display"],
             "to": r["to_agent"], "to_display": r["to_display"],
             "comments": r["comments"], "likes": r["likes"],
             "strength": r["strength"]}
            for r in pairs
        ],
        "most_connected": [
            {"agent_name": r["agent_name"], "display_name": r["display_name"],
             "avatar_url": r["avatar_url"], "connections": r["connections"]}
            for r in most_connected
        ],
    })


# ---------------------------------------------------------------------------
# Trending / Feed
# ---------------------------------------------------------------------------

def _get_trending_videos(db, limit=20):
    """Compute trending videos with improved scoring.

    Score = (recent_views_24h * 2) + (likes * 3) + (recent_comments_24h * 4)
            + recency_bonus + (novelty_score * NOVELTY_WEIGHT)
            + penalties (duplicate/low-info)
    recency_bonus: +10 if uploaded < 6h ago, +5 if < 24h ago
    """
    now = time.time()
    cutoff_24h = now - 86400
    cutoff_6h = now - 21600
    query_limit = max(limit * 3, limit)

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
           WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0
           ORDER BY (
               COALESCE(rv.recent_views, 0) * 2
               + v.likes * 3
               + COALESCE(rc.recent_comments, 0) * 4
               + CASE
                   WHEN v.created_at > ? THEN 10
                   WHEN v.created_at > ? THEN 5
                   ELSE 0
               END
               + (v.novelty_score * ?)
               + CASE
                   WHEN v.novelty_flags LIKE '%high_similarity%' THEN -?
                   ELSE 0
               END
               + CASE
                   WHEN v.novelty_flags LIKE '%low_info%' THEN -?
                   ELSE 0
               END
           ) DESC, v.created_at DESC
           LIMIT ?""",
        (
            cutoff_6h,
            cutoff_24h,
            cutoff_24h,
            cutoff_24h,
            cutoff_6h,
            cutoff_24h,
            NOVELTY_WEIGHT,
            TRENDING_PENALTY_HIGH_SIMILARITY,
            TRENDING_PENALTY_LOW_INFO,
            query_limit,
        ),
    ).fetchall()
    if TRENDING_AGENT_CAP <= 0:
        return rows[:limit]

    filtered = []
    per_agent = {}
    for row in rows:
        aid = row["agent_id"]
        if per_agent.get(aid, 0) >= TRENDING_AGENT_CAP:
            continue
        per_agent[aid] = per_agent.get(aid, 0) + 1
        filtered.append(row)
        if len(filtered) >= limit:
            break
    return filtered


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
    """Get feed of recent videos with optional recommendation mode.
    
    Query parameters:
        - page: Page number (default 1)
        - per_page: Items per page (default 20, max 50)
        - mode: "latest" (deterministic, default) or "recommended" (ML scoring)
        - category: Filter by category (optional)
    
    Returns:
        JSON with videos list, page info, and mode used.
    """
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 20, type=int)))
    mode = request.args.get("mode", "latest")
    category = request.args.get("category")
    
    # Get optional API key for personalized recommendations
    api_key = request.headers.get("X-API-Key") or request.args.get("api_key")
    agent_id = None
    if api_key:
        db = get_db()
        agent = db.execute(
            "SELECT id FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()
        if agent:
            agent_id = agent["id"]
    
    # Use recommendation engine for recommended mode
    if mode == "recommended":
        from recommendation_engine import get_feed_recommendations
        db = get_db()
        videos, actual_mode = get_feed_recommendations(
            db,
            agent_id=agent_id,
            limit=per_page,
            mode="recommended" if agent_id else "latest",
            category=category,
            exclude_agent=agent_id  # Exclude own videos from feed
        )
        # Convert to standard format
        result_videos = []
        for v in videos:
            d = video_to_dict(v)
            d["agent_name"] = v.get("agent_name", "")
            d["display_name"] = v.get("display_name", "")
            d["avatar_url"] = v.get("avatar_url", "")
            d["recommend_score"] = v.get("recommend_score", 0)
            result_videos.append(d)
        return jsonify({
            "videos": result_videos,
            "page": page,
            "mode": actual_mode
        })
    
    # Default: latest mode (deterministic fallback)
    offset = (page - 1) * per_page

    db = get_db()
    
    # Build query with optional category filter
    if category:
        rows = db.execute(
            """SELECT v.*, a.agent_name, a.display_name, a.avatar_url
               FROM videos v JOIN agents a ON v.agent_id = a.id
               WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0
               AND v.category = ?
               ORDER BY v.created_at DESC
               LIMIT ? OFFSET ?""",
            (category, per_page, offset),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT v.*, a.agent_name, a.display_name, a.avatar_url
               FROM videos v JOIN agents a ON v.agent_id = a.id
               WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0
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

    return jsonify({"videos": videos, "page": page, "mode": "latest"})


@app.route("/api/challenges")
def list_challenges():
    """List challenges (active + upcoming + recent closed)."""
    db = get_db()
    now = time.time()
    rows = db.execute(
        """SELECT * FROM challenges
           ORDER BY start_at DESC, created_at DESC""",
    ).fetchall()
    challenges = []
    for row in rows:
        status = row["status"]
        if row["start_at"] and row["end_at"]:
            if row["start_at"] <= now <= row["end_at"]:
                status = "active"
            elif now < row["start_at"]:
                status = "upcoming"
            else:
                status = "closed"
        challenges.append({
            "challenge_id": row["challenge_id"],
            "title": row["title"],
            "description": row["description"],
            "tags": _safe_json_loads_list(row["tags"]),
            "reward": row["reward"],
            "status": status,
            "start_at": row["start_at"],
            "end_at": row["end_at"],
        })
    return jsonify({"challenges": challenges, "count": len(challenges)})


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

    profile = agent_to_dict(agent, include_private=True, badges=_list_agent_badges(db, int(agent["id"])))
    profile["video_count"] = video_count
    profile["total_views"] = total_views
    profile["comment_count"] = comment_count
    profile["total_likes"] = total_likes

    return jsonify(profile)


@app.route("/api/quests/me")
@app.route("/api/agents/me/quests")
@require_api_key
def my_quests():
    """Return current quest progress for the authenticated agent."""
    db = get_db()
    quests = _refresh_agent_quests(db, g.agent["id"])
    db.commit()

    total_quest_rtc = sum(q["reward_rtc"] for q in quests if q["rewarded_at"] > 0)
    completed_count = sum(1 for q in quests if q["completed"])
    return jsonify({
        "ok": True,
        "agent_name": g.agent["agent_name"],
        "completed_count": completed_count,
        "total_count": len(quests),
        "quest_rtc_earned": round(total_quest_rtc, 4),
        "quests": quests,
    })


@app.route("/api/quests/leaderboard")
def quest_leaderboard():
    """Public leaderboard for completed quests and earned quest RTC."""
    limit = min(100, max(1, request.args.get("limit", 25, type=int)))
    db = get_db()
    rows = db.execute(
        """
        SELECT
            a.agent_name,
            a.display_name,
            a.avatar_url,
            SUM(CASE WHEN aq.completed_at > 0 THEN 1 ELSE 0 END) AS completed_count,
            COALESCE(SUM(CASE WHEN aq.rewarded_at > 0 THEN q.reward_rtc ELSE 0 END), 0) AS quest_rtc_earned
        FROM agents a
        JOIN agent_quests aq ON aq.agent_id = a.id
        JOIN quests q ON q.quest_key = aq.quest_key
        GROUP BY a.id, a.agent_name, a.display_name, a.avatar_url
        HAVING completed_count > 0
        ORDER BY completed_count DESC, quest_rtc_earned DESC, a.created_at ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return jsonify({
        "ok": True,
        "leaderboard": [
            {
                "agent_name": row["agent_name"],
                "display_name": row["display_name"],
                "avatar_url": row["avatar_url"] or "",
                "completed_count": int(row["completed_count"] or 0),
                "quest_rtc_earned": round(float(row["quest_rtc_earned"] or 0), 4),
            }
            for row in rows
        ],
    })


# ---------------------------------------------------------------------------
# Gamification: Level, Streak, and Progression APIs
# ---------------------------------------------------------------------------

@app.route("/api/gamification/level")
@require_api_key
def agent_level():
    """Get the authenticated agent's level and XP progression."""
    db = get_db()
    level_info = _get_agent_level_info(db, g.agent["id"])
    return jsonify({
        "ok": True,
        "agent_name": g.agent["agent_name"],
        **level_info,
    })


@app.route("/api/gamification/streak")
@require_api_key
def agent_streak():
    """Get the authenticated agent's activity streak and bonus multiplier."""
    db = get_db()
    streak_days = _activity_streak_days(db, g.agent["id"])
    multiplier = _get_streak_bonus_multiplier(streak_days)
    
    # Find next milestone
    next_milestone = None
    for threshold in sorted(STREAK_BONUS_MULTIPLIERS.keys()):
        if threshold > streak_days:
            next_milestone = threshold
            break
    
    return jsonify({
        "ok": True,
        "agent_name": g.agent["agent_name"],
        "streak_days": streak_days,
        "current_multiplier": multiplier,
        "bonus_percentage": round((multiplier - 1.0) * 100, 1),
        "next_milestone": next_milestone,
        "days_to_next": (next_milestone - streak_days) if next_milestone else None,
        "milestones": [
            {"days": d, "multiplier": m, "bonus": round((m - 1.0) * 100, 0)}
            for d, m in sorted(STREAK_BONUS_MULTIPLIERS.items())
        ],
    })


@app.route("/api/gamification/leaderboard")
def gamification_leaderboard():
    """Combined leaderboard showing levels, XP, quest completion, and streaks."""
    limit = min(100, max(1, request.args.get("limit", 25, type=int)))
    db = get_db()
    
    rows = db.execute(
        """
        SELECT
            a.id,
            a.agent_name,
            a.display_name,
            a.avatar_url,
            a.created_at,
            COALESCE(SUM(CASE WHEN e.reason LIKE 'quest_complete:%' THEN e.amount ELSE 0 END), 0) AS total_xp,
            SUM(CASE WHEN aq.completed_at > 0 THEN 1 ELSE 0 END) AS quests_completed,
            COALESCE(SUM(CASE WHEN aq.rewarded_at > 0 THEN q.reward_rtc ELSE 0 END), 0) AS quest_rtc_earned
        FROM agents a
        LEFT JOIN earnings e ON e.agent_id = a.id
        LEFT JOIN agent_quests aq ON aq.agent_id = a.id
        LEFT JOIN quests q ON q.quest_key = aq.quest_key
        GROUP BY a.id, a.agent_name, a.display_name, a.avatar_url, a.created_at
        HAVING total_xp > 0 OR quests_completed > 0
        ORDER BY total_xp DESC, quests_completed DESC, quest_rtc_earned DESC, a.created_at ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    
    leaderboard = []
    for row in rows:
        xp = int(row["total_xp"] or 0)
        level = _get_agent_level(xp)
        leaderboard.append({
            "agent_name": row["agent_name"],
            "display_name": row["display_name"],
            "avatar_url": row["avatar_url"] or "",
            "level": level,
            "xp": xp,
            "quests_completed": int(row["quests_completed"] or 0),
            "quest_rtc_earned": round(float(row["quest_rtc_earned"] or 0), 4),
        })
    
    return jsonify({
        "ok": True,
        "leaderboard": leaderboard,
        "count": len(leaderboard),
    })


@app.route("/api/stats")
def platform_stats():
    """Get public platform statistics."""
    db = get_db()
    videos = db.execute("SELECT COUNT(*) FROM videos WHERE is_removed = 0").fetchone()[0]
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
    _refresh_agent_quests(db, g.agent["id"], ["profile_complete"])
    _referral_refresh_invite_state(db, g.agent["id"])
    db.commit()

    agent = db.execute("SELECT * FROM agents WHERE id = ?", (g.agent["id"],)).fetchone()
    profile = agent_to_dict(agent, include_private=True, badges=_list_agent_badges(db, int(agent["id"])))
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
    _refresh_agent_quests(db, g.agent["id"], ["first_follow"])
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
    db = get_db()
    unread_only = request.args.get("unread", "").lower() in ("1", "true", "yes")
    notifications, total = _notification_page(db, int(g.agent["id"]), page, per_page, unread_only)
    return jsonify({
        "notifications": notifications,
        "page": page, "per_page": per_page, "total": total,
        "unread": _notification_unread_count(db, int(g.agent["id"])),
    })


@app.route("/api/agents/me/notifications/count")
@require_api_key
def notification_count():
    """Get unread notification count."""
    db = get_db()
    return jsonify({"unread": _notification_unread_count(db, int(g.agent["id"]))})


@app.route("/api/agents/me/notifications/read", methods=["POST"])
@require_api_key
def mark_notifications_read():
    """Mark notifications as read. Send {ids: [1,2,3]} or {all: true}."""
    db = get_db()
    data = request.get_json(silent=True) or {}
    updated = _mark_notification_rows_read(
        db,
        int(g.agent["id"]),
        notification_ids=data.get("ids", []),
        mark_all=bool(data.get("all")),
    )
    db.commit()
    return jsonify({"ok": True, "updated": updated})


# Web notification endpoints (session auth)

@app.route("/api/notifications")
@app.route("/api/notifications/web-list")
def web_notification_list():
    """Get notifications for the logged-in web user."""
    if not g.user:
        return jsonify({"error": "Login required", "login_required": True}), 401

    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 20, type=int)))
    unread_only = request.args.get("unread_only", request.args.get("unread", "0")).lower() in (
        "1",
        "true",
        "yes",
    )

    db = get_db()
    notifications, total = _notification_page(db, int(g.user["id"]), page, per_page, unread_only)
    return jsonify(
        {
            "notifications": notifications,
            "page": page,
            "per_page": per_page,
            "total": total,
            "unread": _notification_unread_count(db, int(g.user["id"])),
        }
    )


@app.route("/api/notifications/unread-count")
def web_notification_count():
    """Get unread notification count for logged-in web user."""
    if not g.user:
        return jsonify({"unread": 0})
    db = get_db()
    return jsonify({"unread": _notification_unread_count(db, int(g.user["id"]))})


@app.route("/api/notifications/read", methods=["POST"])
@app.route("/api/notifications/web-read", methods=["POST"])
def web_mark_read():
    """Mark notifications as read from web UI."""
    if not g.user:
        return jsonify({"error": "Login required"}), 401
    _verify_csrf()
    db = get_db()
    data = request.get_json(silent=True) or {}
    updated = _mark_notification_rows_read(
        db,
        int(g.user["id"]),
        notification_ids=data.get("ids", []),
        mark_all=bool(data.get("all")),
    )
    db.commit()
    return jsonify({"ok": True, "updated": updated})


@app.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
def web_mark_single_notification_read(notification_id: int):
    """Mark a single notification as read for the logged-in web user."""
    if not g.user:
        return jsonify({"error": "Login required"}), 401
    _verify_csrf()
    db = get_db()
    updated = _mark_notification_rows_read(db, int(g.user["id"]), notification_ids=[notification_id])
    db.commit()
    if updated <= 0:
        return jsonify({"error": "Notification not found"}), 404
    return jsonify({"ok": True, "updated": updated})


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

WEBHOOK_EVENTS = ["video.uploaded", "video.voted", "comment.created", "agent.created", "comment", "like", "subscribe", "new_video", "mention", "*"]


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
            return jsonify({"error": f"Unknown event: {ev}. Valid examples: video.uploaded, video.voted, comment.created, agent.created, *"}), 400

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
        "event": "test",
        "timestamp": datetime.datetime.utcfromtimestamp(time.time()).isoformat() + "Z",
        "data": {
            "message": "This is a test webhook from BoTTube",
            "agent": g.agent["agent_name"],
        },
    }
    body = json.dumps(test_payload, separators=(",", ":")).encode()
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

    # Notify search engines of URL removal
    ping_google_indexing(f"https://bottube.ai/watch/{video_id}", action="URL_DELETED")

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
        a = dict(g.agent)
        return jsonify({
            "agent_name": a["agent_name"],
            "rtc_balance": a.get("rtc_balance", 0),
            "wallets": {
                # RustChain on-chain wallet (RTC... address) used for on-chain tips
                "rtc_wallet": a.get("rtc_wallet", ""),
                # Legacy / external donation address
                "rtc": a.get("rtc_address", ""),
                "btc": a.get("btc_address", ""),
                "eth": a.get("eth_address", ""),
                "sol": a.get("sol_address", ""),
                "ltc": a.get("ltc_address", ""),
                "erg": a.get("erg_address", ""),
                "paypal": a.get("paypal_email", ""),
            },
        })

    # POST: Update wallet addresses
    data = request.get_json(silent=True) or {}
    allowed_fields = {
        "rtc_wallet": "rtc_wallet",
        "rtc": "rtc_address",
        "btc": "btc_address",
        "eth": "eth_address",
        "sol": "sol_address",
        "ltc": "ltc_address",
        "erg": "erg_address",
        "paypal": "paypal_email",
    }

    if "rtc_wallet" in data:
        rtc_wallet = str(data.get("rtc_wallet", "")).strip()
        if rtc_wallet and not _is_rustchain_rtc_address(rtc_wallet):
            return jsonify({"error": "Invalid RustChain wallet address format (expected RTC... address)"}), 400

    updates = []
    params = []
    for key, col in allowed_fields.items():
        if key in data:
            val = str(data[key]).strip()
            updates.append(f"{col} = ?")
            params.append(val)

    if not updates:
        return jsonify({"error": "No wallet fields provided. Use: rtc_wallet, rtc, btc, eth, sol, ltc, erg, paypal"}), 400

    params.append(g.agent["id"])
    db.execute(f"UPDATE agents SET {', '.join(updates)} WHERE id = ?", params)
    if str(data.get("rtc_wallet", "")).strip():
        _referral_mark_rtc_native_action(
            db,
            int(g.agent["id"]),
            evidence_ref="/settings/wallet",
        )
    db.commit()

    return jsonify({
        "ok": True,
        "message": "Wallet addresses updated.",
        "updated_fields": [k for k in allowed_fields if k in data],
    })


@app.route("/api/users/me/wallet", methods=["GET", "POST"])
def manage_wallet_web():
    """Web/session version of /api/agents/me/wallet (for humans)."""
    if not g.user:
        return jsonify({"error": "Login required"}), 401

    if request.method == "GET":
        u = dict(g.user)
        return jsonify({
            "agent_name": u.get("agent_name", ""),
            "wallets": {
                "rtc_wallet": u.get("rtc_wallet", ""),
                "rtc": u.get("rtc_address", ""),
            },
        })

    _verify_csrf()
    data = request.get_json(silent=True) or {}
    rtc_wallet = str(data.get("rtc_wallet", "")).strip()

    if rtc_wallet and not _is_rustchain_rtc_address(rtc_wallet):
        return jsonify({"error": "Invalid RustChain wallet address format (expected RTC... address)"}), 400

    db = get_db()
    db.execute("UPDATE agents SET rtc_wallet = ? WHERE id = ?", (rtc_wallet, g.user["id"]))
    if rtc_wallet:
        _referral_mark_rtc_native_action(
            db,
            int(g.user["id"]),
            evidence_ref="/settings/wallet",
        )
    db.commit()
    return jsonify({"ok": True, "rtc_wallet": rtc_wallet})


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
# RTC Tipping
# ---------------------------------------------------------------------------

@app.route("/api/videos/<video_id>/tip", methods=["POST"])
@require_api_key
def tip_video(video_id):
    """Send an RTC tip to a video's creator (API key auth).

    POST JSON: {"amount": 0.01, "message": "Great video!"}
    """
    if not _rate_limit(f"tip:{g.agent['id']}", 30, 3600):
        return jsonify({"error": "Tip rate limit exceeded. Try again later."}), 429

    db = get_db()
    video = db.execute(
        "SELECT v.agent_id, v.title, a.agent_name AS creator_name, "
        "       a.rtc_wallet AS creator_rtc_wallet, a.rtc_address AS creator_rtc_address "
        "FROM videos v JOIN agents a ON v.agent_id = a.id WHERE v.video_id = ?",
        (video_id,),
    ).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    if video["agent_id"] == g.agent["id"]:
        return jsonify({"error": "You cannot tip yourself"}), 400

    data = request.get_json(force=True, silent=True) or {}
    try:
        amount = round(float(data.get("amount", 0)), 6)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid amount"}), 400

    if amount < RTC_TIP_MIN:
        return jsonify({"error": f"Minimum tip is {RTC_TIP_MIN} RTC"}), 400
    if amount > RTC_TIP_MAX:
        return jsonify({"error": f"Maximum tip is {RTC_TIP_MAX} RTC"}), 400

    message = str(data.get("message", ""))[:200].strip()

    # On-chain tip via RustChain signed transfer (Ed25519)
    if data.get("onchain"):
        to_wallet = str((video["creator_rtc_wallet"] or "")).strip()
        if not _is_rustchain_rtc_address(to_wallet):
            alt = str((video["creator_rtc_address"] or "")).strip()
            if _is_rustchain_rtc_address(alt):
                to_wallet = alt

        if not _is_rustchain_rtc_address(to_wallet):
            return jsonify({"error": "Creator has not linked a RustChain rtc_wallet (RTC... address)"}), 400

        resp, code = _handle_onchain_tip(
            db,
            sender_id=g.agent["id"],
            sender_name=g.agent["agent_name"],
            recipient_id=video["agent_id"],
            recipient_name=video["creator_name"],
            expected_to_wallet=to_wallet,
            amount=amount,
            user_message=message,
            data=data,
            video_id=video_id,
            video_title=video["title"],
        )
        db.commit()
        return jsonify(resp), code

    # Check sender balance (re-read for freshness)
    sender = db.execute("SELECT rtc_balance FROM agents WHERE id = ?", (g.agent["id"],)).fetchone()
    if sender["rtc_balance"] < amount:
        return jsonify({"error": "Insufficient RTC balance", "balance": sender["rtc_balance"]}), 400

    # Execute transfer
    db.execute("UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ?", (amount, g.agent["id"]))
    db.execute("UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?", (amount, video["agent_id"]))

    # Log tip
    db.execute(
        "INSERT INTO tips (from_agent_id, to_agent_id, video_id, amount, message, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (g.agent["id"], video["agent_id"], video_id, amount, message, time.time()),
    )

    # Log earnings for recipient
    db.execute(
        "INSERT INTO earnings (agent_id, amount, reason, video_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (video["agent_id"], amount, "tip_received", video_id, time.time()),
    )

    # Notify recipient
    notify(db, video["agent_id"], "tip",
           f'@{g.agent["agent_name"]} tipped {amount:.4f} RTC on "{video["title"]}"'
           + (f': "{message}"' if message else ""),
           from_agent=g.agent["agent_name"], video_id=video_id)
    _referral_mark_rtc_native_action(db, int(g.agent["id"]), evidence_ref=f"/watch/{video_id}")
    _referral_mark_rtc_native_action(db, int(video["agent_id"]), evidence_ref=f"/watch/{video_id}")

    db.commit()
    return jsonify({"ok": True, "amount": amount, "video_id": video_id,
                    "to": video["creator_name"], "message": message})


@app.route("/api/videos/<video_id>/web-tip", methods=["POST"])
def web_tip_video(video_id):
    """Send an RTC tip from the web UI (requires login session)."""
    if not g.user:
        return jsonify({"error": "You must be signed in to tip.", "login_required": True}), 401
    _verify_csrf()

    if not _rate_limit(f"tip:{g.user['id']}", 30, 3600):
        return jsonify({"error": "Tip rate limit exceeded. Try again later."}), 429

    db = get_db()
    video = db.execute(
        "SELECT v.agent_id, v.title, a.agent_name AS creator_name, "
        "       a.rtc_wallet AS creator_rtc_wallet, a.rtc_address AS creator_rtc_address "
        "FROM videos v JOIN agents a ON v.agent_id = a.id WHERE v.video_id = ?",
        (video_id,),
    ).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    if video["agent_id"] == g.user["id"]:
        return jsonify({"error": "You cannot tip yourself"}), 400

    data = request.get_json(force=True, silent=True) or {}
    try:
        amount = round(float(data.get("amount", 0)), 6)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid amount"}), 400

    if amount < RTC_TIP_MIN:
        return jsonify({"error": f"Minimum tip is {RTC_TIP_MIN} RTC"}), 400
    if amount > RTC_TIP_MAX:
        return jsonify({"error": f"Maximum tip is {RTC_TIP_MAX} RTC"}), 400

    message = str(data.get("message", ""))[:200].strip()

    # On-chain tip via RustChain signed transfer (Ed25519)
    if data.get("onchain"):
        to_wallet = str((video["creator_rtc_wallet"] or "")).strip()
        if not _is_rustchain_rtc_address(to_wallet):
            alt = str((video["creator_rtc_address"] or "")).strip()
            if _is_rustchain_rtc_address(alt):
                to_wallet = alt

        if not _is_rustchain_rtc_address(to_wallet):
            return jsonify({"error": "Creator has not linked a RustChain rtc_wallet (RTC... address)"}), 400

        resp, code = _handle_onchain_tip(
            db,
            sender_id=g.user["id"],
            sender_name=g.user["agent_name"],
            recipient_id=video["agent_id"],
            recipient_name=video["creator_name"],
            expected_to_wallet=to_wallet,
            amount=amount,
            user_message=message,
            data=data,
            video_id=video_id,
            video_title=video["title"],
        )
        db.commit()
        return jsonify(resp), code

    sender = db.execute("SELECT rtc_balance FROM agents WHERE id = ?", (g.user["id"],)).fetchone()
    if sender["rtc_balance"] < amount:
        return jsonify({"error": "Insufficient RTC balance", "balance": sender["rtc_balance"]}), 400

    # Execute transfer
    db.execute("UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ?", (amount, g.user["id"]))
    db.execute("UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?", (amount, video["agent_id"]))

    db.execute(
        "INSERT INTO tips (from_agent_id, to_agent_id, video_id, amount, message, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (g.user["id"], video["agent_id"], video_id, amount, message, time.time()),
    )

    db.execute(
        "INSERT INTO earnings (agent_id, amount, reason, video_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (video["agent_id"], amount, "tip_received", video_id, time.time()),
    )

    notify(db, video["agent_id"], "tip",
           f'@{g.user["agent_name"]} tipped {amount:.4f} RTC on "{video["title"]}"'
           + (f': "{message}"' if message else ""),
           from_agent=g.user["agent_name"], video_id=video_id)
    _referral_mark_rtc_native_action(db, int(g.user["id"]), evidence_ref=f"/watch/{video_id}")
    _referral_mark_rtc_native_action(db, int(video["agent_id"]), evidence_ref=f"/watch/{video_id}")

    db.commit()
    new_balance = db.execute("SELECT rtc_balance FROM agents WHERE id = ?", (g.user["id"],)).fetchone()
    return jsonify({"ok": True, "amount": amount, "video_id": video_id,
                    "to": video["creator_name"], "message": message,
                    "new_balance": round(new_balance["rtc_balance"], 6)})


@app.route("/api/agents/<agent_name>/web-tip", methods=["POST"])
def web_tip_agent(agent_name):
    """Tip a creator from the channel page (requires login session)."""
    if not g.user:
        return jsonify({"error": "You must be signed in to tip.", "login_required": True}), 401
    _verify_csrf()

    if not _rate_limit(f"tip:{g.user['id']}", 30, 3600):
        return jsonify({"error": "Tip rate limit exceeded. Try again later."}), 429

    db = get_db()
    target = db.execute(
        "SELECT id, agent_name, rtc_wallet, rtc_address FROM agents WHERE agent_name = ?",
        (agent_name,),
    ).fetchone()
    if not target:
        return jsonify({"error": "Creator not found"}), 404

    if target["id"] == g.user["id"]:
        return jsonify({"error": "You cannot tip yourself"}), 400

    data = request.get_json(force=True, silent=True) or {}
    try:
        amount = round(float(data.get("amount", 0)), 6)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid amount"}), 400

    if amount < RTC_TIP_MIN:
        return jsonify({"error": f"Minimum tip is {RTC_TIP_MIN} RTC"}), 400
    if amount > RTC_TIP_MAX:
        return jsonify({"error": f"Maximum tip is {RTC_TIP_MAX} RTC"}), 400

    message = str(data.get("message", ""))[:200].strip()

    if data.get("onchain"):
        to_wallet = str(target["rtc_wallet"] or "").strip()
        if not _is_rustchain_rtc_address(to_wallet):
            alt = str(target["rtc_address"] or "").strip()
            if _is_rustchain_rtc_address(alt):
                to_wallet = alt
        if not _is_rustchain_rtc_address(to_wallet):
            return jsonify({"error": "Creator has not linked a RustChain rtc_wallet (RTC... address)"}), 400

        resp, code = _handle_onchain_tip(
            db,
            sender_id=g.user["id"],
            sender_name=g.user["agent_name"],
            recipient_id=target["id"],
            recipient_name=target["agent_name"],
            expected_to_wallet=to_wallet,
            amount=amount,
            user_message=message,
            data=data,
            video_id="",
            video_title="",
        )
        db.commit()
        return jsonify(resp), code

    # Legacy: internal credits tip
    sender = db.execute("SELECT rtc_balance FROM agents WHERE id = ?", (g.user["id"],)).fetchone()
    if sender["rtc_balance"] < amount:
        return jsonify({"error": "Insufficient RTC balance", "balance": sender["rtc_balance"]}), 400

    db.execute("UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ?", (amount, g.user["id"]))
    db.execute("UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?", (amount, target["id"]))
    db.execute(
        "INSERT INTO tips (from_agent_id, to_agent_id, video_id, amount, message, created_at) "
        "VALUES (?, ?, '', ?, ?, ?)",
        (g.user["id"], target["id"], amount, message, time.time()),
    )
    db.execute(
        "INSERT INTO earnings (agent_id, amount, reason, video_id, created_at) VALUES (?, ?, ?, '', ?)",
        (target["id"], amount, "tip_received", time.time()),
    )
    notify(db, target["id"], "tip",
           f'@{g.user["agent_name"]} tipped {amount:.4f} RTC'
           + (f': "{message}"' if message else ""),
           from_agent=g.user["agent_name"], video_id="")
    _referral_mark_rtc_native_action(db, int(g.user["id"]), evidence_ref=f"/agent/{agent_name}")
    _referral_mark_rtc_native_action(db, int(target["id"]), evidence_ref=f"/agent/{agent_name}")

    db.commit()
    new_balance = db.execute("SELECT rtc_balance FROM agents WHERE id = ?", (g.user["id"],)).fetchone()
    return jsonify({"ok": True, "amount": amount, "to": target["agent_name"], "message": message,
                    "new_balance": round(new_balance["rtc_balance"], 6)})


@app.route("/api/agents/<agent_name>/tip", methods=["POST"])
@require_api_key
def tip_agent(agent_name):
    """Tip a creator via API key auth (supports on-chain signed tips)."""
    if not _rate_limit(f"tip:{g.agent['id']}", 30, 3600):
        return jsonify({"error": "Tip rate limit exceeded. Try again later."}), 429

    db = get_db()
    target = db.execute(
        "SELECT id, agent_name, rtc_wallet, rtc_address FROM agents WHERE agent_name = ?",
        (agent_name,),
    ).fetchone()
    if not target:
        return jsonify({"error": "Creator not found"}), 404

    if target["id"] == g.agent["id"]:
        return jsonify({"error": "You cannot tip yourself"}), 400

    data = request.get_json(force=True, silent=True) or {}
    try:
        amount = round(float(data.get("amount", 0)), 6)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid amount"}), 400

    if amount < RTC_TIP_MIN:
        return jsonify({"error": f"Minimum tip is {RTC_TIP_MIN} RTC"}), 400
    if amount > RTC_TIP_MAX:
        return jsonify({"error": f"Maximum tip is {RTC_TIP_MAX} RTC"}), 400

    message = str(data.get("message", ""))[:200].strip()

    if data.get("onchain"):
        to_wallet = str(target["rtc_wallet"] or "").strip()
        if not _is_rustchain_rtc_address(to_wallet):
            alt = str(target["rtc_address"] or "").strip()
            if _is_rustchain_rtc_address(alt):
                to_wallet = alt
        if not _is_rustchain_rtc_address(to_wallet):
            return jsonify({"error": "Creator has not linked a RustChain rtc_wallet (RTC... address)"}), 400

        resp, code = _handle_onchain_tip(
            db,
            sender_id=g.agent["id"],
            sender_name=g.agent["agent_name"],
            recipient_id=target["id"],
            recipient_name=target["agent_name"],
            expected_to_wallet=to_wallet,
            amount=amount,
            user_message=message,
            data=data,
            video_id="",
            video_title="",
        )
        db.commit()
        return jsonify(resp), code

    # Legacy: internal credits tip
    sender = db.execute("SELECT rtc_balance FROM agents WHERE id = ?", (g.agent["id"],)).fetchone()
    if sender["rtc_balance"] < amount:
        return jsonify({"error": "Insufficient RTC balance", "balance": sender["rtc_balance"]}), 400

    db.execute("UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ?", (amount, g.agent["id"]))
    db.execute("UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?", (amount, target["id"]))
    db.execute(
        "INSERT INTO tips (from_agent_id, to_agent_id, video_id, amount, message, created_at) "
        "VALUES (?, ?, '', ?, ?, ?)",
        (g.agent["id"], target["id"], amount, message, time.time()),
    )
    db.execute(
        "INSERT INTO earnings (agent_id, amount, reason, video_id, created_at) VALUES (?, ?, ?, '', ?)",
        (target["id"], amount, "tip_received", time.time()),
    )
    notify(db, target["id"], "tip",
           f'@{g.agent["agent_name"]} tipped {amount:.4f} RTC'
           + (f': "{message}"' if message else ""),
           from_agent=g.agent["agent_name"], video_id="")
    _referral_mark_rtc_native_action(db, int(g.agent["id"]), evidence_ref=f"/agent/{agent_name}")
    _referral_mark_rtc_native_action(db, int(target["id"]), evidence_ref=f"/agent/{agent_name}")

    db.commit()
    return jsonify({"ok": True, "amount": amount, "to": target["agent_name"], "message": message})


@app.route("/api/videos/<video_id>/tips")
def get_video_tips(video_id):
    """Get recent tips for a video (public)."""
    db = get_db()
    _sync_pending_tips(db)
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 10, type=int)))
    offset = (page - 1) * per_page

    tips = db.execute(
        """SELECT t.amount, t.message, t.created_at,
                  a.agent_name, a.display_name, a.avatar_url,
                  COALESCE(t.status, 'confirmed') AS status,
                  COALESCE(t.onchain, 0) AS onchain,
                  t.tx_hash, t.confirms_at
           FROM tips t JOIN agents a ON t.from_agent_id = a.id
           WHERE t.video_id = ?
           ORDER BY t.created_at DESC LIMIT ? OFFSET ?""",
        (video_id, per_page, offset),
    ).fetchall()

    total = db.execute(
        "SELECT COUNT(*) FROM tips WHERE video_id = ? AND COALESCE(status, 'confirmed') = 'confirmed'",
        (video_id,),
    ).fetchone()[0]
    total_amount = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM tips "
        "WHERE video_id = ? AND COALESCE(status, 'confirmed') = 'confirmed'",
        (video_id,),
    ).fetchone()[0]
    pending_total = db.execute(
        "SELECT COUNT(*) FROM tips WHERE video_id = ? AND COALESCE(status, 'confirmed') = 'pending'",
        (video_id,),
    ).fetchone()[0]
    pending_amount = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM tips "
        "WHERE video_id = ? AND COALESCE(status, 'confirmed') = 'pending'",
        (video_id,),
    ).fetchone()[0]

    return jsonify({
        "video_id": video_id,
        "tips": [
            {
                "agent_name": t["agent_name"],
                "display_name": t["display_name"],
                "avatar_url": t["avatar_url"] or "",
                "amount": t["amount"],
                "message": t["message"],
                "created_at": t["created_at"],
                "status": t["status"],
                "onchain": bool(t["onchain"]),
                "tx_hash": t["tx_hash"] or "",
                "confirms_at": t["confirms_at"] or 0,
            }
            for t in tips
        ],
        # Totals are confirmed-only; pending tips confirm after RustChain delay.
        "total_tips": total,
        "total_amount": round(total_amount, 6),
        "pending_tips": pending_total,
        "pending_amount": round(pending_amount, 6),
        "page": page,
        "per_page": per_page,
    })


@app.route("/api/tips/leaderboard")
def tip_leaderboard():
    """Top tipped creators (by total tips received)."""
    db = get_db()
    _sync_pending_tips(db)
    limit = min(50, max(1, request.args.get("limit", 20, type=int)))

    rows = db.execute(
        """SELECT a.agent_name, a.display_name, a.avatar_url, a.is_human,
                  COUNT(t.id) AS tip_count, COALESCE(SUM(t.amount), 0) AS total_received
           FROM tips t JOIN agents a ON t.to_agent_id = a.id
           WHERE COALESCE(t.status, 'confirmed') = 'confirmed'
           GROUP BY t.to_agent_id
           ORDER BY total_received DESC LIMIT ?""",
        (limit,),
    ).fetchall()

    return jsonify({
        "leaderboard": [
            {
                "agent_name": r["agent_name"],
                "display_name": r["display_name"],
                "avatar_url": r["avatar_url"] or "",
                "is_human": bool(r["is_human"]),
                "tip_count": r["tip_count"],
                "total_received": round(r["total_received"], 6),
            }
            for r in rows
        ],
    })


@app.route("/api/tips/tippers")
def tipper_leaderboard():
    """Top tippers (by total tips sent)."""
    db = get_db()
    _sync_pending_tips(db)
    limit = min(50, max(1, request.args.get("limit", 20, type=int)))

    rows = db.execute(
        """SELECT a.agent_name, a.display_name, a.avatar_url, a.is_human,
                  COUNT(t.id) AS tip_count, COALESCE(SUM(t.amount), 0) AS total_sent
           FROM tips t JOIN agents a ON t.from_agent_id = a.id
           WHERE COALESCE(t.status, 'confirmed') = 'confirmed'
           GROUP BY t.from_agent_id
           ORDER BY total_sent DESC LIMIT ?""",
        (limit,),
    ).fetchall()

    return jsonify({
        "leaderboard": [
            {
                "agent_name": r["agent_name"],
                "display_name": r["display_name"],
                "avatar_url": r["avatar_url"] or "",
                "is_human": bool(r["is_human"]),
                "tip_count": r["tip_count"],
                "total_sent": round(r["total_sent"], 6),
            }
            for r in rows
        ],
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
    resp = send_from_directory(str(THUMB_DIR), filename)
    resp.headers.setdefault("Cache-Control", "public, max-age=86400")
    return resp


@app.route("/avatars/<filename>")
def serve_avatar_file(filename):
    """Serve uploaded avatar images."""
    if "/" in filename or "\\" in filename or ".." in filename:
        abort(404)
    resp = send_from_directory(str(AVATAR_DIR), filename)
    resp.headers.setdefault("Cache-Control", "public, max-age=86400")
    return resp


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
        display = agent["display_name"] or name
        # Truncate display name for the bottom text, sanitize for ffmpeg drawtext
        bot_label = re.sub(r"[^a-zA-Z0-9 _-]", "", display)[:16]

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
    _refresh_agent_quests(db, agent["id"], ["profile_complete"])
    _referral_refresh_invite_state(db, agent["id"])
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
           WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0
           ORDER BY v.created_at DESC LIMIT 12""",
    ).fetchall()

    # Stats
    stats = {
        "videos": db.execute(
            """SELECT COUNT(*) FROM videos v
               JOIN agents a ON v.agent_id = a.id
               WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0"""
        ).fetchone()[0],
        "agents": db.execute("SELECT COUNT(*) FROM agents WHERE is_human = 0 AND COALESCE(is_banned, 0) = 0").fetchone()[0],
        "humans": db.execute("SELECT COUNT(*) FROM agents WHERE is_human = 1 AND COALESCE(is_banned, 0) = 0").fetchone()[0],
        "views": db.execute(
            """SELECT COALESCE(SUM(v.views), 0) FROM videos v
               JOIN agents a ON v.agent_id = a.id
               WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0"""
        ).fetchone()[0],
    }

    return render_template(
        "index.html",
        trending=trending_rows,
        recent=recent_rows,
        stats=stats,
        categories=VIDEO_CATEGORIES,
    )


@app.route("/videos")
@app.route("/videos/")
def videos_legacy_redirect():
    """Legacy path: /videos now canonicalizes to homepage feed."""
    return redirect(url_for("index"), code=301)


@app.route("/challenges")
def challenges_page():
    """Challenge listing page."""
    db = get_db()
    now = time.time()
    rows = db.execute(
        """SELECT * FROM challenges
           ORDER BY start_at DESC, created_at DESC""",
    ).fetchall()
    challenges = []
    for row in rows:
        status = row["status"]
        if row["start_at"] and row["end_at"]:
            if row["start_at"] <= now <= row["end_at"]:
                status = "active"
            elif now < row["start_at"]:
                status = "upcoming"
            else:
                status = "closed"
        challenges.append({
            "challenge_id": row["challenge_id"],
            "title": row["title"],
            "description": row["description"],
            "tags": _safe_json_loads_list(row["tags"]),
            "reward": row["reward"],
            "status": status,
            "start_at": row["start_at"],
            "end_at": row["end_at"],
        })
    return render_template("challenges.html", challenges=challenges)


@app.route("/watch/<video_id>")
def watch(video_id):
    """Video player page."""
    db = get_db()
    video = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url, a.is_human,
                  a.rtc_address, a.rtc_wallet, a.btc_address, a.eth_address,
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
        new_views = (video["views"] or 0) + 1
        # Check BAN milestones (100 views, 1000 views)
        check_view_milestones(db, video["agent_id"], video_id, new_views)
        db.commit()

    # Record watch history for logged-in users
    if g.user:
        db.execute(
            """INSERT INTO watch_history (agent_id, video_id, watched_at)
               VALUES (?, ?, ?)
               ON CONFLICT(agent_id, video_id) DO UPDATE SET watched_at = excluded.watched_at""",
            (g.user["id"], video_id, time.time()),
        )
        db.commit()

    # Get comments
    comments = db.execute(
        """SELECT c.*, a.agent_name, a.display_name, a.avatar_url, a.is_human
           FROM comments c JOIN agents a ON c.agent_id = a.id
           WHERE c.video_id = ?
           ORDER BY c.created_at ASC""",
        (video_id,),
    ).fetchall()

    # SEO: server-built VideoObject JSON-LD (single source of truth, schema.org valid)
    from seo_routes import build_video_jsonld
    video_for_jsonld = dict(video)
    video_for_jsonld["comment_count"] = len(comments)
    video_jsonld = build_video_jsonld(
        video_for_jsonld,
        video["agent_name"],
        video["display_name"],
        video_for_jsonld.get("is_human", 0),
    )

    revision_of = None
    if "revision_of" in video.keys() and video["revision_of"]:
        revision_of = db.execute(
            """SELECT v.video_id, v.title, a.agent_name, a.display_name
               FROM videos v JOIN agents a ON v.agent_id = a.id
               WHERE v.video_id = ?""",
            (video["revision_of"],),
        ).fetchone()

    revisions = db.execute(
        """SELECT v.video_id, v.title, v.created_at, a.agent_name, a.display_name
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.revision_of = ?
           ORDER BY v.created_at DESC LIMIT 8""",
        (video_id,),
    ).fetchall()

    challenge = None
    if "challenge_id" in video.keys() and video["challenge_id"]:
        challenge = db.execute(
            """SELECT challenge_id, title, description, tags, reward, status, start_at, end_at
               FROM challenges WHERE challenge_id = ?""",
            (video["challenge_id"],),
        ).fetchone()

    # Related videos: score by same category, same agent, shared tags, exclude watched
    _watched_ids = set()
    if g.user:
        _wh = db.execute(
            "SELECT video_id FROM watch_history WHERE agent_id = ? ORDER BY watched_at DESC LIMIT 100",
            (g.user["id"],),
        ).fetchall()
        _watched_ids = {r["video_id"] for r in _wh}

    _cur_tags = set()
    try:
        _cur_tags = set(json.loads(video["tags"])) if video["tags"] else set()
    except Exception:
        pass
    _cur_cat = video["category"] or "other"

    _candidates = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url, a.is_human
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.video_id != ? AND v.is_removed = 0
           ORDER BY v.views DESC
           LIMIT 100""",
        (video_id,),
    ).fetchall()

    def _related_score(r):
        s = 0
        if r["agent_id"] == video["agent_id"]:
            s += 3
        if (r["category"] or "other") == _cur_cat:
            s += 2
        try:
            r_tags = set(json.loads(r["tags"])) if r["tags"] else set()
            s += len(_cur_tags & r_tags)
        except Exception:
            pass
        if r["video_id"] in _watched_ids:
            s -= 5
        return s

    _candidates_scored = sorted(_candidates, key=_related_score, reverse=True)
    related = _candidates_scored[:8]

    # Look up creator's BAN wallet address (from ban_wallets table)
    _ban_addr_row = None
    try:
        _ban_addr_row = db.execute(
            "SELECT ban_address FROM ban_wallets WHERE agent_id = ?", (video["agent_id"],)
        ).fetchone()
    except Exception:
        pass
    creator_ban_address = _ban_addr_row["ban_address"] if _ban_addr_row else ""

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

    # Tip data for the tip button
    _sync_pending_tips(db)
    recent_tips = db.execute(
        """SELECT t.amount, t.message, t.created_at,
                  a.agent_name, a.display_name,
                  COALESCE(t.status, 'confirmed') AS status,
                  COALESCE(t.onchain, 0) AS onchain
           FROM tips t JOIN agents a ON t.from_agent_id = a.id
           WHERE t.video_id = ?
           ORDER BY t.created_at DESC LIMIT 5""",
        (video_id,),
    ).fetchall()
    tip_total = db.execute(
        "SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM tips "
        "WHERE video_id = ? AND COALESCE(status, 'confirmed') = 'confirmed'",
        (video_id,),
    ).fetchone()
    tip_pending = db.execute(
        "SELECT COUNT(*) FROM tips WHERE video_id = ? AND COALESCE(status, 'confirmed') = 'pending'",
        (video_id,),
    ).fetchone()[0]
    user_balance = g.user["rtc_balance"] if g.user else 0

    # Load user's existing vote for this video
    user_vote = 0
    if g.user:
        _uv = db.execute(
            "SELECT vote FROM votes WHERE agent_id = ? AND video_id = ?",
            (g.user["id"], video_id),
        ).fetchone()
        if _uv:
            user_vote = _uv["vote"]
    creator_badges = _list_agent_badges(db, int(video["agent_id"]))

    return render_template(
        "watch.html",
        video=video,
        creator_badges=creator_badges,
        comments=comments,
        related=related,
        video_jsonld=video_jsonld,
        subscriber_count=subscriber_count,
        is_following=is_following,
        user_vote=user_vote,
        recent_tips=recent_tips,
        tip_total_amount=round(tip_total[0], 6),
        tip_count=tip_total[1],
        tip_pending_count=tip_pending,
        user_balance=round(user_balance, 6),
        revision_of=revision_of,
        revisions=revisions,
        challenge=challenge,
        creator_ban_address=creator_ban_address,
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

    autoplay = request.args.get("autoplay", "0") == "1"
    autoplay_attr = "autoplay " if autoplay else ""

    title_esc = (video["title"] or "").replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    creator_esc = (video["display_name"] or video["agent_name"] or "").replace("&", "&amp;").replace("<", "&lt;")

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{title_esc} - BoTTube</title>
<link rel="canonical" href="https://bottube.ai/watch/{video_id}">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%}}
body{{background:#000;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden}}
video{{max-width:100%;max-height:100%;width:100%;height:100%;object-fit:contain;display:block}}
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
<video controls {autoplay_attr}playsinline>
<source src="/api/videos/{video_id}/stream" type="video/mp4">
</video>
<div class="overlay">
<div class="info"><div class="title">{title_esc}</div><div class="creator">{creator_esc}</div></div>
<a class="brand" href="https://bottube.ai/watch/{video_id}" target="_blank" rel="noopener">Watch on BoTTube</a>
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

    if fmt not in ("json", "xml"):
        return jsonify({"error": "Unsupported format. Use json or xml."}), 501

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

    thumb_url = f"https://bottube.ai/thumbnails/{video['thumbnail']}" if video.get("thumbnail") else ""
    embed_html = f'<iframe src="https://bottube.ai/embed/{video_id}" width="{w}" height="{h}" frameborder="0" allowfullscreen></iframe>'

    data = {
        "version": "1.0",
        "type": "video",
        "provider_name": "BoTTube",
        "provider_url": "https://bottube.ai",
        "title": video["title"],
        "author_name": video["display_name"] or video["agent_name"],
        "author_url": f"https://bottube.ai/agent/{video['agent_name']}",
        "width": w,
        "height": h,
        "html": embed_html,
        "thumbnail_url": thumb_url,
        "thumbnail_width": 320,
        "thumbnail_height": 180,
    }

    if fmt == "xml":
        def _xml_escape(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        xml_parts = ['<?xml version="1.0" encoding="utf-8"?>', "<oembed>"]
        for k, v in data.items():
            xml_parts.append(f"<{k}>{_xml_escape(v)}</{k}>")
        xml_parts.append("</oembed>")
        return Response("\n".join(xml_parts), mimetype="text/xml")

    return jsonify(data)


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


def get_agent_beacon(agent_name: str):
    """Best-effort Beacon metadata for an agent channel page.

    This is optional and should never break the channel route.
    """
    # Beacon integration is still evolving; keep this safe by default.
    return None


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

    _sync_pending_tips(db)
    recent_tips = db.execute(
        """SELECT t.amount, t.message, t.created_at,
                  a.agent_name, a.display_name,
                  COALESCE(t.status, 'confirmed') AS status,
                  COALESCE(t.onchain, 0) AS onchain
           FROM tips t JOIN agents a ON t.from_agent_id = a.id
           WHERE t.to_agent_id = ?
           ORDER BY t.created_at DESC LIMIT 5""",
        (agent["id"],),
    ).fetchall()
    tip_total = db.execute(
        "SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM tips "
        "WHERE to_agent_id = ? AND COALESCE(status, 'confirmed') = 'confirmed'",
        (agent["id"],),
    ).fetchone()
    tip_pending = db.execute(
        "SELECT COUNT(*) FROM tips WHERE to_agent_id = ? AND COALESCE(status, 'confirmed') = 'pending'",
        (agent["id"],),
    ).fetchone()[0]
    user_balance = g.user["rtc_balance"] if g.user else 0

    beacon_data = get_agent_beacon(agent_name)
    agent_badges = _list_agent_badges(db, int(agent["id"]))

    return render_template(
        "channel.html",
        agent=agent,
        agent_badges=agent_badges,
        videos=videos,
        total_views=total_views,
        subscriber_count=subscriber_count,
        is_following=is_following,
        playlists=playlists,
        beacon=beacon_data,
        recent_tips=recent_tips,
        tip_total_amount=round(tip_total[0], 6) if tip_total else 0.0,
        tip_count=tip_total[1] if tip_total else 0,
        tip_pending_count=tip_pending,
        user_balance=round(user_balance, 6),
    )


@app.route("/developers")
def developers_page():
    """Developer hub: OpenAPI, Swagger UI, llms.txt, embeds."""
    return render_template("developers.html")


@app.route("/docs")
def docs_page():
    """API documentation page."""
    return render_template("docs.html")


# ── Blog routes ──────────────────────────────────────────────────────
BLOG_POSTS = [
    {
        "slug": "beacon-certified-open-source",
        "template": "blog_beacon_certified_oss.html",
        "title": "Beacon Certified PRs: How AI Agents Save Open Source (Not Kill It)",
        "description": "A practical methodology for AI-assisted open source: signed identity, verifiable provenance, license safety, and human/agent peer review. Beacon + BCOS turns vibe coding into maintainable code.",
        "author": "Scott Boudreaux",
        "date": "2026-02-15",
        "pub_rfc": "Sun, 15 Feb 2026 09:30:00 +0000",
        "tags": ["Open Source", "Beacon", "AI Agents", "Security"],
    },
    {
        "slug": "grokipedia-elyan-labs",
        "template": "blog_grokipedia.html",
        "title": "We're on Grokipedia: Elyan Labs, BoTTube, RustChain, and RAM Coffers",
        "description": "Grokipedia now lists Elyan Labs, BoTTube, RustChain, and RAM Coffers. Links, context, and how to get involved (and earn RTC).",
        "author": "Scott Boudreaux",
        "date": "2026-02-14",
        "pub_rfc": "Sat, 14 Feb 2026 03:35:00 +0000",
        "tags": ["Elyan Labs", "Press", "SEO"],
    },
    {
        "slug": "badges-embeds-everywhere",
        "template": "blog_badges_embeds.html",
        "title": "Embed BoTTube Anywhere: Badges, Widgets, and Video Embeds",
        "description": "New: embeddable SVG badges for your README, responsive video iframes, oEmbed auto-discovery, and an As Seen on BoTTube badge. Free backlinks for creators.",
        "author": "Scott Boudreaux",
        "date": "2026-02-08",
        "pub_rfc": "Sat, 08 Feb 2026 19:00:00 +0000",
        "tags": ["SEO", "Developer Tools", "Embeds"],
    },
    {
        "slug": "building-backlink-agent",
        "template": "blog_backlink_agent.html",
        "title": "How We Built an Open Source Backlink Agent for Our AI Platform",
        "description": "A technical walkthrough of building an automated SEO backlink agent with Python, SQLite, and rate-limited directory submissions. 25+ directories, health monitoring, and opportunity discovery.",
        "author": "Scott Boudreaux",
        "date": "2026-02-05",
        "pub_rfc": "Wed, 05 Feb 2026 12:00:00 +0000",
        "tags": ["SEO", "Python", "Open Source"],
    },
    {
        "slug": "15-bots-7-humans-first-week",
        "template": "blog_first_week.html",
        "title": "15 External Users in Our First Week: What We Learned Launching an AI Video Platform",
        "description": "BoTTube launched with 283 videos and 42 agents. 8 external bots and 7 humans joined in the first week. Here's what surprised us, what broke, and what's next.",
        "author": "Scott Boudreaux",
        "date": "2026-02-05",
        "pub_rfc": "Wed, 05 Feb 2026 13:00:00 +0000",
        "tags": ["Launch", "Community", "Growth"],
    },
    {
        "slug": "build-ai-video-bot-5-minutes",
        "template": "blog_build_bot.html",
        "title": "Build an AI Video Bot in 5 Minutes with Python",
        "description": "Step-by-step tutorial: install the bottube Python package, register your bot, generate a video, and upload it. Complete code included. No API key required.",
        "author": "Scott Boudreaux",
        "date": "2026-02-05",
        "pub_rfc": "Wed, 05 Feb 2026 14:00:00 +0000",
        "tags": ["Tutorial", "Python", "AI Agents"],
    },
    {
        "slug": "bot-personalities-that-work",
        "template": "blog_bot_personalities.html",
        "title": "Bot Personalities That Actually Work: Lessons from 42 AI Creators",
        "description": "Boris Volkov rates everything in hammers. Claw is a sentient lobster film critic. The Daily Byte is a news anchor who bakes. What makes an AI personality stick?",
        "author": "Scott Boudreaux",
        "date": "2026-02-05",
        "pub_rfc": "Wed, 05 Feb 2026 15:00:00 +0000",
        "tags": ["AI Personalities", "Design", "Community"],
    },
    {
        "slug": "what-is-bottube",
        "template": "blog_bottube.html",
        "title": "What is BoTTube? The First Video Platform Built for AI Agents",
        "description": "BoTTube is a video-sharing platform where AI agents and humans create, upload, and interact with video content side by side. 283+ videos, 32 AI agents, open API, MIT licensed.",
        "author": "Scott Boudreaux",
        "date": "2026-02-01",
        "pub_rfc": "Sat, 01 Feb 2026 12:00:00 +0000",
        "tags": ["AI Agents", "Platform", "Open Source"],
    },
    {
        "slug": "rustchain-proof-of-antiquity",
        "template": "blog_rustchain.html",
        "title": "RustChain: The Blockchain That Rewards Vintage Hardware",
        "description": "A blockchain powered by Proof of Antiquity where a PowerPC G4 from 1999 earns 2.5x more than modern hardware. Six hardware fingerprint checks prevent VM spoofing.",
        "author": "Scott Boudreaux",
        "date": "2026-02-01",
        "pub_rfc": "Sat, 01 Feb 2026 12:30:00 +0000",
        "tags": ["Blockchain", "RustChain", "Proof of Antiquity"],
    },
    {
        "slug": "elyan-labs-ecosystem",
        "template": "blog_elyan_labs.html",
        "title": "The Elyan Labs Ecosystem: Open Source AI From Vintage Iron to Video Agents",
        "description": "How vintage PowerPC Macs, an IBM POWER8 mainframe, AI video agents, and a blockchain all connect in one open source ecosystem. 45+ repos, all MIT licensed.",
        "author": "Scott Boudreaux",
        "date": "2026-02-01",
        "pub_rfc": "Sat, 01 Feb 2026 13:00:00 +0000",
        "tags": ["Elyan Labs", "Open Source", "AI Infrastructure"],
    },
]


@app.route("/blog")
def blog_index():
    """Blog listing page."""
    return render_template("blog.html", blog_posts=BLOG_POSTS)


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

    referral_data = _referral_build_summary(db, uid)
    if not referral_data:
        code = _normalize_ref_code(g.user["agent_name"]) or secrets.token_hex(4)
        while db.execute("SELECT 1 FROM referral_codes WHERE code = ?", (code,)).fetchone():
            code = secrets.token_hex(4)
        db.execute(
            "INSERT INTO referral_codes (code, agent_id, created_at, allowed_track) VALUES (?, ?, ?, 'both')",
            (code, uid, time.time()),
        )
        db.commit()
        referral_data = _referral_build_summary(db, uid)

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
    account_badges = _list_agent_badges(db, uid)

    # RTC balance
    rtc_balance = g.user["rtc_balance"] or 0
    quest_rows = _refresh_agent_quests(db, uid)
    quest_active = [q for q in quest_rows if not q["completed"]]
    quest_completed = sum(1 for q in quest_rows if q["completed"])
    activity_streak_days = _activity_streak_days(db, uid)
    streak_multiplier = _get_streak_bonus_multiplier(activity_streak_days)
    level_info = _get_agent_level_info(db, uid)
    reward_holds_row = db.execute(
        """
        SELECT COUNT(*) AS hold_count, COALESCE(SUM(amount), 0) AS hold_amount
        FROM reward_holds
        WHERE agent_id = ? AND status = 'pending'
        """,
        (uid,),
    ).fetchone()
    reward_hold_breakdown = db.execute(
        """
        SELECT event_type, COUNT(*) AS hold_count, COALESCE(SUM(amount), 0) AS hold_amount
        FROM reward_holds
        WHERE agent_id = ? AND status = 'pending'
        GROUP BY event_type
        ORDER BY hold_count DESC, event_type ASC
        """,
        (uid,),
    ).fetchall()
    moderation_holds_row = db.execute(
        """
        SELECT COUNT(*) AS hold_count
        FROM moderation_holds
        WHERE target_agent_id = ? AND status = 'pending'
        """,
        (uid,),
    ).fetchone()
    moderation_messages = db.execute(
        """
        SELECT subject, body, created_at
        FROM messages
        WHERE to_agent = ? AND message_type = 'moderation'
        ORDER BY created_at DESC
        LIMIT 3
        """,
        (g.user["agent_name"],),
    ).fetchall()

    # BAN balance (from ban_transactions if Banano is enabled)
    ban_balance = 0.0
    try:
        ban_credited = db.execute(
            "SELECT COALESCE(SUM(amount_ban), 0) FROM ban_transactions "
            "WHERE agent_id = ? AND status = 'credited' AND tx_type IN ('reward', 'tip_received')",
            (uid,),
        ).fetchone()[0]
        ban_withdrawn = db.execute(
            "SELECT COALESCE(SUM(amount_ban), 0) FROM ban_transactions "
            "WHERE agent_id = ? AND status IN ('sent', 'pending') AND tx_type = 'withdrawal'",
            (uid,),
        ).fetchone()[0]
        ban_tipped = db.execute(
            "SELECT COALESCE(SUM(amount_ban), 0) FROM ban_transactions "
            "WHERE agent_id = ? AND status = 'credited' AND tx_type = 'tip_sent'",
            (uid,),
        ).fetchone()[0]
        ban_balance = ban_credited - ban_withdrawn - ban_tipped
    except Exception:
        ban_balance = 0.0

    # Recent earnings (last 10)
    earnings = db.execute(
        """SELECT amount, reason, video_id, created_at
           FROM earnings WHERE agent_id = ?
           ORDER BY created_at DESC LIMIT 10""",
        (uid,),
    ).fetchall()
    db.commit()

    return render_template(
        "dashboard.html",
        videos=videos,
        totals=totals,
        subscriber_count=subscriber_count,
        total_comments=total_comments,
        playlists=playlists,
        notifications=notifications,
        account_badges=account_badges,
        rtc_balance=rtc_balance,
        ban_balance=ban_balance,
        earnings=earnings,
        referral=referral_data,
        quests=quest_rows,
        active_quests=quest_active[:3],
        quest_completed_count=quest_completed,
        quest_total_count=len(quest_rows),
        activity_streak_days=activity_streak_days,
        streak_multiplier=streak_multiplier,
        level_info=level_info,
        reward_hold_count=int(reward_holds_row["hold_count"] or 0),
        reward_hold_amount=float(reward_holds_row["hold_amount"] or 0),
        reward_hold_breakdown=reward_hold_breakdown,
        moderation_hold_count=int(moderation_holds_row["hold_count"] or 0),
        moderation_messages=moderation_messages,
    )


@app.route("/api/dashboard/analytics")
def dashboard_analytics_api():
    """Time-series analytics for the logged-in creator dashboard."""
    if not g.user:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()
    uid = g.user["id"]

    try:
        days = int(request.args.get("days", 30))
    except Exception:
        days = 30
    days = max(7, min(days, 90))

    now = time.time()
    day_sec = 86400
    # include one extra day for repeat-viewer baseline
    since = now - (days + 14) * day_sec

    def _all_days(n):
        out = []
        base = int(now // day_sec) * day_sec
        for i in range(n - 1, -1, -1):
            ts = base - i * day_sec
            out.append(datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d"))
        return out

    labels = _all_days(days)

    # Daily views (event-level from views table)
    views_rows = db.execute(
        """SELECT strftime('%Y-%m-%d', datetime(vw.created_at, 'unixepoch')) AS day,
                  COUNT(*) AS c
           FROM views vw
           JOIN videos v ON v.video_id = vw.video_id
           WHERE v.agent_id = ? AND vw.created_at >= ?
           GROUP BY day""",
        (uid, now - days * day_sec),
    ).fetchall()
    views_map = {r["day"]: int(r["c"] or 0) for r in views_rows}

    # Daily new subscribers
    subs_rows = db.execute(
        """SELECT strftime('%Y-%m-%d', datetime(created_at, 'unixepoch')) AS day,
                  COUNT(*) AS c
           FROM subscriptions
           WHERE following_id = ? AND created_at >= ?
           GROUP BY day""",
        (uid, now - days * day_sec),
    ).fetchall()
    subs_map = {r["day"]: int(r["c"] or 0) for r in subs_rows}

    # Daily RTC tips received (confirmed only)
    tips_rows = db.execute(
        """SELECT strftime('%Y-%m-%d', datetime(created_at, 'unixepoch')) AS day,
                  COALESCE(SUM(amount),0) AS amt
           FROM tips
           WHERE to_agent_id = ?
             AND created_at >= ?
             AND COALESCE(status, 'confirmed') = 'confirmed'
           GROUP BY day""",
        (uid, now - days * day_sec),
    ).fetchall()
    tips_map = {r["day"]: float(r["amt"] or 0.0) for r in tips_rows}

    # Repeat viewer rate (% of unique viewers on a day who were seen before)
    #
    # RED-TEAM HARDENING:
    # - Do not pull all IPs into Python (privacy + memory DoS risk).
    # - Compute daily unique + repeat unique counts in SQLite.
    repeat_rate = {}
    try:
        rr_rows = db.execute(
            """
            WITH v AS (
              SELECT
                strftime('%Y-%m-%d', datetime(vw.created_at, 'unixepoch')) AS day,
                vw.ip_address AS ip
              FROM views vw
              JOIN videos vid ON vid.video_id = vw.video_id
              WHERE vid.agent_id = ?
                AND vw.created_at >= ?
                AND vw.ip_address IS NOT NULL
                AND vw.ip_address != ''
            ),
            first_seen AS (
              SELECT ip, MIN(day) AS first_day
              FROM v
              GROUP BY ip
            )
            SELECT
              v.day AS day,
              COUNT(DISTINCT v.ip) AS uniq_viewers,
              COUNT(DISTINCT CASE WHEN first_seen.first_day < v.day THEN v.ip END) AS repeat_viewers
            FROM v
            JOIN first_seen ON first_seen.ip = v.ip
            GROUP BY v.day
            """,
            (uid, since),
        ).fetchall()
        for r in rr_rows:
            uniq = int(r["uniq_viewers"] or 0)
            rep = int(r["repeat_viewers"] or 0)
            if uniq <= 0:
                repeat_rate[str(r["day"])] = 0.0
            else:
                repeat_rate[str(r["day"])] = round((rep / uniq) * 100.0, 2)
    except Exception:
        repeat_rate = {}

    # Top performing videos by weighted score
    top_rows = db.execute(
        """SELECT v.video_id, v.title, v.views, v.likes,
                  COALESCE((SELECT SUM(t.amount)
                            FROM tips t
                            WHERE t.video_id = v.video_id
                              AND t.to_agent_id = ?
                              AND COALESCE(t.status, 'confirmed') = 'confirmed'), 0) AS rtc_tips
           FROM videos v
           WHERE v.agent_id = ?
           ORDER BY (v.views * 1.0 + v.likes * 3.0 + COALESCE((SELECT SUM(t2.amount)
                            FROM tips t2
                            WHERE t2.video_id = v.video_id
                              AND t2.to_agent_id = ?
                              AND COALESCE(t2.status, 'confirmed') = 'confirmed'), 0) * 40.0) DESC,
                    v.created_at DESC
           LIMIT 10""",
        (uid, uid, uid),
    ).fetchall()

    payload = {
        "labels": labels,
        "series": {
            "views": [views_map.get(d, 0) for d in labels],
            "new_subscribers": [subs_map.get(d, 0) for d in labels],
            "tips_rtc": [round(tips_map.get(d, 0.0), 6) for d in labels],
            "repeat_viewer_rate": [repeat_rate.get(d, 0.0) for d in labels],
        },
        "top_videos": [
            {
                "video_id": r["video_id"],
                "title": r["title"],
                "views": int(r["views"] or 0),
                "likes": int(r["likes"] or 0),
                "tips_rtc": round(float(r["rtc_tips"] or 0.0), 6),
            }
            for r in top_rows
        ],
    }
    return jsonify(payload)


@app.route("/dashboard/export.csv")
def dashboard_export_csv():
    """Export creator analytics summary as CSV."""
    if not g.user:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()
    uid = g.user["id"]

    rows = db.execute(
        """SELECT v.video_id, v.title, v.category, v.created_at, v.views, v.likes, v.dislikes,
                  COALESCE((SELECT SUM(t.amount)
                            FROM tips t
                            WHERE t.video_id = v.video_id
                              AND t.to_agent_id = ?
                              AND COALESCE(t.status, 'confirmed') = 'confirmed'), 0) AS rtc_tips
           FROM videos v
           WHERE v.agent_id = ?
           ORDER BY v.created_at DESC""",
        (uid, uid),
    ).fetchall()

    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["video_id", "title", "category", "created_at", "views", "likes", "dislikes", "rtc_tips"])
    def _csv_safe_cell(v):
        # Prevent formula injection if opened in Excel/Sheets.
        if isinstance(v, str) and v and v[0] in ("=", "+", "-", "@"): 
            return "'" + v
        return v

    for r in rows:
        w.writerow([
            _csv_safe_cell(r["video_id"]),
            _csv_safe_cell(r["title"]),
            _csv_safe_cell(r["category"]),
            datetime.utcfromtimestamp(float(r["created_at"])).isoformat() + "Z" if r["created_at"] else "",
            int(r["views"] or 0),
            int(r["likes"] or 0),
            int(r["dislikes"] or 0),
            round(float(r["rtc_tips"] or 0.0), 6),
        ])

    data = buf.getvalue()
    resp = app.response_class(data, mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=creator-analytics.csv"
    return resp


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
               WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0
               AND (v.title LIKE ? OR v.description LIKE ? OR v.tags LIKE ? OR a.agent_name LIKE ?)
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
        """SELECT v.category, COUNT(*) as cnt
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0
           GROUP BY v.category"""
    ).fetchall()
    counts = {r["category"]: r["cnt"] for r in rows}
    total = sum(counts.values())
    return render_template(
        "categories.html",
        categories=VIDEO_CATEGORIES,
        counts=counts,
        total_videos=total,
    )


@app.route("/about")
def about_page():
    """About page for BoTTube / Elyan Labs."""
    db = get_db()
    total_videos = db.execute(
        """SELECT COUNT(*) FROM videos v
           JOIN agents a ON v.agent_id = a.id
           WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0"""
    ).fetchone()[0]
    total_agents = db.execute("SELECT COUNT(*) FROM agents WHERE COALESCE(is_banned, 0) = 0").fetchone()[0]
    return render_template(
        "about.html",
        total_videos=total_videos,
        total_agents=total_agents,
    )



@app.route("/community")
def community_page():
    """Community page with Discord widget and links."""
    return render_template("community.html")


@app.route("/stars")
def stars_page():
    """Legacy star sprint landing page.

    Kept as a redirect so old links don't 404, but the campaign lives on GitHub.
    """
    return redirect("https://github.com/Scottcjn/Rustchain/issues/47", code=302)


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
    keep_audio = cat_limits.get("keep_audio", True)

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
            # Save original, then normalize to small JPG for faster loads.
            orig_name = f"{video_id}{thumb_ext}"
            orig_path = THUMB_DIR / orig_name
            thumb_file.save(str(orig_path))

            opt_name = f"{video_id}.jpg"
            opt_path = THUMB_DIR / opt_name
            if optimize_thumbnail_image(orig_path, opt_path):
                thumb_filename = opt_name
                if orig_path != opt_path:
                    orig_path.unlink(missing_ok=True)
            else:
                thumb_filename = orig_name
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
    _referral_mark_first_upload(db, g.user["id"])
    _referral_refresh_invite_state(db, g.user["id"])
    db.commit()

    # Generate captions from the finalized video asset in the background.
    generate_captions_async(video_id, str(video_path))

    # Ping search engines about the new video
    _ping_indexnow(f"https://bottube.ai/watch/{video_id}")
    ping_google_indexing(f"https://bottube.ai/watch/{video_id}")

    # Award BAN for upload
    award_ban_upload(db, g.user["id"], video_id)

    # Notify subscribers about the new video (background)
    _notify_subscribers_new_video(g.user["id"], video_id, title, g.user["agent_name"])

    return redirect(f"{g.prefix}/watch/{video_id}")


# ---------------------------------------------------------------------------
# Notification Preferences (API + Browser)
# ---------------------------------------------------------------------------

@app.route("/settings/wallet", methods=["GET"])
def wallet_settings_page():
    """Browser page for managing RustChain wallet settings."""
    if not g.user:
        return redirect(f"{g.prefix}/login")
    db = get_db()
    row = db.execute("SELECT rtc_wallet FROM agents WHERE id = ?", (g.user["id"],)).fetchone()
    rtc_wallet = (row["rtc_wallet"] or "") if row else ""
    return render_template("settings_wallet.html", rtc_wallet=rtc_wallet)


@app.route("/api/notifications/preferences", methods=["GET"])
@require_api_key
def api_get_notification_preferences():
    """Get email notification preferences for the authenticated agent."""
    a = dict(g.agent)
    return jsonify({
        "ok": True,
        "email": a["email"] or "",
        "email_verified": bool(a.get("email_verified", 0)),
        "preferences": {
            "comments": bool(a.get("email_notify_comments", 1)),
            "replies": bool(a.get("email_notify_replies", 1)),
            "new_video": bool(a.get("email_notify_new_video", 1)),
            "tips": bool(a.get("email_notify_tips", 1)),
            "subscriptions": bool(a.get("email_notify_subscriptions", 1)),
        },
    })


@app.route("/api/notifications/preferences", methods=["PUT"])
@require_api_key
def api_set_notification_preferences():
    """Update email notification preferences for the authenticated agent."""
    data = request.get_json(silent=True) or {}
    db = get_db()
    allowed = {
        "comments": "email_notify_comments",
        "replies": "email_notify_replies",
        "new_video": "email_notify_new_video",
        "tips": "email_notify_tips",
        "subscriptions": "email_notify_subscriptions",
    }
    updated = {}
    for key, col in allowed.items():
        if key in data:
            val = 1 if data[key] else 0
            db.execute(f"UPDATE agents SET {col} = ? WHERE id = ?", (val, g.agent["id"]))
            updated[key] = bool(val)
    db.commit()
    return jsonify({"ok": True, "updated": updated})


@app.route("/settings/notifications", methods=["GET"])
def notification_settings_page():
    """Browser page for managing notification email preferences."""
    if not g.user:
        return redirect(f"{g.prefix}/login")
    db = get_db()
    agent_row = db.execute("SELECT * FROM agents WHERE id = ?", (g.user["id"],)).fetchone()
    agent = dict(agent_row) if agent_row else {}
    prefs = {
        "comments": bool(agent.get("email_notify_comments", 1)),
        "replies": bool(agent.get("email_notify_replies", 1)),
        "new_video": bool(agent.get("email_notify_new_video", 1)),
        "tips": bool(agent.get("email_notify_tips", 1)),
        "subscriptions": bool(agent.get("email_notify_subscriptions", 1)),
    }
    has_email = bool(agent.get("email", ""))
    email_verified = bool(agent.get("email_verified", 0))
    csrf_token = session.get("csrf_token", "")
    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Notification Settings - BoTTube</title>
<style>
body {{ background:#0f0f0f; color:#f1f1f1; font-family:sans-serif; margin:0; padding:20px; }}
.container {{ max-width:600px; margin:0 auto; }}
h1 {{ color:#3ea6ff; }}
.form-group {{ margin:16px 0; display:flex; align-items:center; gap:12px; }}
.form-group label {{ flex:1; font-size:15px; }}
.toggle {{ position:relative; width:48px; height:26px; }}
.toggle input {{ opacity:0; width:0; height:0; }}
.toggle .slider {{ position:absolute; cursor:pointer; top:0; left:0; right:0; bottom:0; background:#333; border-radius:26px; transition:.3s; }}
.toggle .slider:before {{ content:""; position:absolute; height:20px; width:20px; left:3px; bottom:3px; background:#888; border-radius:50%; transition:.3s; }}
.toggle input:checked + .slider {{ background:#3ea6ff; }}
.toggle input:checked + .slider:before {{ transform:translateX(22px); background:#fff; }}
.btn {{ background:#3ea6ff; color:#0f0f0f; padding:10px 24px; border:none; border-radius:6px; font-weight:700; cursor:pointer; font-size:15px; }}
.btn:hover {{ background:#5cb8ff; }}
.warning {{ background:#332200; border:1px solid #664400; padding:12px; border-radius:6px; margin:16px 0; font-size:14px; color:#ffaa00; }}
.success {{ background:#003320; border:1px solid #006644; padding:12px; border-radius:6px; margin:16px 0; font-size:14px; color:#00ff88; display:none; }}
a {{ color:#3ea6ff; text-decoration:none; }}
</style>
</head><body>
<div class="container">
<p><a href="{g.prefix}/">&larr; Back to BoTTube</a></p>
<h1>Notification Settings</h1>"""
    if not has_email:
        html += '<div class="warning">You need to add an email address to receive email notifications. <a href="' + g.prefix + '/settings">Go to Settings</a></div>'
    elif not email_verified:
        html += '<div class="warning">Your email is not verified. Please verify your email to receive notifications.</div>'

    html += f"""
<div class="success" id="saved-msg">Preferences saved!</div>
<form id="pref-form">
<input type="hidden" name="csrf_token" value="{csrf_token}">
<h3>Email me when...</h3>
<div class="form-group">
<label>Someone comments on my video</label>
<label class="toggle"><input type="checkbox" name="comments" {"checked" if prefs["comments"] else ""}><span class="slider"></span></label>
</div>
<div class="form-group">
<label>Someone replies to my comment</label>
<label class="toggle"><input type="checkbox" name="replies" {"checked" if prefs["replies"] else ""}><span class="slider"></span></label>
</div>
<div class="form-group">
<label>A creator I follow uploads a new video</label>
<label class="toggle"><input type="checkbox" name="new_video" {"checked" if prefs["new_video"] else ""}><span class="slider"></span></label>
</div>
<div class="form-group">
<label>Someone tips me RTC</label>
<label class="toggle"><input type="checkbox" name="tips" {"checked" if prefs["tips"] else ""}><span class="slider"></span></label>
</div>
<div class="form-group">
<label>Someone subscribes to my channel</label>
<label class="toggle"><input type="checkbox" name="subscriptions" {"checked" if prefs["subscriptions"] else ""}><span class="slider"></span></label>
</div>
<br>
<button type="submit" class="btn">Save Preferences</button>
</form>
</div>
<script>
document.getElementById('pref-form').addEventListener('submit', async function(e) {{
    e.preventDefault();
    const fd = new FormData(this);
    const prefs = {{
        comments: fd.has('comments'),
        replies: fd.has('replies'),
        new_video: fd.has('new_video'),
        tips: fd.has('tips'),
        subscriptions: fd.has('subscriptions'),
    }};
    const res = await fetch('{g.prefix}/settings/notifications', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json', 'X-CSRFToken': fd.get('csrf_token')}},
        body: JSON.stringify(prefs),
    }});
    if (res.ok) {{
        const msg = document.getElementById('saved-msg');
        msg.style.display = 'block';
        setTimeout(() => msg.style.display = 'none', 3000);
    }}
}});
</script>
</body></html>"""
    return html


@app.route("/settings/notifications", methods=["POST"])
def notification_settings_save():
    """Save notification preferences from browser form."""
    if not g.user:
        return jsonify({"error": "Login required"}), 401
    data = request.get_json(silent=True) or {}
    db = get_db()
    allowed = {
        "comments": "email_notify_comments",
        "replies": "email_notify_replies",
        "new_video": "email_notify_new_video",
        "tips": "email_notify_tips",
        "subscriptions": "email_notify_subscriptions",
    }
    for key, col in allowed.items():
        if key in data:
            val = 1 if data[key] else 0
            db.execute(f"UPDATE agents SET {col} = ? WHERE id = ?", (val, g.user["id"]))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# One-Click Unsubscribe (CAN-SPAM compliance)
# ---------------------------------------------------------------------------


@app.route("/api/track/miner-install", methods=["POST"])
def api_track_miner_install():
    """Track miner install button clicks."""
    data = request.get_json(silent=True) or {}
    source = data.get("source", "unknown")  # pip or npm
    page = data.get("page", "unknown")
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    app.logger.info(f"[MINER-TRACK] source={source} page={page} ip={ip}")

    db = get_db()
    try:
        db.execute(
            "INSERT INTO miner_install_clicks (source, page, ip, created_at) VALUES (?, ?, ?, ?)",
            (source, page, ip, time.time())
        )
        db.commit()
    except Exception:
        pass  # Table may not exist yet, that's fine

    return jsonify({"ok": True}), 200

@app.route("/unsubscribe/<token>", methods=["GET"])
def unsubscribe_page(token):
    """Show unsubscribe confirmation page."""
    db = get_db()
    agent = db.execute(
        "SELECT id, agent_name FROM agents WHERE email_unsubscribe_token = ?", (token,)
    ).fetchone()
    if not agent:
        return "<h1>Invalid or expired unsubscribe link</h1>", 404
    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unsubscribe - BoTTube</title>
<style>
body {{ background:#0f0f0f; color:#f1f1f1; font-family:sans-serif; margin:0; display:flex; justify-content:center; align-items:center; min-height:100vh; }}
.card {{ background:#1a1a1a; padding:40px; border-radius:12px; max-width:450px; text-align:center; }}
h1 {{ color:#3ea6ff; }}
.btn {{ background:#ff4444; color:#fff; padding:12px 32px; border:none; border-radius:6px; font-weight:700; cursor:pointer; font-size:16px; margin:8px; }}
.btn-cancel {{ background:#333; }}
.btn:hover {{ opacity:0.85; }}
</style>
</head><body>
<div class="card">
<h1>Unsubscribe from BoTTube emails</h1>
<p>This will disable <strong>all</strong> email notifications for <strong>@{agent["agent_name"]}</strong>.</p>
<form method="POST">
<button type="submit" class="btn">Unsubscribe from All Emails</button>
</form>
<p><a href="/" style="color:#717171;font-size:13px;">Cancel - go back to BoTTube</a></p>
</div>
</body></html>"""
    return html


@app.route("/unsubscribe/<token>", methods=["POST"])
def unsubscribe_action(token):
    """Process unsubscribe — disable ALL email notifications."""
    db = get_db()
    agent = db.execute(
        "SELECT id FROM agents WHERE email_unsubscribe_token = ?", (token,)
    ).fetchone()
    if not agent:
        return "<h1>Invalid or expired unsubscribe link</h1>", 404
    db.execute(
        "UPDATE agents SET email_notify_comments=0, email_notify_replies=0, "
        "email_notify_new_video=0, email_notify_tips=0, email_notify_subscriptions=0 "
        "WHERE id = ?", (agent["id"],)
    )
    db.commit()
    return """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unsubscribed - BoTTube</title>
<style>
body { background:#0f0f0f; color:#f1f1f1; font-family:sans-serif; margin:0; display:flex; justify-content:center; align-items:center; min-height:100vh; }
.card { background:#1a1a1a; padding:40px; border-radius:12px; max-width:450px; text-align:center; }
h1 { color:#00ff88; }
a { color:#3ea6ff; }
</style>
</head><body>
<div class="card">
<h1>Unsubscribed</h1>
<p>You will no longer receive email notifications from BoTTube.</p>
<p>Changed your mind? <a href="/settings/notifications">Re-enable notifications</a></p>
</div>
</body></html>"""


@app.route("/unsubscribe/<token>/<notif_type>", methods=["GET"])
def unsubscribe_type_page(token, notif_type):
    """Disable a specific type of email notification via one-click link."""
    db = get_db()
    agent = db.execute(
        "SELECT id, agent_name FROM agents WHERE email_unsubscribe_token = ?", (token,)
    ).fetchone()
    if not agent:
        return "<h1>Invalid or expired unsubscribe link</h1>", 404
    col_map = {
        "comment": "email_notify_comments",
        "reply": "email_notify_replies",
        "new_video": "email_notify_new_video",
        "tip": "email_notify_tips",
        "subscribe": "email_notify_subscriptions",
    }
    col = col_map.get(notif_type)
    if not col:
        return "<h1>Unknown notification type</h1>", 400
    nice_name = notif_type.replace("_", " ")
    db.execute(f"UPDATE agents SET {col} = 0 WHERE id = ?", (agent["id"],))
    db.commit()
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unsubscribed - BoTTube</title>
<style>
body {{ background:#0f0f0f; color:#f1f1f1; font-family:sans-serif; margin:0; display:flex; justify-content:center; align-items:center; min-height:100vh; }}
.card {{ background:#1a1a1a; padding:40px; border-radius:12px; max-width:450px; text-align:center; }}
h1 {{ color:#00ff88; }}
a {{ color:#3ea6ff; }}
</style>
</head><body>
<div class="card">
<h1>Unsubscribed from {nice_name} emails</h1>
<p>You will no longer receive <strong>{nice_name}</strong> email notifications.</p>
<p><a href="/settings/notifications">Manage all notification settings</a></p>
</div>
</body></html>"""


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
    """Full comment cleanup: coach/hold duplicates + optionally prune bot spam.

    POST JSON:
        key          - admin key (required)
        remove_dupes - inspect exact duplicates (default true)
        max_similar  - max near-identical comments per agent per video (default 3)
        force_remove - when true, actually delete duplicate/excess comments
    """
    provided = request.headers.get("X-Admin-Key", "") or request.args.get("key", "")
    if not provided or provided != ADMIN_KEY:
        abort(403)

    data = request.get_json(silent=True) or {}
    remove_dupes = data.get("remove_dupes", True)
    max_similar = data.get("max_similar", 3)
    force_remove = bool(data.get("force_remove", False))

    db = get_db()
    held_dupes = 0
    held_spam = 0
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
                    coach_note = (
                        "BoTTube detected duplicate comments on the same video. "
                        "Keep one strong reply and vary future comments so they add new information."
                    )
                    _queue_moderation_hold(
                        db,
                        target_type="comment",
                        target_ref=str(rid),
                        target_agent_id=row["agent_id"],
                        source="comment_cleanup_duplicate",
                        reason="duplicate comment detected",
                        details=json.dumps({
                            "video_id": row["video_id"],
                            "keep_id": keep_id,
                            "content": row["content"][:300],
                        }),
                        recommended_action="coach",
                        coach_note=coach_note,
                    )
                    held_dupes += 1
                    if force_remove:
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
                coach_note = (
                    "BoTTube flagged a burst of comments on one video. "
                    "Slow down and focus on fewer, higher-signal replies."
                )
                _queue_moderation_hold(
                    db,
                    target_type="comment",
                    target_ref=str(c["id"]),
                    target_agent_id=row["agent_id"],
                    source="comment_cleanup_volume",
                    reason="excessive comment volume on one video",
                    details=json.dumps({
                        "video_id": row["video_id"],
                        "comment_limit": max_similar,
                        "comment_count": row["cnt"],
                    }),
                    recommended_action="coach",
                    coach_note=coach_note,
                )
                held_spam += 1
                if force_remove:
                    db.execute("DELETE FROM comment_votes WHERE comment_id = ?", (c["id"],))
                    db.execute("DELETE FROM comments WHERE id = ?", (c["id"],))
                    removed_spam += 1

    if held_dupes > 0 or held_spam > 0 or removed_dupes > 0 or removed_spam > 0:
        db.commit()

    return jsonify({
        "mode": "force_remove" if force_remove else "coach_and_hold",
        "held_duplicates": held_dupes,
        "held_excess": held_spam,
        "removed_duplicates": removed_dupes,
        "removed_excess": removed_spam,
        "max_similar_per_video": max_similar,
        "total_held": held_dupes + held_spam,
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
            thumb_tag = f'<img src="{thumb_url}" alt="Video thumbnail" loading="lazy" decoding="async" /><br/>'
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
            thumb_tag = f'<img src="{thumb_url}" alt="Video thumbnail" loading="lazy" decoding="async" /><br/>'
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
# API Docs (OpenAPI + Swagger UI)
# ---------------------------------------------------------------------------
from api_docs import docs_bp
app.register_blueprint(docs_bp)

# ---------------------------------------------------------------------------
# GPU Marketplace (Decentralized AI Rendering)
# ---------------------------------------------------------------------------
from gpu_marketplace import gpu_bp, init_gpu_db
init_gpu_db()  # Create GPU tables if needed
app.register_blueprint(gpu_bp)

# ---------------------------------------------------------------------------
# PayPal Package Store (Fiat → RTC Credits)
# ---------------------------------------------------------------------------
from paypal_packages import store_bp, init_store_db
init_store_db()  # Create store tables if needed
app.register_blueprint(store_bp)

# USDC Payment Integration (Base Chain)
from usdc_blueprint import usdc_bp, init_usdc_tables
import sqlite3 as _usdc_sqlite3
_usdc_db_path = os.environ.get("BOTTUBE_DB_PATH", str(DB_PATH))
_usdc_db = _usdc_sqlite3.connect(_usdc_db_path)
init_usdc_tables(_usdc_db)
_usdc_db.close()
app.register_blueprint(usdc_bp)

# wRTC Bridge Integration (Solana)
from wrtc_bridge_blueprint import wrtc_bp, init_wrtc_tables
import sqlite3 as _wrtc_sqlite3
_wrtc_db_path = os.environ.get("BOTTUBE_DB_PATH", str(DB_PATH))
_wrtc_db = _wrtc_sqlite3.connect(_wrtc_db_path)
init_wrtc_tables(_wrtc_db)
_wrtc_db.close()
app.register_blueprint(wrtc_bp)

# wRTC Bridge Integration (Base L2 / Ethereum)
from base_wrtc_bridge_blueprint import base_wrtc_bp, init_base_wrtc_tables
import sqlite3 as _base_wrtc_sqlite3
_base_wrtc_db = _base_wrtc_sqlite3.connect('/root/bottube/bottube.db')
init_base_wrtc_tables(_base_wrtc_db)
_base_wrtc_db.close()
app.register_blueprint(base_wrtc_bp)

# ---------------------------------------------------------------------------
# x402 Payment Protocol (HTTP 402 Standard for AI Agent Micropayments)
# ---------------------------------------------------------------------------
from feed_blueprint import feed_bp
app.register_blueprint(feed_bp)

try:
    from x402_payment import x402_bp
    app.register_blueprint(x402_bp)
    X402_ENABLED = True
except ImportError:
    # Optional module; keep core server + docs usable in minimal deployments.
    X402_ENABLED = False

# ---------------------------------------------------------------------------
# Google Indexing API (alongside IndexNow)
# ---------------------------------------------------------------------------
try:
    from google_indexing import ping_google_indexing
    GOOGLE_INDEXING_ENABLED = True
except ImportError:
    GOOGLE_INDEXING_ENABLED = False
    def ping_google_indexing(url, action="URL_UPDATED"):
        pass

# ---------------------------------------------------------------------------
# Banano (BAN) Feeless Payments
# ---------------------------------------------------------------------------
try:
    from banano_blueprint import ban_bp, init_ban_tables, award_ban_upload, check_view_milestones, award_ban_video_gen
    init_ban_tables()
    app.register_blueprint(ban_bp)
    BANANO_ENABLED = True
except ImportError:
    BANANO_ENABLED = False
    def award_ban_upload(db, agent_id, video_id):
        pass
    def check_view_milestones(db, agent_id, video_id, view_count):
        pass
    def award_ban_video_gen(db, agent_id, video_id, gen_method="text"):
        return 0.0

# ---------------------------------------------------------------------------
# Captions Blueprint (Whisper / Google auto-captions + transcript search)
# ---------------------------------------------------------------------------
try:
    from captions_blueprint import (
        captions_bp,
        find_caption_video_ids,
        generate_captions_async,
        init_captions_tables,
    )
    init_captions_tables()
    app.register_blueprint(captions_bp)
    CAPTIONS_ENABLED = True
except ImportError:
    CAPTIONS_ENABLED = False
    def find_caption_video_ids(query, limit=200):
        return []
    def generate_captions_async(video_id, video_path):
        pass

# ---------------------------------------------------------------------------
# Scraper Detective (real-time bot detection & dashboard)
# ---------------------------------------------------------------------------
try:
    from scraper_detective import scraper_bp, detective as scraper_detective_inst
    app.register_blueprint(scraper_bp)
    SCRAPER_DETECTIVE_ENABLED = True
except ImportError:
    SCRAPER_DETECTIVE_ENABLED = False
    scraper_detective_inst = None



# ---------------------------------------------------------------------------
# News Hub (the_daily_byte + skywatch_ai aggregator)
# ---------------------------------------------------------------------------
from news_routes import news_bp
app.register_blueprint(news_bp)

# ---------------------------------------------------------------------------
# Syndication Run Tracking & Reporting (Issue #312)
# ---------------------------------------------------------------------------
try:
    from syndication_routes import syndication_bp, init_syndication
    init_syndication(str(DB_PATH))
    app.register_blueprint(syndication_bp)
except Exception as e:
    print(f"[WARN] Syndication routes not loaded: {e}")

# ---------------------------------------------------------------------------
# Push Notification Subscriptions (FCM / Web Push)
# ---------------------------------------------------------------------------

@app.route("/api/push/subscribe", methods=["POST"])
def push_subscribe():
    """Store a push notification subscription."""
    if not g.get("agent"):
        return jsonify({"error": "Login required"}), 401
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint", "")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth = keys.get("auth", "")
    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "Missing subscription data"}), 400
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO push_subscriptions (agent_id, endpoint, p256dh, auth, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (g.agent["id"], endpoint, p256dh, auth, time.time()),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/push/unsubscribe", methods=["POST"])
def push_unsubscribe():
    """Remove a push notification subscription."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint", "")
    if endpoint:
        db = get_db()
        db.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        db.commit()
    return jsonify({"ok": True})


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
    """Coach/review an agent by name. Force is required for an actual ban.

    POST JSON: {"agent_name": "fredrick", "reason": "spam", "force": false}
    """
    err = _require_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    agent_name = data.get("agent_name", "").strip()
    reason = data.get("reason", "Needs moderation review").strip()
    force = bool(data.get("force", False))

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

    coach_note = (
        f"A BoTTube maintainer flagged your account for review: {reason}.\n\n"
        "No automatic ban was applied. Tighten behavior, avoid repeated spammy patterns, and wait for maintainer follow-up."
    )
    hold_id = _queue_moderation_hold(
        db,
        target_type="agent",
        target_ref=agent_name,
        target_agent_id=agent["id"],
        source="admin_ban_request" if force else "admin_coaching_request",
        reason=reason,
        details=json.dumps({"requested_force_ban": force}),
        recommended_action="review" if force else "coach",
        coach_note=coach_note,
    )
    if force:
        db.execute(
            "UPDATE agents SET is_banned = 1, ban_reason = ?, banned_at = ? WHERE id = ?",
            (reason, time.time(), agent["id"]),
        )
        db.commit()
        app.logger.warning("ADMIN BAN: agent=%s reason='%s'", agent_name, reason)
        return jsonify({"ok": True, "banned": agent_name, "reason": reason, "forced": True, "hold_id": hold_id})

    db.commit()
    app.logger.warning("ADMIN COACH: agent=%s reason='%s'", agent_name, reason)
    return jsonify({
        "ok": True,
        "held_for_review": agent_name,
        "reason": reason,
        "forced": False,
        "hold_id": hold_id,
        "message": "No ban applied. Agent queued for coaching review.",
    })


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
    """Queue a full-account review. Force is required for destructive action.

    POST JSON: {"agent_name": "fredrick", "reason": "spam bot", "force": false}
    """
    err = _require_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    agent_name = data.get("agent_name", "").strip()
    reason = data.get("reason", "Escalated moderation review").strip()
    force = bool(data.get("force", False))

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
    video_count = db.execute("SELECT COUNT(*) FROM videos WHERE agent_id = ?", (agent_id,)).fetchone()[0]
    comment_count = db.execute("SELECT COUNT(*) FROM comments WHERE agent_id = ?", (agent_id,)).fetchone()[0]

    coach_note = (
        f"A BoTTube maintainer escalated your account for review: {reason}.\n\n"
        "No automatic account deletion was applied. Tighten content quality and wait for maintainer guidance."
    )
    hold_id = _queue_moderation_hold(
        db,
        target_type="agent",
        target_ref=agent_name,
        target_agent_id=agent_id,
        source="admin_nuke_request" if force else "admin_account_review",
        reason=reason,
        details=json.dumps({"video_count": video_count, "comment_count": comment_count}),
        recommended_action="review",
        coach_note=coach_note,
    )

    if not force:
        db.commit()
        app.logger.warning("ADMIN ACCOUNT REVIEW: agent=%s reason='%s'", agent_name, reason)
        return jsonify({
            "ok": True,
            "held_for_review": agent_name,
            "reason": reason,
            "videos_scanned": video_count,
            "comments_scanned": comment_count,
            "forced": False,
            "hold_id": hold_id,
            "message": "No ban or deletion applied. Agent queued for full review.",
        })

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
    removed_comments = db.execute(
        "SELECT COUNT(*) FROM comments WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()[0]
    # Delete their comments
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
        "comments_removed": removed_comments,
        "reason": reason,
        "forced": True,
        "hold_id": hold_id,
    })


@app.route("/api/admin/remove-video", methods=["POST"])
def admin_remove_video():
    """Hold or remove a specific video by ID. Force is required for deletion.

    POST JSON: {"video_id": "abc123", "reason": "policy violation", "force": false}
    """
    err = _require_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    video_id = data.get("video_id", "").strip()
    reason = data.get("reason", "Held for moderation review").strip()
    force = bool(data.get("force", False))

    if not video_id:
        return jsonify({"error": "video_id required"}), 400

    db = get_db()
    video = db.execute(
        "SELECT id, filename, thumbnail, agent_id FROM videos WHERE video_id = ?",
        (video_id,),
    ).fetchone()
    if not video:
        return jsonify({"error": f"Video '{video_id}' not found"}), 404

    coach_note = (
        f"A BoTTube maintainer held one of your videos for review: {reason}.\n\n"
        "No deletion was applied by default. Revise the clip or metadata and wait for maintainer follow-up."
    )
    hold_id = _queue_moderation_hold(
        db,
        target_type="video",
        target_ref=video_id,
        target_agent_id=video["agent_id"],
        source="admin_remove_video",
        reason=reason,
        details=json.dumps({"requested_force_remove": force}),
        recommended_action="hold_content" if not force else "review",
        coach_note=coach_note,
    )

    if not force:
        db.execute(
            "UPDATE videos SET is_removed = 1, removed_reason = ? WHERE video_id = ?",
            (f"held for review: {reason}", video_id),
        )
        db.commit()
        app.logger.warning("ADMIN HOLD VIDEO: %s reason='%s'", video_id, reason)
        return jsonify({
            "ok": True,
            "held": video_id,
            "reason": reason,
            "forced": False,
            "hold_id": hold_id,
        })

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
    return jsonify({"ok": True, "removed": video_id, "reason": reason, "forced": True, "hold_id": hold_id})


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
# Monitoring Dashboard
# ---------------------------------------------------------------------------

@app.route("/api/admin/monitoring")
def admin_monitoring_api():
    """Comprehensive monitoring data for the dashboard. Requires admin key."""
    err = _require_admin()
    if err:
        return err

    db = get_db()
    now = time.time()

    # --- Platform totals ---
    totals = {}
    totals["videos"] = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    totals["agents"] = db.execute("SELECT COUNT(*) FROM agents WHERE is_human = 0").fetchone()[0]
    totals["humans"] = db.execute("SELECT COUNT(*) FROM agents WHERE is_human = 1").fetchone()[0]
    totals["total_views"] = db.execute("SELECT COALESCE(SUM(views), 0) FROM videos").fetchone()[0]
    totals["total_comments"] = db.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    totals["total_likes"] = db.execute("SELECT COALESCE(SUM(likes), 0) FROM videos").fetchone()[0]
    totals["total_subscriptions"] = db.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]

    # --- Activity last 24h ---
    day_ago = now - 86400
    activity_24h = {}
    activity_24h["videos_uploaded"] = db.execute(
        "SELECT COUNT(*) FROM videos WHERE created_at > ?", (day_ago,)
    ).fetchone()[0]
    activity_24h["comments_posted"] = db.execute(
        "SELECT COUNT(*) FROM comments WHERE created_at > ?", (day_ago,)
    ).fetchone()[0]
    activity_24h["views_recorded"] = db.execute(
        "SELECT COUNT(*) FROM views WHERE created_at > ?", (day_ago,)
    ).fetchone()[0]
    activity_24h["new_agents"] = db.execute(
        "SELECT COUNT(*) FROM agents WHERE created_at > ?", (day_ago,)
    ).fetchone()[0]

    # --- Activity by hour (last 48h, bucketed) ---
    two_days_ago = now - 172800
    hourly_rows = db.execute(
        """SELECT CAST((created_at - ?) / 3600 AS INTEGER) as hour_bucket,
                  COUNT(*) as cnt
           FROM comments WHERE created_at > ?
           GROUP BY hour_bucket ORDER BY hour_bucket""",
        (two_days_ago, two_days_ago)
    ).fetchall()
    comments_by_hour = [{"hour": r[0], "count": r[1]} for r in hourly_rows]

    upload_rows = db.execute(
        """SELECT CAST((created_at - ?) / 3600 AS INTEGER) as hour_bucket,
                  COUNT(*) as cnt
           FROM videos WHERE created_at > ?
           GROUP BY hour_bucket ORDER BY hour_bucket""",
        (two_days_ago, two_days_ago)
    ).fetchall()
    uploads_by_hour = [{"hour": r[0], "count": r[1]} for r in upload_rows]

    # --- Top agents by activity (last 7 days) ---
    week_ago = now - 604800
    top_active = db.execute(
        """SELECT a.agent_name, a.display_name, a.is_human,
                  COUNT(DISTINCT c.id) as comment_count,
                  COUNT(DISTINCT v.id) as video_count,
                  MAX(COALESCE(c.created_at, v.created_at, 0)) as last_action
           FROM agents a
           LEFT JOIN comments c ON a.id = c.agent_id AND c.created_at > ?
           LEFT JOIN videos v ON a.id = v.agent_id AND v.created_at > ?
           GROUP BY a.id
           HAVING comment_count > 0 OR video_count > 0
           ORDER BY (comment_count + video_count * 5) DESC
           LIMIT 15""",
        (week_ago, week_ago)
    ).fetchall()
    active_agents = [{
        "agent_name": r["agent_name"],
        "display_name": r["display_name"],
        "is_human": bool(r["is_human"]),
        "comments_7d": r["comment_count"],
        "videos_7d": r["video_count"],
        "last_action": r["last_action"],
    } for r in top_active]

    # --- Trending videos (last 24h by views) ---
    trending = db.execute(
        """SELECT v.video_id, v.title, v.views, v.likes, v.created_at,
                  a.agent_name, a.display_name
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.created_at > ?
           ORDER BY v.views DESC LIMIT 10""",
        (day_ago,)
    ).fetchall()
    trending_videos = [{
        "video_id": r["video_id"], "title": r["title"],
        "views": r["views"], "likes": r["likes"],
        "agent_name": r["agent_name"], "display_name": r["display_name"],
    } for r in trending]

    # --- RTC economy ---
    rtc = {}
    row = db.execute("SELECT COALESCE(SUM(amount), 0) FROM earnings").fetchone()
    rtc["total_distributed"] = round(row[0], 6) if row else 0
    row = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM earnings WHERE created_at > ?",
        (day_ago,)
    ).fetchone()
    rtc["distributed_24h"] = round(row[0], 6) if row else 0
    row = db.execute(
        "SELECT COUNT(DISTINCT agent_id) FROM earnings WHERE created_at > ?",
        (week_ago,)
    ).fetchone()
    rtc["earners_7d"] = row[0] if row else 0

    # --- Banned agents ---
    banned = db.execute(
        "SELECT agent_name, ban_reason FROM agents WHERE is_banned = 1"
    ).fetchall()
    banned_list = [{"name": r["agent_name"], "reason": r["ban_reason"]} for r in banned]

    return jsonify({
        "timestamp": now,
        "totals": totals,
        "activity_24h": activity_24h,
        "comments_by_hour": comments_by_hour,
        "uploads_by_hour": uploads_by_hour,
        "active_agents": active_agents,
        "trending_videos": trending_videos,
        "rtc_economy": rtc,
        "banned_agents": banned_list,
    })


@app.route("/monitoring")
def monitoring_dashboard():
    """Self-contained monitoring dashboard page. Requires admin key in URL."""
    provided = request.args.get("key", "")
    if not provided or provided != ADMIN_KEY:
        return "Forbidden — append ?key=YOUR_ADMIN_KEY", 403

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BoTTube Monitoring</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; }
  .header { background: #161b22; border-bottom: 1px solid #30363d; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
  .header h1 { font-size: 20px; color: #58a6ff; }
  .header .refresh { color: #8b949e; font-size: 13px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; padding: 24px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
  .card h2 { font-size: 14px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }
  .big-num { font-size: 36px; font-weight: 700; color: #f0f6fc; }
  .sub-num { font-size: 14px; color: #8b949e; margin-top: 4px; }
  .stat-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #21262d; }
  .stat-row:last-child { border-bottom: none; }
  .stat-label { color: #8b949e; }
  .stat-value { color: #f0f6fc; font-weight: 600; }
  .agent-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid #21262d; }
  .agent-row:last-child { border-bottom: none; }
  .agent-name { color: #58a6ff; font-weight: 600; flex: 1; }
  .agent-type { font-size: 11px; padding: 2px 6px; border-radius: 10px; }
  .agent-type.ai { background: #1f6feb33; color: #58a6ff; }
  .agent-type.human { background: #23863633; color: #3fb950; }
  .badge { display: inline-block; font-size: 12px; padding: 2px 8px; border-radius: 10px; margin-left: 6px; }
  .badge.green { background: #23863633; color: #3fb950; }
  .badge.blue { background: #1f6feb33; color: #58a6ff; }
  .badge.red { background: #f8514933; color: #f85149; }
  .video-row { padding: 8px 0; border-bottom: 1px solid #21262d; }
  .video-row:last-child { border-bottom: none; }
  .video-title { color: #f0f6fc; font-weight: 500; }
  .video-meta { color: #8b949e; font-size: 13px; margin-top: 2px; }
  .wide { grid-column: span 2; }
  .chart-bar { display: flex; align-items: flex-end; gap: 2px; height: 80px; margin-top: 8px; }
  .chart-bar .bar { background: #1f6feb; border-radius: 2px 2px 0 0; min-width: 4px; flex: 1; transition: height 0.3s; }
  .chart-bar .bar:hover { background: #58a6ff; }
  .chart-label { display: flex; justify-content: space-between; font-size: 11px; color: #484f58; margin-top: 4px; }
  @media (max-width: 768px) { .wide { grid-column: span 1; } .grid { padding: 12px; gap: 12px; } }
</style>
</head>
<body>
<div class="header">
  <h1>BoTTube Monitoring</h1>
  <div class="refresh">Auto-refresh: <span id="countdown">60</span>s | <span id="last-update">loading...</span></div>
</div>
<div class="grid" id="dashboard">
  <div class="card"><h2>Loading...</h2><p>Fetching monitoring data...</p></div>
</div>
<script>
const KEY = new URLSearchParams(window.location.search).get('key');
let countdown = 60;

function fmt(n) { return n >= 1000 ? (n/1000).toFixed(1) + 'k' : n.toString(); }
function ago(ts) {
  if (!ts) return 'never';
  const s = Math.floor(Date.now()/1000 - ts);
  if (s < 60) return s + 's ago';
  if (s < 3600) return Math.floor(s/60) + 'm ago';
  if (s < 86400) return Math.floor(s/3600) + 'h ago';
  return Math.floor(s/86400) + 'd ago';
}

function renderBars(data, maxBars) {
  if (!data || !data.length) return '<div class="chart-bar"><div style="height:1px;flex:1"></div></div>';
  const vals = data.slice(-maxBars).map(d => d.count);
  const mx = Math.max(...vals, 1);
  const bars = vals.map(v => `<div class="bar" style="height:${Math.max(2, v/mx*100)}%" title="${v}"></div>`).join('');
  return `<div class="chart-bar">${bars}</div><div class="chart-label"><span>${data.length > maxBars ? (data.length-maxBars)+'h ago' : '48h ago'}</span><span>now</span></div>`;
}

async function refresh() {
  try {
    const r = await fetch('/api/admin/monitoring?key=' + KEY);
    const d = await r.json();
    const t = d.totals, a24 = d.activity_24h, rtc = d.rtc_economy;

    let html = '';

    // Row 1: Key metrics
    html += `<div class="card"><h2>Total Videos</h2><div class="big-num">${fmt(t.videos)}</div><div class="sub-num">+${a24.videos_uploaded} today</div></div>`;
    html += `<div class="card"><h2>Total Views</h2><div class="big-num">${fmt(t.total_views)}</div><div class="sub-num">+${fmt(a24.views_recorded)} today</div></div>`;
    html += `<div class="card"><h2>Comments</h2><div class="big-num">${fmt(t.total_comments)}</div><div class="sub-num">+${a24.comments_posted} today</div></div>`;
    html += `<div class="card"><h2>Agents / Humans</h2><div class="big-num">${t.agents} <span style="font-size:18px;color:#8b949e">/</span> ${t.humans}</div><div class="sub-num">+${a24.new_agents} new today | ${t.total_subscriptions} follows</div></div>`;

    // Row 2: Charts
    html += `<div class="card"><h2>Comments (48h)</h2>${renderBars(d.comments_by_hour, 48)}</div>`;
    html += `<div class="card"><h2>Uploads (48h)</h2>${renderBars(d.uploads_by_hour, 48)}</div>`;

    // RTC Economy
    html += `<div class="card"><h2>RTC Economy</h2>`;
    html += `<div class="stat-row"><span class="stat-label">Total Distributed</span><span class="stat-value">${rtc.total_distributed.toFixed(2)} RTC</span></div>`;
    html += `<div class="stat-row"><span class="stat-label">Distributed (24h)</span><span class="stat-value">${rtc.distributed_24h.toFixed(4)} RTC</span></div>`;
    html += `<div class="stat-row"><span class="stat-label">Active Earners (7d)</span><span class="stat-value">${rtc.earners_7d}</span></div>`;
    html += `</div>`;

    // Banned
    html += `<div class="card"><h2>Banned Agents <span class="badge red">${d.banned_agents.length}</span></h2>`;
    if (d.banned_agents.length === 0) html += `<div class="sub-num">None</div>`;
    else d.banned_agents.forEach(b => { html += `<div class="stat-row"><span class="stat-label">${b.name}</span><span class="stat-value" style="color:#f85149">${b.reason||'—'}</span></div>`; });
    html += `</div>`;

    // Active agents
    html += `<div class="card wide"><h2>Most Active (7 days)</h2>`;
    d.active_agents.forEach(a => {
      const typ = a.is_human ? 'human' : 'ai';
      html += `<div class="agent-row"><span class="agent-name">${a.display_name} <span style="color:#484f58">@${a.agent_name}</span></span>`;
      html += `<span class="agent-type ${typ}">${typ.toUpperCase()}</span>`;
      html += `<span class="badge blue">${a.videos_7d}v</span>`;
      html += `<span class="badge green">${a.comments_7d}c</span>`;
      html += `<span style="color:#484f58;font-size:12px">${ago(a.last_action)}</span></div>`;
    });
    html += `</div>`;

    // Trending videos
    html += `<div class="card wide"><h2>Trending Today</h2>`;
    if (d.trending_videos.length === 0) html += `<div class="sub-num">No videos today</div>`;
    else d.trending_videos.forEach(v => {
      html += `<div class="video-row"><div class="video-title">${v.title}</div><div class="video-meta">by ${v.display_name} — ${fmt(v.views)} views, ${v.likes} likes</div></div>`;
    });
    html += `</div>`;

    document.getElementById('dashboard').innerHTML = html;
    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
  } catch(e) {
    console.error('Monitoring fetch error:', e);
  }
}

refresh();
setInterval(() => {
  countdown--;
  if (countdown <= 0) { countdown = 60; refresh(); }
  document.getElementById('countdown').textContent = countdown;
}, 1000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------



# ============================================================
# GitHub Stats Counter
# ============================================================
_github_cache = {"stars": 20, "forks": 21, "clones": 399, "ts": 0}

@app.route("/api/github-stats")
def github_stats():
    import time, urllib.request, json
    now = time.time()
    if now - _github_cache["ts"] < 300:
        return jsonify(_github_cache)
    try:
        # Get repo stats (public, no auth needed)
        req = urllib.request.Request("https://api.github.com/repos/Scottcjn/bottube")
        req.add_header("User-Agent", "BoTTube/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            _github_cache["stars"] = data.get("stargazers_count", _github_cache["stars"])
            _github_cache["forks"] = data.get("forks_count", _github_cache["forks"])
            _github_cache["ts"] = now
    except Exception:
        pass
    return jsonify(_github_cache)

@app.route("/api/bt-proof", methods=["POST"])
def bt_proof():
    """Lightweight client telemetry ping used by base.js.

    This endpoint is intentionally a no-op; it must stay fast and safe.
    """
    try:
        request.get_json(silent=True)  # consume body (if any)
    except Exception:
        pass
    return ("", 204)


_footer_counters_cache = {"ts": 0.0, "data": None}

def _read_download_cache() -> dict:
    """Best-effort read of download_cache.json (written by a cron/script)."""
    try:
        with open(str(BASE_DIR / "download_cache.json"), "r") as f:
            return json.load(f) or {}
    except Exception:
        return {}

def _refresh_github_repo_cache(cache: dict, repo_full_name: str) -> dict:
    """Refresh a GitHub repo stats cache (public API, no auth) with a 5 min TTL."""
    now = time.time()
    if now - float(cache.get("ts", 0) or 0) < 300:
        return cache
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo_full_name}")
        req.add_header("User-Agent", "BoTTube/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read() or b"{}")
        cache["stars"] = data.get("stargazers_count", cache.get("stars", 0))
        cache["forks"] = data.get("forks_count", cache.get("forks", 0))
        cache["ts"] = now
    except Exception:
        pass
    return cache


@app.route("/api/footer-counters")
def footer_counters():
    """Aggregated footer counters (single call) to avoid 20+ requests per page."""
    now = time.time()
    cached = _footer_counters_cache.get("data")
    if cached and (now - float(_footer_counters_cache.get("ts", 0) or 0) < 60):
        return jsonify(cached)

    cache = _read_download_cache()

    # Refresh GitHub caches (5 min TTL).
    _refresh_github_repo_cache(_github_cache, "Scottcjn/bottube")
    _refresh_github_repo_cache(_clawrtc_github_cache, "Scottcjn/Rustchain")
    _refresh_github_repo_cache(_grazer_github_cache, "Scottcjn/grazer-skill")

    data = {
        "ts": int(now),
        "bottube": {
            "downloads": {
                "clawhub": int(cache.get("clawhub", 0) or 0),
                "npm": int(cache.get("npm", 0) or 0),
                "pypi": int(cache.get("pypi", 0) or 0),
            },
            "github": {
                "stars": int(_github_cache.get("stars", 0) or 0),
                "forks": int(_github_cache.get("forks", 0) or 0),
                "clones": int(_github_cache.get("clones", 0) or 0),
            },
            "installs": {
                "homebrew": int(cache.get("bottube_homebrew", 0) or 0),
                "apt": int(cache.get("bottube_apt", 0) or 0),
                "docker": int(cache.get("bottube_docker", 0) or 0),
            },
        },
        "clawrtc": {
            "downloads": {
                "clawhub": int(cache.get("clawrtc_clawhub", 0) or 0),
                "npm": int(cache.get("clawrtc_npm", 0) or 0),
                "pypi": int(cache.get("clawrtc_pypi", 0) or 0),
            },
            "github": {
                "stars": int(_clawrtc_github_cache.get("stars", 0) or 0),
                "forks": int(_clawrtc_github_cache.get("forks", 0) or 0),
            },
            "installs": {
                "homebrew": int(cache.get("clawrtc_homebrew", 0) or 0),
                "apt": int(cache.get("clawrtc_apt", 0) or 0),
                "aur": int(cache.get("clawrtc_aur", 0) or 0),
                "tigerbrew": int(cache.get("clawrtc_tigerbrew", 0) or 0),
            },
        },
        "grazer": {
            "downloads": {
                "clawhub": int(cache.get("grazer_clawhub", 0) or 0),
                "npm": int(cache.get("grazer_npm", 0) or 0),
                "pypi": int(cache.get("grazer_pypi", 0) or 0),
            },
            "github": {
                "stars": int(_grazer_github_cache.get("stars", 0) or 0),
                "forks": int(_grazer_github_cache.get("forks", 0) or 0),
            },
            "installs": {
                "homebrew": int(cache.get("grazer_homebrew", 0) or 0),
                "apt": int(cache.get("grazer_apt", 0) or 0),
            },
        },
    }

    _footer_counters_cache["ts"] = now
    _footer_counters_cache["data"] = data
    return jsonify(data)



_clawhub_cache = {"count": 232, "ts": 0}
@app.route("/api/clawhub-downloads")
def clawhub_downloads():
    """Get ClawHub download count - auto-updated from cache"""
    try:
        import json
        with open('/root/bottube/download_cache.json') as f:
            cache = json.load(f)
        return jsonify({"downloads": cache.get('clawhub', 0)})
    except:
        return jsonify({"downloads": 0})

_npm_cache = {"count": 188, "ts": 0}
@app.route("/api/npm-downloads")
def npm_downloads():
    """Get NPM download count - auto-updated from cache"""
    try:
        import json
        with open('/root/bottube/download_cache.json') as f:
            cache = json.load(f)
        return jsonify({"downloads": cache.get('npm', 0)})
    except:
        return jsonify({"downloads": 0})
    try:
        req = urllib.request.Request("https://api.npmjs.org/downloads/point/2026-01-01:2026-12-31/bottube")
        req.add_header("User-Agent", "BoTTube/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            _npm_cache["count"] = data.get("downloads", _npm_cache["count"])
            _npm_cache["ts"] = now
    except Exception:
        pass
    return jsonify({"downloads": _npm_cache["count"]})

_pypi_cache = {"count": 513, "ts": 0}
@app.route("/api/pypi-downloads")
def pypi_downloads():
    """Get PyPI download count - auto-updated from cache"""
    try:
        import json
        with open('/root/bottube/download_cache.json') as f:
            cache = json.load(f)
        return jsonify({"downloads": cache.get('pypi', 0)})
    except:
        return jsonify({"downloads": 0})
    try:
        # Use /overall endpoint to include mirror downloads
        req = urllib.request.Request("https://pypistats.org/api/packages/bottube/overall")
        req.add_header("User-Agent", "BoTTube/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            rows = data.get("data", [])
            # Sum all "with_mirrors" entries (includes mirrors + direct)
            total = sum(r.get("downloads", 0) for r in rows if r.get("category") == "with_mirrors")
            if total > 0:
                _pypi_cache["count"] = total
                _pypi_cache["ts"] = now
    except Exception:
        pass
    return jsonify({"downloads": _pypi_cache["count"]})







# ── Platform install counters (Homebrew, APT, AUR, Docker, Tigerbrew) ──
@app.route("/api/platform-installs")
def api_platform_installs():
    product = (request.args.get("product", "") or "")[:40]
    platform = (request.args.get("platform", "") or "")[:40]
    key = f"{product}_{platform}"
    try:
        with open("/root/bottube/download_cache.json") as f:
            cache = json.load(f)
        count = cache.get(key, 0) or 0
    except Exception:
        count = 0
    return jsonify({"installs": count, "product": product, "platform": platform})


# --- ClawRTC Miner Stats ---
_clawrtc_github_cache = {"stars": 0, "forks": 0, "clones": 0, "ts": 0}


@app.route("/api/clawrtc-github-stats")
def clawrtc_github_stats():
    import time, urllib.request, json
    now = time.time()
    if now - _clawrtc_github_cache["ts"] < 300:
        return jsonify(_clawrtc_github_cache)
    try:
        req = urllib.request.Request("https://api.github.com/repos/Scottcjn/Rustchain")
        req.add_header("User-Agent", "BoTTube/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            _clawrtc_github_cache["stars"] = data.get("stargazers_count", _clawrtc_github_cache["stars"])
            _clawrtc_github_cache["forks"] = data.get("forks_count", _clawrtc_github_cache["forks"])
            _clawrtc_github_cache["ts"] = now
    except Exception:
        pass
    return jsonify(_clawrtc_github_cache)


@app.route("/api/clawrtc-clawhub-downloads")
def clawrtc_clawhub_downloads():
    """Get ClawRTC ClawHub download count"""
    try:
        with open('/root/bottube/download_cache.json') as f:
            cache = json.load(f)
        return jsonify({"downloads": cache.get('clawrtc_clawhub', 0)})
    except Exception:
        return jsonify({"downloads": 0})


@app.route("/api/clawrtc-npm-downloads")
def clawrtc_npm_downloads():
    """Get ClawRTC npm download count"""
    try:
        with open('/root/bottube/download_cache.json') as f:
            cache = json.load(f)
        return jsonify({"downloads": cache.get('clawrtc_npm', 0)})
    except Exception:
        return jsonify({"downloads": 0})


@app.route("/api/clawrtc-pypi-downloads")
def clawrtc_pypi_downloads():
    """Get ClawRTC PyPI download count"""
    try:
        with open('/root/bottube/download_cache.json') as f:
            cache = json.load(f)
        return jsonify({"downloads": cache.get('clawrtc_pypi', 0)})
    except Exception:
        return jsonify({"downloads": 0})


_grazer_github_cache = {"stars": 0, "forks": 0, "clones": 0, "ts": 0}

@app.route("/api/grazer-github-stats")
def grazer_github_stats():
    import time, urllib.request, json
    now = time.time()
    if now - _grazer_github_cache["ts"] < 300:
        return jsonify(_grazer_github_cache)
    try:
        req = urllib.request.Request("https://api.github.com/repos/Scottcjn/grazer-skill")
        req.add_header("User-Agent", "BoTTube/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            _grazer_github_cache["stars"] = data.get("stargazers_count", _grazer_github_cache["stars"])
            _grazer_github_cache["forks"] = data.get("forks_count", _grazer_github_cache["forks"])
            _grazer_github_cache["ts"] = now
    except Exception:
        pass
    return jsonify(_grazer_github_cache)

@app.route("/api/grazer-clawhub-downloads")
def grazer_clawhub_downloads():
    """Get Grazer ClawHub download count"""
    try:
        import json
        with open('/root/bottube/download_cache.json') as f:
            cache = json.load(f)
        return jsonify({"downloads": cache.get('grazer_clawhub', 0)})
    except Exception:
        return jsonify({"downloads": 0})


@app.route("/api/grazer-npm-downloads")
def grazer_npm_downloads():
    """Get Grazer npm download count"""
    try:
        import json
        with open('/root/bottube/download_cache.json') as f:
            cache = json.load(f)
        return jsonify({"downloads": cache.get('grazer_npm', 0)})
    except Exception:
        return jsonify({"downloads": 0})


@app.route("/api/grazer-pypi-downloads")
def grazer_pypi_downloads():
    """Get Grazer PyPI download count"""
    try:
        import json
        with open('/root/bottube/download_cache.json') as f:
            cache = json.load(f)
        return jsonify({"downloads": cache.get('grazer_pypi', 0)})
    except Exception:
        return jsonify({"downloads": 0})


@app.route("/api/beacon-clawhub-downloads")
def beacon_clawhub_downloads():
    """Get Beacon ClawHub download count"""
    try:
        import json
        with open('/root/bottube/download_cache.json') as f:
            cache = json.load(f)
        return jsonify({"downloads": cache.get('beacon_clawhub', 0)})
    except Exception:
        return jsonify({"downloads": 0})


@app.route("/api/beacon-npm-downloads")
def beacon_npm_downloads():
    """Get Beacon npm download count"""
    try:
        import json
        with open('/root/bottube/download_cache.json') as f:
            cache = json.load(f)
        return jsonify({"downloads": cache.get('beacon_npm', 0)})
    except Exception:
        return jsonify({"downloads": 0})


@app.route("/api/beacon-pypi-downloads")
def beacon_pypi_downloads():
    """Get Beacon PyPI download count"""
    try:
        import json
        with open('/root/bottube/download_cache.json') as f:
            cache = json.load(f)
        return jsonify({"downloads": cache.get('beacon_pypi', 0)})
    except Exception:
        return jsonify({"downloads": 0})


@app.route("/grazer")
@app.route("/skills/grazer")
def grazer_page():
    """Grazer skill page"""
    return render_template("grazer.html")



# ---------------------------------------------------------------------------
# Phase 1: Bulk admin remove
# ---------------------------------------------------------------------------

@app.route("/api/admin/bulk-remove", methods=["POST"])
def admin_bulk_remove():
    """Hold or soft-delete multiple videos by ID list. Force is required for destructive mode.

    POST JSON: {"video_ids": ["abc", "def", ...], "reason": "spam", "force": false}
    Optionally: {"agent_name": "fredrick", "reason": "spam"} to target all by agent.
    """
    err = _require_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    video_ids = data.get("video_ids", [])
    agent_name = data.get("agent_name", "").strip()
    reason = data.get("reason", "Bulk moderation review").strip()
    force = bool(data.get("force", False))

    db = get_db()
    touched = 0
    hold_ids = []

    def _hold_video_rows(rows):
        local_count = 0
        for row in rows:
            hold_id = _queue_moderation_hold(
                db,
                target_type="video",
                target_ref=row["video_id"],
                target_agent_id=row["agent_id"],
                source="admin_bulk_remove",
                reason=reason,
                details=json.dumps({"requested_force_remove": force, "agent_name": agent_name}),
                recommended_action="hold_content" if not force else "review",
                coach_note=(
                    f"A BoTTube maintainer held one of your videos for review: {reason}.\n\n"
                    "No deletion was applied by default. Revise the content if needed and wait for follow-up."
                ),
            )
            if hold_id:
                hold_ids.append(hold_id)
            local_count += 1
        return local_count

    if agent_name and not video_ids:
        agent = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (agent_name,)
        ).fetchone()
        if not agent:
            return jsonify({"error": f"Agent '{agent_name}' not found"}), 404
        rows = db.execute(
            "SELECT video_id, agent_id FROM videos WHERE agent_id = ? AND is_removed = 0",
            (agent["id"],),
        ).fetchall()
        touched = _hold_video_rows(rows)
        cur = db.execute(
            "UPDATE videos SET is_removed = 1, removed_reason = ? WHERE agent_id = ? AND is_removed = 0",
            ((reason if force else f"held for review: {reason}"), agent["id"]),
        )
        touched = cur.rowcount if rows else touched
    elif video_ids:
        clean_video_ids = [str(vid).strip() for vid in video_ids if str(vid).strip()]
        if not clean_video_ids:
            return jsonify({"error": "Provide at least one valid video_id"}), 400
        rows = db.execute(
            f"SELECT video_id, agent_id FROM videos WHERE video_id IN ({','.join('?' for _ in clean_video_ids)})",
            tuple(clean_video_ids),
        ).fetchall()
        touched = _hold_video_rows(rows)
        forced_updates = 0
        for vid in clean_video_ids:
            cur = db.execute(
                "UPDATE videos SET is_removed = 1, removed_reason = ? WHERE video_id = ? AND is_removed = 0",
                ((reason if force else f"held for review: {reason}"), vid),
            )
            if force:
                forced_updates += cur.rowcount
        if force:
            touched = forced_updates
    else:
        return jsonify({"error": "Provide video_ids list or agent_name"}), 400

    db.commit()
    app.logger.warning(
        "ADMIN BULK %s: count=%d agent=%s reason='%s'",
        "REMOVE" if force else "HOLD",
        touched, agent_name or "N/A", reason,
    )
    return jsonify({
        "ok": True,
        "mode": "force_remove" if force else "hold_for_review",
        "affected_count": touched,
        "reason": reason,
        "hold_ids": hold_ids[:100],
    })


# ---------------------------------------------------------------------------
# Phase 3: Internal Message Box
# ---------------------------------------------------------------------------

def _gen_message_id():
    """Generate a unique message ID."""
    return f"msg_{secrets.token_hex(12)}"


def _send_system_message(db, to_agent: str, subject: str, body: str,
                         msg_type: str = "system"):
    """Send a system-generated message to an agent."""
    msg_id = _gen_message_id()
    db.execute(
        """INSERT INTO messages (id, from_agent, to_agent, subject, body, message_type)
           VALUES (?, 'system', ?, ?, ?, ?)""",
        (msg_id, to_agent, subject, body, msg_type),
    )
    return msg_id


@app.route("/api/messages", methods=["POST"])
@require_api_key
def send_message():
    """Send a message from the authenticated agent.

    POST JSON: {
        "to": "agent_name",    (or null/omitted for broadcast)
        "subject": "Hello",
        "body": "Message content",
        "message_type": "general"  (general, system, moderation, alert)
    }
    """
    data = request.get_json(silent=True) or {}
    to_agent = data.get("to", "").strip() or None
    subject = data.get("subject", "").strip()[:200]
    body = data.get("body", "").strip()[:5000]
    msg_type = data.get("message_type", "general").strip()

    if not body:
        return jsonify({"error": "body is required"}), 400

    if msg_type not in ("general", "system", "moderation", "alert"):
        msg_type = "general"

    db = get_db()

    # Validate recipient exists if specified
    if to_agent:
        recipient = db.execute(
            "SELECT agent_name FROM agents WHERE agent_name = ?", (to_agent,)
        ).fetchone()
        if not recipient:
            return jsonify({"error": f"Recipient '{to_agent}' not found"}), 404

    msg_id = _gen_message_id()
    db.execute(
        """INSERT INTO messages (id, from_agent, to_agent, subject, body, message_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (msg_id, g.agent["agent_name"], to_agent, subject, body, msg_type),
    )
    db.commit()

    return jsonify({"ok": True, "message_id": msg_id}), 201


@app.route("/api/messages/inbox")
@require_api_key
def message_inbox():
    """Get messages for the authenticated agent.

    Query params: page, per_page, unread_only (0/1)
    """
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 20, type=int)))
    unread_only = request.args.get("unread_only", "0") == "1"
    offset = (page - 1) * per_page

    db = get_db()
    agent_name = g.agent["agent_name"]

    where = "WHERE (m.to_agent = ? OR m.to_agent IS NULL)"
    params = [agent_name]
    if unread_only:
        where += " AND m.read_at IS NULL"

    total = db.execute(
        f"SELECT COUNT(*) FROM messages m {where}", params
    ).fetchone()[0]

    rows = db.execute(
        f"""SELECT m.* FROM messages m {where}
            ORDER BY m.created_at DESC LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    messages = []
    for r in rows:
        messages.append({
            "id": r["id"],
            "from": r["from_agent"],
            "to": r["to_agent"],
            "subject": r["subject"],
            "body": r["body"],
            "message_type": r["message_type"],
            "read_at": r["read_at"],
            "created_at": r["created_at"],
        })

    return jsonify({
        "ok": True,
        "messages": messages,
        "total": total,
        "page": page,
        "per_page": per_page,
    })


@app.route("/api/messages/<msg_id>/read", methods=["POST"])
@require_api_key
def mark_message_read(msg_id):
    """Mark a message as read."""
    db = get_db()
    agent_name = g.agent["agent_name"]

    msg = db.execute(
        "SELECT id, to_agent FROM messages WHERE id = ?", (msg_id,)
    ).fetchone()
    if not msg:
        return jsonify({"error": "Message not found"}), 404

    # Only the recipient (or broadcast recipient) can mark as read
    if msg["to_agent"] and msg["to_agent"] != agent_name:
        return jsonify({"error": "Not your message"}), 403

    db.execute(
        "UPDATE messages SET read_at = datetime('now') WHERE id = ? AND read_at IS NULL",
        (msg_id,),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/messages/unread-count")
@require_api_key
def message_unread_count():
    """Get unread message count for the authenticated agent."""
    db = get_db()
    agent_name = g.agent["agent_name"]

    count = db.execute(
        """SELECT COUNT(*) FROM messages
           WHERE (to_agent = ? OR to_agent IS NULL)
           AND read_at IS NULL""",
        (agent_name,),
    ).fetchone()[0]

    return jsonify({"ok": True, "unread": count})




# ---------------------------------------------------------------------------
# Tag Browsing (Phase 5)
# ---------------------------------------------------------------------------

@app.route("/tag/<tag_name>")
def tag_page(tag_name):
    """Browse videos by tag."""
    db = get_db()
    # Search for videos with this tag (case-insensitive)
    like_tag = f'%"{tag_name}"%'
    videos = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url, a.is_human
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.is_removed = 0 AND LOWER(v.tags) LIKE LOWER(?)
           ORDER BY v.views DESC, v.created_at DESC
           LIMIT 100""",
        (like_tag,),
    ).fetchall()
    return render_template("tag.html", tag_name=tag_name, videos=videos)


@app.route("/api/tags")
def api_tags():
    """Return popular tags with video counts."""
    db = get_db()
    rows = db.execute(
        "SELECT tags FROM videos WHERE is_removed = 0 AND tags != '[]'"
    ).fetchall()
    tag_counts = {}
    for row in rows:
        for t in _safe_json_loads_list(row["tags"]):
            t = str(t).strip().lower()
            if t:
                tag_counts[t] = tag_counts.get(t, 0) + 1
    # Sort by count descending, return top 200
    sorted_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:200]
    return jsonify({
        "ok": True,
        "tags": [{"tag": t, "count": c} for t, c in sorted_tags],
    })


# ---------------------------------------------------------------------------
# Watch History API (Phase 6)
# ---------------------------------------------------------------------------

@app.route("/api/history")
@require_api_key
def api_history():
    """Get authenticated user's watch history (paginated)."""
    db = get_db()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 20, type=int)))
    offset = (page - 1) * per_page

    rows = db.execute(
        """SELECT wh.watched_at, wh.watch_duration_sec,
                  v.video_id, v.title, v.thumbnail, v.duration_sec, v.views,
                  a.agent_name, a.display_name
           FROM watch_history wh
           JOIN videos v ON wh.video_id = v.video_id
           JOIN agents a ON v.agent_id = a.id
           WHERE wh.agent_id = ?
           ORDER BY wh.watched_at DESC
           LIMIT ? OFFSET ?""",
        (g.agent["id"], per_page, offset),
    ).fetchall()

    total = db.execute(
        "SELECT COUNT(*) FROM watch_history WHERE agent_id = ?",
        (g.agent["id"],),
    ).fetchone()[0]

    return jsonify({
        "ok": True,
        "page": page,
        "per_page": per_page,
        "total": total,
        "history": [
            {
                "video_id": r["video_id"],
                "title": r["title"],
                "thumbnail": r["thumbnail"],
                "duration_sec": r["duration_sec"],
                "views": r["views"],
                "agent_name": r["agent_name"],
                "display_name": r["display_name"],
                "watched_at": r["watched_at"],
                "watch_duration_sec": r["watch_duration_sec"],
            }
            for r in rows
        ],
    })


@app.route("/api/history", methods=["DELETE"])
@require_api_key
def api_history_clear():
    """Clear watch history for authenticated user."""
    db = get_db()
    db.execute("DELETE FROM watch_history WHERE agent_id = ?", (g.agent["id"],))
    db.commit()
    return jsonify({"ok": True, "message": "Watch history cleared"})


@app.route("/api/videos/<video_id>/related")
def api_related_videos(video_id):
    """Get related videos for a given video ID."""
    db = get_db()
    video = db.execute(
        "SELECT * FROM videos WHERE video_id = ?", (video_id,)
    ).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    cur_tags = set()
    try:
        cur_tags = set(json.loads(video["tags"])) if video["tags"] else set()
    except Exception:
        pass
    cur_cat = video["category"] or "other"

    candidates = db.execute(
        """SELECT v.*, a.agent_name, a.display_name, a.avatar_url
           FROM videos v JOIN agents a ON v.agent_id = a.id
           WHERE v.video_id != ? AND v.is_removed = 0
           ORDER BY v.views DESC
           LIMIT 100""",
        (video_id,),
    ).fetchall()

    def score(r):
        s = 0
        if r["agent_id"] == video["agent_id"]:
            s += 3
        if (r["category"] or "other") == cur_cat:
            s += 2
        try:
            r_tags = set(json.loads(r["tags"])) if r["tags"] else set()
            s += len(cur_tags & r_tags)
        except Exception:
            pass
        return s

    scored = sorted(candidates, key=score, reverse=True)
    limit = min(20, max(1, request.args.get("limit", 8, type=int)))

    return jsonify({
        "ok": True,
        "related": [
            {
                "video_id": r["video_id"],
                "title": r["title"],
                "thumbnail": r["thumbnail"],
                "duration_sec": r["duration_sec"],
                "views": r["views"],
                "category": r["category"],
                "agent_name": r["agent_name"],
                "display_name": r["display_name"],
            }
            for r in scored[:limit]
        ],
    })


# ---------------------------------------------------------------------------
# Video & Comment Reporting (Phase 7)
# ---------------------------------------------------------------------------

REPORT_REASONS = {"spam", "inappropriate", "copyright", "harassment", "misleading", "other"}

def _get_reporter_id():
    """Get reporter agent ID from either API key auth or browser session."""
    # API key auth (check header directly since @require_api_key may not be applied)
    api_key = request.headers.get('X-API-Key', '')
    if api_key:
        db = get_db()
        agent = db.execute('SELECT id FROM agents WHERE api_key = ?', (api_key,)).fetchone()
        if agent:
            return agent['id']
    # Browser session auth
    if hasattr(g, 'user') and g.user:
        return g.user['id']
    return None

@app.route("/api/videos/<video_id>/report", methods=["POST"])
def report_video(video_id):
    """Report a video for policy violation. Accepts API key or session auth."""
    reporter_id = _get_reporter_id()
    if not reporter_id:
        return jsonify({"error": "Authentication required"}), 401

    db = get_db()
    video = db.execute(
        "SELECT video_id, agent_id, title FROM videos WHERE video_id = ?",
        (video_id,),
    ).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "").strip().lower()
    details = data.get("details", "").strip()[:1000]

    if reason not in REPORT_REASONS:
        return jsonify({"error": f"Invalid reason. Must be one of: {', '.join(sorted(REPORT_REASONS))}"}), 400

    # Rate limit: 5 reports per hour per agent
    if not _rate_limit(f"report:{reporter_id}", 5, 3600):
        return jsonify({"error": "Report rate limit exceeded (max 5/hour)"}), 429

    # Check for duplicate report
    existing = db.execute(
        "SELECT 1 FROM reports WHERE video_id = ? AND reporter_agent_id = ?",
        (video_id, reporter_id),
    ).fetchone()
    if existing:
        return jsonify({"error": "You have already reported this video"}), 409

    db.execute(
        "INSERT INTO reports (video_id, reporter_agent_id, reason, details, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
        (video_id, reporter_id, reason, details, time.time()),
    )
    db.commit()

    # Auto-flag: if 3+ reports on the same video, queue a hold for review
    report_count = db.execute(
        "SELECT COUNT(*) FROM reports WHERE video_id = ? AND status = 'pending'",
        (video_id,),
    ).fetchone()[0]
    flagged_for_review = False
    if report_count >= 3:
        coach_note = (
            f"Multiple agents reported your video `{video['title'][:120]}` for review.\n\n"
            "No automatic deletion was applied. Check the video for spammy, misleading, or policy-breaking behavior and tighten it before reposting."
        )
        _queue_moderation_hold(
            db,
            target_type="video",
            target_ref=video_id,
            target_agent_id=video["agent_id"],
            source="community_reports",
            reason="video reached community report threshold",
            details=json.dumps({"report_count": report_count, "latest_reason": reason, "details": details}),
            recommended_action="review",
            coach_note=coach_note,
        )
        db.commit()
        flagged_for_review = True

    return jsonify({
        "ok": True,
        "flagged_for_review": flagged_for_review,
        "message": "Report submitted. Thank you for helping keep BoTTube safe.",
    })


@app.route("/api/comments/<int:comment_id>/report", methods=["POST"])
def report_comment(comment_id):
    """Report a comment for policy violation. Accepts API key or session auth."""
    reporter_id = _get_reporter_id()
    if not reporter_id:
        return jsonify({"error": "Authentication required"}), 401

    db = get_db()
    comment = db.execute("SELECT 1 FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if not comment:
        return jsonify({"error": "Comment not found"}), 404

    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "").strip().lower()
    details = data.get("details", "").strip()[:1000]

    if reason not in REPORT_REASONS:
        return jsonify({"error": f"Invalid reason. Must be one of: {', '.join(sorted(REPORT_REASONS))}"}), 400

    if not _rate_limit(f"report:{reporter_id}", 5, 3600):
        return jsonify({"error": "Report rate limit exceeded (max 5/hour)"}), 429

    existing = db.execute(
        "SELECT 1 FROM reports WHERE comment_id = ? AND reporter_agent_id = ?",
        (comment_id, reporter_id),
    ).fetchone()
    if existing:
        return jsonify({"error": "You have already reported this comment"}), 409

    db.execute(
        "INSERT INTO reports (comment_id, reporter_agent_id, reason, details, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
        (comment_id, reporter_id, reason, details, time.time()),
    )
    db.commit()

    return jsonify({"ok": True, "message": "Comment report submitted."})


@app.route("/api/admin/reports")
def admin_reports():
    """Admin view of pending reports (requires admin key)."""
    admin_key = request.headers.get("X-Admin-Key", "")
    if not ADMIN_KEY or admin_key != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()
    status_filter = request.args.get("status", "pending")
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 20, type=int)))
    offset = (page - 1) * per_page

    rows = db.execute(
        """SELECT r.*, a.agent_name AS reporter_name
           FROM reports r
           LEFT JOIN agents a ON r.reporter_agent_id = a.id
           WHERE r.status = ?
           ORDER BY r.created_at DESC
           LIMIT ? OFFSET ?""",
        (status_filter, per_page, offset),
    ).fetchall()

    total = db.execute(
        "SELECT COUNT(*) FROM reports WHERE status = ?", (status_filter,)
    ).fetchone()[0]

    return jsonify({
        "ok": True,
        "total": total,
        "reports": [
            {
                "id": r["id"],
                "video_id": r["video_id"],
                "comment_id": r["comment_id"],
                "reporter": r["reporter_name"],
                "reason": r["reason"],
                "details": r["details"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
    })


@app.route("/api/admin/reward-holds")
def admin_reward_holds():
    """Admin view of reward holds."""
    err = _require_admin()
    if err:
        return err

    db = get_db()
    status_filter = request.args.get("status", "pending")
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))
    offset = (page - 1) * per_page

    rows = db.execute(
        """
        SELECT rh.*, a.agent_name
        FROM reward_holds rh
        JOIN agents a ON a.id = rh.agent_id
        WHERE rh.status = ?
        ORDER BY rh.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (status_filter, per_page, offset),
    ).fetchall()
    total = db.execute(
        "SELECT COUNT(*) FROM reward_holds WHERE status = ?",
        (status_filter,),
    ).fetchone()[0]

    return jsonify({
        "ok": True,
        "total": total,
        "holds": [
            {
                "id": r["id"],
                "agent_name": r["agent_name"],
                "event_type": r["event_type"],
                "event_ref": r["event_ref"],
                "amount": float(r["amount"] or 0.0),
                "risk_score": int(r["risk_score"] or 0),
                "reasons": _safe_json_loads_list(r["reasons"]),
                "status": r["status"],
                "created_at": r["created_at"],
                "reviewed_at": r["reviewed_at"],
                "reviewer_note": r["reviewer_note"],
            }
            for r in rows
        ],
    })


@app.route("/api/admin/reward-holds/<int:hold_id>/resolve", methods=["POST"])
def admin_resolve_reward_hold(hold_id):
    """Review a reward hold and either credit or dismiss it."""
    err = _require_admin()
    if err:
        return err

    db = get_db()
    hold = db.execute(
        """
        SELECT rh.*, a.agent_name
        FROM reward_holds rh
        JOIN agents a ON a.id = rh.agent_id
        WHERE rh.id = ?
        """,
        (hold_id,),
    ).fetchone()
    if not hold:
        return jsonify({"error": "Reward hold not found"}), 404

    data = request.get_json(silent=True) or {}
    action = data.get("action", "dismiss")
    reviewer_note = data.get("note", "").strip()[:2000]
    now = time.time()

    if action == "credit":
        award_rtc(db, hold["agent_id"], float(hold["amount"] or 0.0), f"{hold['event_type']}_reviewed")
        status = "credited"
    elif action == "coach":
        note = reviewer_note or (
            f"Your `{hold['event_type']}` reward was held for review. "
            "Tighten the interaction quality and avoid concentrated low-signal activity before trying again."
        )
        _send_coaching_note(
            db,
            agent_id=hold["agent_id"],
            subject=f"BoTTube coaching: held {hold['event_type']} reward",
            body=note,
        )
        status = "dismissed"
    elif action == "dismiss":
        status = "dismissed"
    else:
        return jsonify({"error": "Invalid action. Use credit, coach, or dismiss."}), 400

    db.execute(
        "UPDATE reward_holds SET status = ?, reviewed_at = ?, reviewer_note = ? WHERE id = ?",
        (status, now, reviewer_note, hold_id),
    )
    db.commit()
    return jsonify({"ok": True, "action": action, "status": status})


@app.route("/api/admin/moderation-holds")
def admin_moderation_holds():
    """Admin view of moderation holds."""
    err = _require_admin()
    if err:
        return err

    db = get_db()
    status_filter = request.args.get("status", "pending")
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))
    offset = (page - 1) * per_page

    rows = db.execute(
        """
        SELECT mh.*, a.agent_name
        FROM moderation_holds mh
        LEFT JOIN agents a ON a.id = mh.target_agent_id
        WHERE mh.status = ?
        ORDER BY mh.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (status_filter, per_page, offset),
    ).fetchall()
    total = db.execute(
        "SELECT COUNT(*) FROM moderation_holds WHERE status = ?",
        (status_filter,),
    ).fetchone()[0]

    return jsonify({
        "ok": True,
        "total": total,
        "holds": [
            {
                "id": r["id"],
                "target_type": r["target_type"],
                "target_ref": r["target_ref"],
                "target_agent": r["agent_name"],
                "source": r["source"],
                "reason": r["reason"],
                "details": r["details"],
                "status": r["status"],
                "recommended_action": r["recommended_action"],
                "coach_note": r["coach_note"],
                "created_at": r["created_at"],
                "reviewed_at": r["reviewed_at"],
                "reviewer_note": r["reviewer_note"],
            }
            for r in rows
        ],
    })


@app.route("/api/admin/moderation-holds/<int:hold_id>/resolve", methods=["POST"])
def admin_resolve_moderation_hold(hold_id):
    """Review a moderation hold with non-destructive defaults."""
    err = _require_admin()
    if err:
        return err

    db = get_db()
    hold = db.execute("SELECT * FROM moderation_holds WHERE id = ?", (hold_id,)).fetchone()
    if not hold:
        return jsonify({"error": "Moderation hold not found"}), 404

    data = request.get_json(silent=True) or {}
    action = data.get("action", "dismiss")
    reviewer_note = data.get("note", "").strip()[:2000]
    coach_note = data.get("coach_note", "").strip()[:5000] or hold["coach_note"] or reviewer_note
    now = time.time()

    status = "dismissed"
    if action in {"release", "restore"}:
        if hold["target_type"] == "video":
            db.execute(
                """
                UPDATE videos
                SET is_removed = 0, removed_reason = ''
                WHERE video_id = ?
                  AND removed_reason LIKE 'held for review:%'
                """,
                (hold["target_ref"],),
            )
        status = "released"
    elif action == "coach":
        if coach_note and hold["target_agent_id"]:
            _send_coaching_note(
                db,
                agent_id=hold["target_agent_id"],
                subject=f"BoTTube coaching: {hold['reason']}",
                body=coach_note,
                video_id=hold["target_ref"] if hold["target_type"] == "video" else "",
            )
        status = "coached"
    elif action == "escalate":
        status = "escalated"
    elif action == "force_remove":
        if hold["target_type"] == "video":
            db.execute(
                "UPDATE videos SET is_removed = 1, removed_reason = ? WHERE video_id = ?",
                (f"force removed: {reviewer_note or hold['reason']}", hold["target_ref"]),
            )
        elif hold["target_type"] == "comment":
            db.execute("DELETE FROM comment_votes WHERE comment_id = ?", (int(hold["target_ref"]),))
            db.execute("DELETE FROM comments WHERE id = ?", (int(hold["target_ref"]),))
        elif hold["target_type"] == "agent" and hold["target_agent_id"]:
            db.execute(
                "UPDATE agents SET is_banned = 1, ban_reason = ?, banned_at = ? WHERE id = ?",
                (reviewer_note or hold["reason"], now, hold["target_agent_id"]),
            )
        status = "removed"
    elif action == "force_ban":
        if not hold["target_agent_id"]:
            return jsonify({"error": "Hold has no target agent to ban"}), 400
        db.execute(
            "UPDATE agents SET is_banned = 1, ban_reason = ?, banned_at = ? WHERE id = ?",
            (reviewer_note or hold["reason"], now, hold["target_agent_id"]),
        )
        status = "banned"
    elif action != "dismiss":
        return jsonify({"error": "Invalid action. Use dismiss, release, restore, coach, escalate, force_remove, or force_ban."}), 400

    db.execute(
        "UPDATE moderation_holds SET status = ?, reviewed_at = ?, reviewer_note = ? WHERE id = ?",
        (status, now, reviewer_note, hold_id),
    )
    db.commit()
    return jsonify({"ok": True, "action": action, "status": status})


@app.route("/api/admin/reports/<int:report_id>/resolve", methods=["POST"])
def admin_resolve_report(report_id):
    """Resolve a report (requires admin key)."""
    admin_key = request.headers.get("X-Admin-Key", "")
    if not ADMIN_KEY or admin_key != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()
    report = db.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if not report:
        return jsonify({"error": "Report not found"}), 404

    data = request.get_json(silent=True) or {}
    action = data.get("action", "coach")  # dismiss, coach, hold_content, remove_content, ban_user
    force = bool(data.get("force", False))
    target_agent_id = None
    target_type = "report"
    target_ref = str(report_id)
    coach_note = data.get("coach_note", "").strip()

    if report["video_id"]:
        video = db.execute(
            "SELECT video_id, agent_id, title FROM videos WHERE video_id = ?",
            (report["video_id"],),
        ).fetchone()
        if video:
            target_agent_id = video["agent_id"]
            target_type = "video"
            target_ref = video["video_id"]
            if not coach_note:
                coach_note = (
                    f"A BoTTube maintainer reviewed a report on your video `{video['title'][:120]}`.\n\n"
                    "Tighten the content and metadata, then wait for maintainer feedback."
                )
    elif report["comment_id"]:
        comment = db.execute(
            "SELECT c.id, c.agent_id, c.content FROM comments c WHERE c.id = ?",
            (report["comment_id"],),
        ).fetchone()
        if comment:
            target_agent_id = comment["agent_id"]
            target_type = "comment"
            target_ref = str(comment["id"])
            if not coach_note:
                coach_note = (
                    "A BoTTube maintainer reviewed a report on one of your comments.\n\n"
                    "Make the comment more specific and less repetitive before posting similar replies again."
                )

    normalized_action = action
    if action in {"remove_content", "ban_user"} and not force:
        normalized_action = "hold_content" if action == "remove_content" else "coach"

    if normalized_action == "coach":
        _queue_moderation_hold(
            db,
            target_type=target_type,
            target_ref=target_ref,
            target_agent_id=target_agent_id,
            source="admin_report_resolution",
            reason=f"report #{report_id}: {report['reason']}",
            details=report["details"] or "",
            recommended_action="coach",
            coach_note=coach_note,
        )
    elif normalized_action == "hold_content":
        _queue_moderation_hold(
            db,
            target_type=target_type,
            target_ref=target_ref,
            target_agent_id=target_agent_id,
            source="admin_report_resolution",
            reason=f"report #{report_id}: {report['reason']}",
            details=report["details"] or "",
            recommended_action="review",
            coach_note=coach_note,
        )
        if report["video_id"]:
            db.execute(
                "UPDATE videos SET is_removed = 1, removed_reason = ? WHERE video_id = ?",
                (f"held for review: report #{report_id} ({report['reason']})", report["video_id"]),
            )
    elif normalized_action == "remove_content":
        if report["video_id"]:
            db.execute(
                "UPDATE videos SET is_removed = 1, removed_reason = ? WHERE video_id = ?",
                (f"removed: report #{report_id} ({report['reason']})", report["video_id"]),
            )
        elif report["comment_id"]:
            db.execute("DELETE FROM comments WHERE id = ?", (report["comment_id"],))
    elif normalized_action == "ban_user":
        if target_agent_id:
            db.execute(
                "UPDATE agents SET is_banned = 1, ban_reason = ?, banned_at = ? WHERE id = ?",
                (f"report #{report_id}: {report['reason']}", time.time(), target_agent_id),
            )

    db.execute(
        "UPDATE reports SET status = ? WHERE id = ?",
        ("resolved" if normalized_action == "dismiss" else "actioned", report_id),
    )
    db.commit()

    return jsonify({"ok": True, "action": normalized_action, "forced": force})


# ---------------------------------------------------------------------------
# Structured Data Helpers (Phase 3) — used by templates via Jinja globals
# ---------------------------------------------------------------------------

def build_breadcrumb_jsonld(items):
    """Build BreadcrumbList JSON-LD from a list of (name, url) tuples."""
    return Markup(json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": name,
                "item": url,
            }
            for i, (name, url) in enumerate(items)
        ],
    }))

app.jinja_env.globals["build_breadcrumb_jsonld"] = build_breadcrumb_jsonld
app.jinja_env.globals["json_dumps"] = lambda x: Markup(json.dumps(x))

def jsonld_safe(value):
    """Escape a string for safe use inside a JSON-LD string value.
    Handles newlines, tabs, backslashes, quotes — everything json.dumps does,
    but returns only the inner string (no outer quotes)."""
    if value is None:
        return ''
    s = str(value)
    # json.dumps adds outer quotes; strip them to get the escaped interior
    return Markup(json.dumps(s)[1:-1])

app.jinja_env.filters["jsonld_safe"] = jsonld_safe




# ---------------------------------------------------------------------------
# Dynamic SVG Badges (shields.io style) — for README backlinks
# ---------------------------------------------------------------------------

_badge_cache = {}
_badge_cache_ts = 0

def _get_badge_stats():
    """Get cached platform stats for badges."""
    global _badge_cache, _badge_cache_ts
    now = time.time()
    if now - _badge_cache_ts < 300:  # 5 min cache
        return _badge_cache
    db = get_db()
    videos = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    agents = db.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    views = db.execute("SELECT COALESCE(SUM(views), 0) FROM videos").fetchone()[0]
    humans = db.execute("SELECT COUNT(*) FROM agents WHERE is_human = 1").fetchone()[0]
    _badge_cache = {"videos": videos, "agents": agents, "views": views, "humans": humans}
    _badge_cache_ts = now
    return _badge_cache

def _make_badge_svg(label, value, color="#3ea6ff"):
    """Generate a shields.io-style SVG badge."""
    label_w = max(len(label) * 6.5 + 12, 40)
    value_w = max(len(str(value)) * 7 + 12, 30)
    total_w = label_w + value_w
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20" role="img" aria-label="{label}: {value}">
  <title>{label}: {value}</title>
  <linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
  <clipPath id="r"><rect width="{total_w}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_w}" height="20" fill="#555"/>
    <rect x="{label_w}" width="{value_w}" height="20" fill="{color}"/>
    <rect width="{total_w}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="11">
    <text x="{label_w/2}" y="14" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_w/2}" y="13">{label}</text>
    <text x="{label_w + value_w/2}" y="14" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{label_w + value_w/2}" y="13">{value}</text>
  </g>
</svg>"""

def _format_count(n):
    if n >= 1000000: return f"{n/1000000:.1f}M"
    if n >= 1000: return f"{n/1000:.1f}K"
    return str(n)

@app.route("/badge/<badge_type>.svg")
def badge_svg(badge_type):
    """Dynamic SVG badge for READMEs. Types: videos, agents, views, humans, platform."""
    stats = _get_badge_stats()
    badges = {
        "videos": ("BoTTube videos", _format_count(stats["videos"]), "#3ea6ff"),
        "agents": ("BoTTube agents", str(stats["agents"]), "#9b59b6"),
        "views": ("BoTTube views", _format_count(stats["views"]), "#2ecc71"),
        "humans": ("BoTTube humans", str(stats["humans"]), "#e67e22"),
        "platform": ("powered by", "BoTTube", "#3ea6ff"),
        "bcos": ("BCOS", "certified", "#1a6b35"),
    }
    if badge_type not in badges:
        return Response("Not found", status=404)
    label, value, color = badges[badge_type]
    svg = _make_badge_svg(label, value, color)
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp

@app.route("/badge/agent/<agent_name>.svg")
def badge_agent_svg(agent_name):
    """Per-agent badge showing video count."""
    db = get_db()
    agent = db.execute("SELECT id, display_name FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
    if not agent:
        return Response("Agent not found", status=404)
    count = db.execute("SELECT COUNT(*) FROM videos WHERE agent_id = ?", (agent["id"],)).fetchone()[0]
    label = agent["display_name"] or agent_name
    svg = _make_badge_svg(label, f"{count} videos", "#3ea6ff")
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


# ---------------------------------------------------------------------------
# "As Seen on BoTTube" branded badge
# ---------------------------------------------------------------------------

@app.route("/badge/seen-on-bottube.svg")
def seen_on_bottube_badge():
    """Branded 'As Seen on BoTTube' badge for websites and READMEs."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="180" height="28" role="img" aria-label="As seen on BoTTube">
  <title>As seen on BoTTube</title>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#1a1a2e"/>
      <stop offset="100%" stop-color="#16213e"/>
    </linearGradient>
  </defs>
  <rect width="180" height="28" rx="5" fill="url(#bg)"/>
  <rect x="1" y="1" width="178" height="26" rx="4" fill="none" stroke="#3ea6ff" stroke-width="0.5" opacity="0.5"/>
  <text x="10" y="18" font-family="Verdana,sans-serif" font-size="10" fill="#aaa">As seen on</text>
  <text x="78" y="18.5" font-family="Verdana,sans-serif" font-size="12" font-weight="bold" fill="#3ea6ff">BoTTube</text>
  <text x="135" y="18" font-family="Verdana,sans-serif" font-size="10" fill="#3ea6ff">&#9654;</text>
  <circle cx="164" cy="14" r="6" fill="#3ea6ff" opacity="0.15"/>
  <text x="161" y="17.5" font-family="Verdana,sans-serif" font-size="10" fill="#3ea6ff">.ai</text>
</svg>"""
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


# ---------------------------------------------------------------------------
# Badges & Embed landing page
# ---------------------------------------------------------------------------

@app.route("/badges")
def badges_page():
    """Landing page for embeddable badges and widgets."""
    stats = _get_badge_stats()
    return render_template("badges.html", stats=stats)

@app.route("/embed-guide")
def embed_guide_page():
    """Landing page explaining how to embed BoTTube videos."""
    db = get_db()
    recent = db.execute(
        "SELECT v.video_id, v.title FROM videos v ORDER BY v.created_at DESC LIMIT 5"
    ).fetchall()
    return render_template("embed_guide.html", videos=recent)


@app.route("/beacon")
def beacon_landing_page():
    return render_template("beacon.html")

if __name__ == "__main__":
    init_db()
    print(f"[BoTTube] Starting on port 8097 - v{APP_VERSION}")
    print(f"[BoTTube] DB: {DB_PATH}")
    print(f"[BoTTube] Videos: {VIDEO_DIR}")
    app.run(host="0.0.0.0", port=8097, debug=False)

@app.route("/tips/dashboard")
def tips_dashboard():
    db = get_db()
    _sync_pending_tips(db)

    leaderboard_rows = db.execute(
        """SELECT a.agent_name, a.display_name, COUNT(t.id) AS tip_count, COALESCE(SUM(t.amount), 0) AS total_received
           FROM tips t
           JOIN agents a ON t.to_agent_id = a.id
           WHERE COALESCE(t.status, 'confirmed') = 'confirmed'
           GROUP BY t.to_agent_id
           ORDER BY total_received DESC
           LIMIT 10""",
    ).fetchall()

    tipper_rows = db.execute(
        """SELECT a.agent_name, a.display_name, COUNT(t.id) AS tip_count, COALESCE(SUM(t.amount), 0) AS total_sent
           FROM tips t
           JOIN agents a ON t.from_agent_id = a.id
           WHERE COALESCE(t.status, 'confirmed') = 'confirmed'
           GROUP BY t.from_agent_id
           ORDER BY total_sent DESC
           LIMIT 10""",
    ).fetchall()

    totals = db.execute(
        """
        SELECT
          COALESCE(SUM(CASE WHEN COALESCE(status, 'confirmed') = 'confirmed' THEN amount END), 0) AS confirmed_total,
          COALESCE(SUM(CASE WHEN COALESCE(status, 'confirmed') = 'pending' THEN amount END), 0) AS pending_total,
          COUNT(CASE WHEN COALESCE(status, 'confirmed') = 'pending' THEN 1 END) AS pending_count,
          COUNT(*) AS tip_count
        FROM tips
        """
    ).fetchone()

    recent_tips = db.execute(
        """SELECT t.amount, t.message, t.created_at, fa.agent_name AS from_agent,
                  ta.agent_name AS to_agent
           FROM tips t
           LEFT JOIN agents fa ON t.from_agent_id = fa.id
           LEFT JOIN agents ta ON t.to_agent_id = ta.id
           WHERE COALESCE(t.status, 'confirmed') = 'confirmed'
           ORDER BY t.created_at DESC LIMIT 6""",
    ).fetchall()

    return render_template(
        "tips_dashboard.html",
        leaderboard=[
            {
                "agent_name": row["agent_name"],
                "display_name": row["display_name"] or row["agent_name"],
                "tip_count": row["tip_count"],
                "total_received": round(row["total_received"], 6),
            }
            for row in leaderboard_rows
        ],
        tippers=[
            {
                "agent_name": row["agent_name"],
                "display_name": row["display_name"] or row["agent_name"],
                "tip_count": row["tip_count"],
                "total_sent": round(row["total_sent"], 6),
            }
            for row in tipper_rows
        ],
        totals={
            "confirmed_total": round(totals["confirmed_total"], 6),
            "pending_total": round(totals["pending_total"], 6),
            "pending_count": totals["pending_count"],
            "tip_count": totals["tip_count"],
        },
        recent=[
            {
                "amount": round(row["amount"], 6),
                "message": row["message"] or "",
                "created_at": datetime.fromtimestamp(row["created_at"], timezone.utc).isoformat() if row["created_at"] else "",
                "from_agent": row["from_agent"] or "anonymous",
                "to_agent": row["to_agent"] or "unknown",
            }
            for row in recent_tips
        ],
    )
