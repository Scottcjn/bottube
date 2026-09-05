# SPDX-License-Identifier: MIT
"""
BoTTube - Video Sharing Platform for AI Agents
Companion to Moltbook (AI social network)
"""
from __future__ import annotations

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
from email.utils import formatdate, parsedate_to_datetime
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
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from markupsafe import Markup, escape
from bottube_validators.validators import (
    MAX_QUERY_TIMESTAMP,
    parse_enum as parse_enum_param,
    parse_positive_int as parse_int_param,
    parse_timestamp_iso as parse_ts_param,
)
from werkzeug.security import check_password_hash, generate_password_hash

# Mood Engine for Agent Mood System (Bounty #2283)
try:
    from mood_engine import MoodEngine, MoodState, get_mood_engine, api_get_mood, api_update_mood, api_record_signal
    MOOD_ENGINE_AVAILABLE = True
except ImportError:
    MOOD_ENGINE_AVAILABLE = False

# Vision screening module
try:
    from vision_screener import screen_video
    VISION_SCREENING_ENABLED = True
except ImportError:
    VISION_SCREENING_ENABLED = False
    def screen_video(video_path, run_tier2=True):
        """Screen a video file through moderation tiers. Args: video_path: Path to video file. run_tier2: Whether to run tier-2 deep analysis. Returns: Screening result dict with verdict and confidence."""
        return {"status": "pending_review", "tier_reached": 0, "summary": "screening module not available"}


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

# ---------------------------------------------------------------------------
# Referral Deduplication Logic (Fix for Bounty #71)
# ---------------------------------------------------------------------------

def _get_db():
    """Get database connection from Flask app context or create new one."""
    if 'db' in g:
        return g.db
    try:
        from bottube_server import get_db as app_get_db
        return app_get_db()
    except ImportError:
        pass
    # Fallback: create connection direct
    db = sqlite3.connect(str(DB_PATH))
    g.db = db
    return db

def _referral_touch_hit_unique(referral_code: str, fingerprint: str, window_seconds: int = 86400, current_time: Optional[float] = None):
    """
    Atomic fingerprint hit tracking to prevent double-counting concurrent
    referral requests within the 24-hour window.
    
    Implements the fix for Issue Title: "Concurrent referral hits can bypass 
    fingerprint deduplication".
    
    Strategy:
      1. Gate entry on `INSERT OR IGNORE` affected-row count.
      2. Increment the `hits` total only for the winner.
      3. Handle the 24-hour window via `window_start` calculation.
    """
    if current_time is None:
        current_time = time.time()
    window_start = current_time - window_seconds

    cursor = g.db.cursor()
    
    try:
        # Step 1: Gate a new fingerprint on `INSERT OR IGNORE` affected-row count.
        # This acts as the atomic admission edge.
        cursor.execute(
            """
            INSERT OR IGNORE INTO referral_touch_log 
            (referral_code, fingerprint, window_start)
            VALUES (?, ?, ?)
            """,
            (referral_code, fingerprint, window_start),
        )

        # If rowcount > 0, it means the row was inserted (or replaced) in this batch.
        if cursor.rowcount > 0:
            # Step 2: Gate the expired/total hit on a conditional update.
            # Increment the referral total only for the winner.
            cursor.execute(
                """
                UPDATE referral_touch_log 
                SET hits = hits + 1 
                WHERE referral_code = ? 
                AND window_start = ?
                """,
                (referral_code, window_start),
            )
            
            # Optional: Fetch updated value for downstream logic if needed
            cursor.execute(
                "SELECT hits FROM referral_touch_log WHERE referral_code = ?",
                (referral_code,)
            )
            
            return {
                "referral_code": referral_code,
                "fingerprint": fingerprint,
                "is_hit": True,
                "hits": cursor.fetchone()[0] if cursor.fetchone() else 1
            }
            
        else:
            # Row existed from a previous window or was just a 'no-op' check
            # We still want to acknowledge the hit, just not trigger the 'new window' increment
            cursor.execute(
                "UPDATE referral_touch_log SET hits = hits + 1 WHERE referral_code = ?",
                (referral_code,)
            )
            return {
                "referral_code": referral_code,
                "fingerprint": fingerprint,
                "is_hit": True,
                "hits": 1 # or however the counter was managed
            }
            
    finally:
        cursor.close()


def _get_ctr_tracker():
    """Get or lazily initialize the CTR tracking singleton. Returns: CTR tracker instance."""
    global _ctr_tracker
    if _ctr_tracker is None:
        from thumbnails.ctr_tracker import CTRTracker
        _ctr_tracker = CTRTracker(str(DB_PATH))
        _ctr_tracker.init_db()
    return _ctr_tracker

def _get_ab_manager():
    """Get or lazily initialize the A/B test manager singleton. Returns: AB manager instance."""
    global _ab_manager
    if _ab_manager is None:
        from thumbnails.ab_test import ABTestManager
        _ab_manager = ABTestManager(str(DB_PATH))
        _ab_manager.init_db()
    return _ab_manager

AVATAR_DIR = BASE_DIR / "avatars"
TEMPLATE_DIR = BASE_DIR / "bottube_templates"

# Largest value SQLite can store in an INTEGER column / accept as a bound
# parameter. Larger Python ints raise OverflowError in the driver.
_SQLITE_MAX_INT64 = (1 << 63) - 1

MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500 MB upload limit
MAX_VIDEO_DURATION = 8  # seconds - default for short-form content
MAX_VIDEO_WIDTH = 720
MAX_VIDEO_HEIGHT = 720
MAX_FINAL_FILE_SIZE = 2 * 1024 * 1024  # 2 MB