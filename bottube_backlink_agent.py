#!/usr/bin/env python3
"""
BoTTube Backlink Agent — Automated SEO directory submission, health monitoring,
and opportunity discovery.

White-hat only:
  - Auto-submits to directories (they expect submissions)
  - Monitors existing backlink health
  - Discovers forum/thread opportunities (human reviews before posting)
  - Rate-limited to avoid bans
  - Never auto-posts to forums or communities

Usage:
    python3 bottube_backlink_agent.py              # Run full daily cycle
    python3 bottube_backlink_agent.py --submit     # Submit to next pending directory
    python3 bottube_backlink_agent.py --check      # Check health of all live links
    python3 bottube_backlink_agent.py --discover   # Scan for new opportunities
    python3 bottube_backlink_agent.py --report     # Print daily report
    python3 bottube_backlink_agent.py --daemon     # Run as continuous daemon

Elyan Labs — https://bottube.ai
"""

import sqlite3
import requests
import time
import json
import hashlib
import logging
import argparse
import os
import sys
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse, quote_plus

# ── Configuration ────────────────────────────────────────────────────

BOTTUBE_URL = "https://bottube.ai"
BOTTUBE_GITHUB = "https://github.com/Scottcjn/bottube"
BOTTUBE_DESCRIPTION = (
    "BoTTube is the first video platform built for AI agents. "
    "Bots create, upload, and interact with video content alongside humans. "
    "Open API, Python SDK (pip install bottube), MIT licensed."
)
BOTTUBE_SHORT = "YouTube for AI agents — bots create, share, and watch videos"
BOTTUBE_TAGS = ["artificial-intelligence", "ai-agents", "video-platform",
                "open-source", "python", "api", "bot-platform"]
BOTTUBE_CATEGORY = "Artificial Intelligence"

DB_PATH = os.environ.get("BACKLINK_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "backlink_agent.db"))

# Rate limits
MAX_SUBMISSIONS_PER_DAY = 5
MIN_HOURS_BETWEEN_SAME_PLATFORM = 6
HEALTH_CHECK_INTERVAL_HOURS = 24
REDDIT_SCAN_DELAY_SEC = 3

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger("backlink_agent")


# ── Directory Database ───────────────────────────────────────────────

DIRECTORIES = [
    # Tier 1: High DA, AI/Tech focused
    {
        "name": "There's An AI For That",
        "url": "https://theresanaiforthat.com",
        "submit_url": "https://theresanaiforthat.com/submit/",
        "da": 70, "free": True, "auto_submit": False,
        "category": "ai_directory",
        "notes": "Manual form submission required",
    },
    {
        "name": "Futurepedia",
        "url": "https://www.futurepedia.io",
        "submit_url": "https://www.futurepedia.io/submit-tool",
        "da": 65, "free": True, "auto_submit": False,
        "category": "ai_directory",
    },
    {
        "name": "Toolify.ai",
        "url": "https://www.toolify.ai",
        "submit_url": "https://www.toolify.ai/submit",
        "da": 55, "free": True, "auto_submit": False,
        "category": "ai_directory",
    },
    {
        "name": "TopAI.tools",
        "url": "https://topai.tools",
        "submit_url": "https://topai.tools/submit",
        "da": 55, "free": True, "auto_submit": False,
        "category": "ai_directory",
    },
    {
        "name": "ToolPilot.ai",
        "url": "https://www.toolpilot.ai",
        "submit_url": "https://www.toolpilot.ai/submit",
        "da": 50, "free": True, "auto_submit": False,
        "category": "ai_directory",
    },
    {
        "name": "AI Scout",
        "url": "https://aiscout.net",
        "submit_url": "https://aiscout.net/submit/",
        "da": 40, "free": True, "auto_submit": False,
        "category": "ai_directory",
    },
    {
        "name": "AItoolsclub",
        "url": "https://www.aitoolsclub.com",
        "submit_url": "https://www.aitoolsclub.com/submit",
        "da": 40, "free": True, "auto_submit": False,
        "category": "ai_directory",
    },
    # Tier 2: High DA, general tech/startup
    {
        "name": "AlternativeTo",
        "url": "https://alternativeto.net",
        "submit_url": "https://alternativeto.net/submit/",
        "da": 80, "free": True, "auto_submit": False,
        "category": "tech_directory",
        "notes": "List as alternative to YouTube for AI",
    },
    {
        "name": "SaaSHub",
        "url": "https://www.saashub.com",
        "submit_url": "https://www.saashub.com/submit",
        "da": 70, "free": True, "auto_submit": False,
        "category": "tech_directory",
    },
    {
        "name": "BetaList",
        "url": "https://betalist.com",
        "submit_url": "https://betalist.com/submit",
        "da": 70, "free": True, "auto_submit": False,
        "category": "startup_directory",
    },
    {
        "name": "Indie Hackers",
        "url": "https://www.indiehackers.com",
        "submit_url": "https://www.indiehackers.com/products",
        "da": 75, "free": True, "auto_submit": False,
        "category": "startup_directory",
    },
    {
        "name": "Launching Next",
        "url": "https://www.launchingnext.com",
        "submit_url": "https://www.launchingnext.com/submit",
        "da": 55, "free": True, "auto_submit": False,
        "category": "startup_directory",
    },
    {
        "name": "SideProjectors",
        "url": "https://www.sideprojectors.com",
        "submit_url": "https://www.sideprojectors.com",
        "da": 50, "free": True, "auto_submit": False,
        "category": "startup_directory",
    },
    {
        "name": "DevPost",
        "url": "https://devpost.com",
        "submit_url": "https://devpost.com/software",
        "da": 75, "free": True, "auto_submit": False,
        "category": "dev_directory",
    },
    {
        "name": "SourceForge",
        "url": "https://sourceforge.net",
        "submit_url": "https://sourceforge.net/create/",
        "da": 90, "free": True, "auto_submit": False,
        "category": "dev_directory",
        "notes": "Open source project listing",
    },
    {
        "name": "F6S",
        "url": "https://www.f6s.com",
        "submit_url": "https://www.f6s.com/startup-register",
        "da": 70, "free": True, "auto_submit": False,
        "category": "startup_directory",
    },
    {
        "name": "StartupRanking",
        "url": "https://www.startupranking.com",
        "submit_url": "https://www.startupranking.com/startup/register",
        "da": 55, "free": True, "auto_submit": False,
        "category": "startup_directory",
    },
    {
        "name": "Startup Stash",
        "url": "https://startupstash.com",
        "submit_url": "https://startupstash.com/add-listing/",
        "da": 60, "free": True, "auto_submit": False,
        "category": "startup_directory",
    },
    # Tier 3: Very high DA, general
    {
        "name": "Crunchbase",
        "url": "https://www.crunchbase.com",
        "submit_url": "https://www.crunchbase.com/register",
        "da": 90, "free": True, "auto_submit": False,
        "category": "business_directory",
        "notes": "Company profile, high authority",
    },
    {
        "name": "G2",
        "url": "https://www.g2.com",
        "submit_url": "https://sell.g2.com/create-a-profile",
        "da": 90, "free": True, "auto_submit": False,
        "category": "review_site",
    },
    {
        "name": "Capterra",
        "url": "https://www.capterra.com",
        "submit_url": "https://www.capterra.com/vendors/sign-up",
        "da": 90, "free": True, "auto_submit": False,
        "category": "review_site",
    },
    # Content platforms (for blog syndication)
    {
        "name": "Dev.to",
        "url": "https://dev.to",
        "submit_url": "https://dev.to/new",
        "da": 80, "free": True, "auto_submit": False,
        "category": "content_platform",
        "notes": "Cross-post blog articles",
    },
    {
        "name": "Hashnode",
        "url": "https://hashnode.com",
        "submit_url": "https://hashnode.com/onboard",
        "da": 75, "free": True, "auto_submit": False,
        "category": "content_platform",
    },
    {
        "name": "Medium",
        "url": "https://medium.com",
        "submit_url": "https://medium.com/new-story",
        "da": 90, "free": True, "auto_submit": False,
        "category": "content_platform",
        "notes": "Nofollow but high traffic",
    },
    # Social bookmarking
    {
        "name": "Mix (StumbleUpon)",
        "url": "https://mix.com",
        "submit_url": "https://mix.com",
        "da": 60, "free": True, "auto_submit": False,
        "category": "social_bookmark",
    },
    {
        "name": "Flipboard",
        "url": "https://flipboard.com",
        "submit_url": "https://flipboard.com",
        "da": 85, "free": True, "auto_submit": False,
        "category": "social_bookmark",
    },
    # ── Unique / Creative Targets ────────────────────────────────────
    # AI-specific directories
    {
        "name": "Future Tools",
        "url": "https://www.futuretools.io",
        "submit_url": "https://www.futuretools.io/submit-a-tool",
        "da": 55, "free": True, "auto_submit": False,
        "category": "ai_directory",
        "notes": "Matt Wolfe newsletter — favors open source",
    },
    {
        "name": "Ben's Bites",
        "url": "https://news.bensbites.co",
        "submit_url": "https://news.bensbites.co",
        "da": 55, "free": True, "auto_submit": False,
        "category": "ai_directory",
        "notes": "AI newsletter + tool directory — huge reach",
    },
    {
        "name": "AI Valley",
        "url": "https://aivalley.ai",
        "submit_url": "https://aivalley.ai/submit-tool/",
        "da": 40, "free": True, "auto_submit": False,
        "category": "ai_directory",
    },
    {
        "name": "Papers With Code",
        "url": "https://paperswithcode.com",
        "submit_url": "https://paperswithcode.com/",
        "da": 75, "free": True, "auto_submit": False,
        "category": "academic",
        "notes": "Submit under Video Generation. Proof of Antiquity also novel.",
    },
    # Developer / open-source directories
    {
        "name": "DevHunt",
        "url": "https://devhunt.org",
        "submit_url": "https://devhunt.org/",
        "da": 40, "free": True, "auto_submit": False,
        "category": "dev_directory",
        "notes": "Product Hunt for dev tools — launch here",
    },
    {
        "name": "Open Source Alternative",
        "url": "https://www.opensourcealternative.to",
        "submit_url": "https://www.opensourcealternative.to/",
        "da": 45, "free": True, "auto_submit": False,
        "category": "dev_directory",
        "notes": "Alt to Synthesia/HeyGen/D-ID. Open source angle.",
    },
    {
        "name": "Stackshare",
        "url": "https://stackshare.io",
        "submit_url": "https://stackshare.io/",
        "da": 70, "free": True, "auto_submit": False,
        "category": "dev_directory",
        "notes": "Create stack page showing Python/Flask/SQLite stack",
    },
    {
        "name": "Slant.co",
        "url": "https://www.slant.co",
        "submit_url": "https://www.slant.co/",
        "da": 55, "free": True, "auto_submit": False,
        "category": "tech_directory",
        "notes": "Add to 'best AI video tools' Q&A",
    },
    {
        "name": "Open Hub",
        "url": "https://www.openhub.net",
        "submit_url": "https://www.openhub.net/",
        "da": 65, "free": True, "auto_submit": False,
        "category": "dev_directory",
        "notes": "Auto-analyzes repos, creates detailed pages",
    },
    {
        "name": "Console.dev",
        "url": "https://console.dev",
        "submit_url": "https://console.dev/",
        "da": 55, "free": True, "auto_submit": False,
        "category": "dev_directory",
        "notes": "Dev tools newsletter — editorial review",
    },
    # Very high DA platforms
    {
        "name": "Product Hunt",
        "url": "https://www.producthunt.com",
        "submit_url": "https://www.producthunt.com/posts/new",
        "da": 90, "free": True, "auto_submit": False,
        "category": "launch_platform",
        "notes": "PLAN A LAUNCH DAY. Prepare assets first.",
    },
    {
        "name": "Hacker News Show HN",
        "url": "https://news.ycombinator.com",
        "submit_url": "https://news.ycombinator.com/submit",
        "da": 90, "free": True, "auto_submit": False,
        "category": "community",
        "notes": "Show HN: BoTTube — AI agents create videos (MIT)",
    },
    {
        "name": "DockerHub",
        "url": "https://hub.docker.com",
        "submit_url": "https://hub.docker.com/",
        "da": 90, "free": True, "auto_submit": False,
        "category": "dev_directory",
        "notes": "Publish Docker image if containerized",
    },
    {
        "name": "Hugging Face Spaces",
        "url": "https://huggingface.co",
        "submit_url": "https://huggingface.co/new-space",
        "da": 80, "free": True, "auto_submit": False,
        "category": "ai_directory",
        "notes": "Create Gradio demo of agent-to-video pipeline",
    },
    # Review & comparison platforms
    {
        "name": "TrustRadius",
        "url": "https://www.trustradius.com",
        "submit_url": "https://www.trustradius.com/",
        "da": 70, "free": True, "auto_submit": False,
        "category": "review_site",
    },
    # Academic / research
    {
        "name": "Zenodo (CERN)",
        "url": "https://zenodo.org",
        "submit_url": "https://zenodo.org/deposit/new",
        "da": 80, "free": True, "auto_submit": False,
        "category": "academic",
        "notes": "Publish AI video dataset + get DOI",
    },
    {
        "name": "Kaggle Datasets",
        "url": "https://www.kaggle.com",
        "submit_url": "https://www.kaggle.com/datasets",
        "da": 90, "free": True, "auto_submit": False,
        "category": "academic",
        "notes": "Publish BoTTube video metadata dataset",
    },
    {
        "name": "ResearchGate",
        "url": "https://www.researchgate.net",
        "submit_url": "https://www.researchgate.net/",
        "da": 90, "free": True, "auto_submit": False,
        "category": "academic",
        "notes": "Create project page for RustChain/BoTTube research",
    },
    # RSS aggregators
    {
        "name": "Feedspot",
        "url": "https://www.feedspot.com",
        "submit_url": "https://www.feedspot.com/",
        "da": 70, "free": True, "auto_submit": False,
        "category": "rss_directory",
        "notes": "Submit bottube.ai/blog/rss",
    },
    # Open source specific
    {
        "name": "It's FOSS",
        "url": "https://itsfoss.com",
        "submit_url": "https://itsfoss.com/contact-us/",
        "da": 70, "free": True, "auto_submit": False,
        "category": "content_platform",
        "notes": "Pitch 'Open Source AI Video Platform' article",
    },
    {
        "name": "GitHub Sponsors",
        "url": "https://github.com/sponsors",
        "submit_url": "https://github.com/sponsors",
        "da": 100, "free": True, "auto_submit": False,
        "category": "dev_directory",
        "notes": "Set up sponsorship page — indexed by GitHub",
    },
    {
        "name": "OpenCollective",
        "url": "https://opencollective.com",
        "submit_url": "https://opencollective.com/create",
        "da": 75, "free": True, "auto_submit": False,
        "category": "dev_directory",
        "notes": "Create collective for BoTTube funding",
    },
    # Newsletter submissions
    {
        "name": "TLDR Newsletter",
        "url": "https://tldr.tech",
        "submit_url": "https://tldr.tech/",
        "da": 65, "free": True, "auto_submit": False,
        "category": "content_platform",
        "notes": "Submit to AI or Open Source edition (750K+ readers)",
    },
    # Blockchain/crypto specific (for RustChain angle)
    {
        "name": "Ergo Forum",
        "url": "https://www.ergoforum.org",
        "submit_url": "https://www.ergoforum.org/",
        "da": 35, "free": True, "auto_submit": False,
        "category": "community",
        "notes": "RustChain anchors to Ergo — community interest",
    },
]

# Reddit subreddits to monitor for opportunities
REDDIT_TARGETS = [
    {"sub": "artificial", "keywords": ["ai video", "ai content", "bot platform"]},
    {"sub": "MachineLearning", "keywords": ["video generation", "autonomous agent"]},
    {"sub": "SideProject", "keywords": ["launched", "ai platform", "open source"]},
    {"sub": "startups", "keywords": ["ai tool", "launch", "video platform"]},
    {"sub": "selfhosted", "keywords": ["video platform", "youtube alternative"]},
    {"sub": "Python", "keywords": ["bot framework", "video api", "ai agent"]},
    {"sub": "opensource", "keywords": ["ai platform", "video", "mit license"]},
    {"sub": "webdev", "keywords": ["ai platform", "video api"]},
    {"sub": "indiehackers", "keywords": ["ai launch", "saas", "side project"]},
    {"sub": "homelab", "keywords": ["ai server", "video hosting", "self hosted"]},
    {"sub": "CryptoCurrency", "keywords": ["proof of work alternative", "vintage hardware", "novel consensus"]},
    {"sub": "RetroComputing", "keywords": ["powerpc", "vintage hardware", "old computer useful"]},
    {"sub": "Filmmakers", "keywords": ["ai video", "automated video", "ai content creation"]},
    {"sub": "VideoEditing", "keywords": ["ai video tool", "automated editing", "text to video"]},
]


# ── Database Schema ──────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS directories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    submit_url TEXT,
    estimated_da INTEGER DEFAULT 0,
    category TEXT,
    is_free INTEGER DEFAULT 1,
    status TEXT DEFAULT 'pending',
    submitted_at TEXT,
    approved_at TEXT,
    live_url TEXT,
    last_checked TEXT,
    last_live_at TEXT,
    is_dofollow INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backlinks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    target_url TEXT DEFAULT 'https://bottube.ai',
    link_type TEXT DEFAULT 'directory',
    status TEXT DEFAULT 'pending',
    submitted_at TEXT,
    last_checked TEXT,
    last_live_at TEXT,
    is_dofollow INTEGER DEFAULT 0,
    anchor_text TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rate_limits (
    platform TEXT PRIMARY KEY,
    last_action_at TEXT,
    actions_today INTEGER DEFAULT 0,
    daily_reset_date TEXT,
    max_daily INTEGER DEFAULT 3
);

CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    body_preview TEXT,
    relevance_score REAL DEFAULT 0.0,
    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
    acted_on INTEGER DEFAULT 0,
    draft_response TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    target TEXT,
    success INTEGER DEFAULT 1,
    details TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS health_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backlink_id INTEGER,
    directory_id INTEGER,
    status TEXT,
    response_code INTEGER,
    checked_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


# ── Agent Core ───────────────────────────────────────────────────────

class BacklinkAgent:
    """White-hat backlink agent for BoTTube SEO."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self._init_db()
        self._seed_directories()

    def _init_db(self):
        self.db.executescript(SCHEMA)
        self.db.commit()

    def _seed_directories(self):
        """Seed directory database from DIRECTORIES list."""
        for d in DIRECTORIES:
            existing = self.db.execute(
                "SELECT id FROM directories WHERE name=?", (d["name"],)
            ).fetchone()
            if not existing:
                self.db.execute("""
                    INSERT INTO directories (name, url, submit_url, estimated_da,
                                             category, is_free, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (d["name"], d["url"], d.get("submit_url", ""),
                      d.get("da", 0), d.get("category", ""),
                      1 if d.get("free", True) else 0,
                      d.get("notes", "")))
        self.db.commit()

    def _log_action(self, action, target=None, success=True, details=None):
        self.db.execute(
            "INSERT INTO action_log (action, target, success, details) VALUES (?,?,?,?)",
            (action, target, 1 if success else 0, details))
        self.db.commit()

    # ── Rate Limiting ────────────────────────────────────────────────

    def _reset_daily_counters(self):
        """Reset daily counters if the date has changed."""
        today = datetime.now().strftime("%Y-%m-%d")
        self.db.execute("""
            UPDATE rate_limits SET actions_today = 0, daily_reset_date = ?
            WHERE daily_reset_date IS NULL OR daily_reset_date != ?
        """, (today, today))
        self.db.commit()

    def can_act(self, platform):
        """Check if we're within rate limits for a platform."""
        self._reset_daily_counters()
        row = self.db.execute(
            "SELECT last_action_at, actions_today, max_daily FROM rate_limits WHERE platform=?",
            (platform,)
        ).fetchone()
        if not row:
            return True

        # Check daily limit
        if row["actions_today"] >= row["max_daily"]:
            return False

        # Check minimum interval
        if row["last_action_at"]:
            last = datetime.fromisoformat(row["last_action_at"])
            if datetime.now() - last < timedelta(hours=MIN_HOURS_BETWEEN_SAME_PLATFORM):
                return False

        return True

    def record_action(self, platform):
        """Record that we acted on a platform."""
        now = datetime.now().isoformat()
        today = datetime.now().strftime("%Y-%m-%d")
        self.db.execute("""
            INSERT INTO rate_limits (platform, last_action_at, actions_today, daily_reset_date, max_daily)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(platform) DO UPDATE SET
                last_action_at = ?,
                actions_today = actions_today + 1
        """, (platform, now, today, MAX_SUBMISSIONS_PER_DAY, now))
        self.db.commit()

    def get_total_submissions_today(self):
        """Count total submissions across all platforms today."""
        today = datetime.now().strftime("%Y-%m-%d")
        row = self.db.execute("""
            SELECT COALESCE(SUM(actions_today), 0) as total
            FROM rate_limits WHERE daily_reset_date = ?
        """, (today,)).fetchone()
        return row["total"] if row else 0

    # ── Directory Submission Tracking ────────────────────────────────

    def get_pending_directories(self):
        """Get directories we haven't submitted to yet, ordered by DA."""
        return self.db.execute("""
            SELECT * FROM directories
            WHERE status = 'pending'
            ORDER BY estimated_da DESC
        """).fetchall()

    def mark_submitted(self, directory_name, live_url=None):
        """Mark a directory as submitted."""
        now = datetime.now().isoformat()
        self.db.execute("""
            UPDATE directories SET status = 'submitted', submitted_at = ?, live_url = ?
            WHERE name = ?
        """, (now, live_url, directory_name))

        # Also create a backlink record
        dir_row = self.db.execute(
            "SELECT * FROM directories WHERE name=?", (directory_name,)
        ).fetchone()
        if dir_row:
            self.db.execute("""
                INSERT INTO backlinks (source_name, source_url, link_type, status, submitted_at)
                VALUES (?, ?, 'directory', 'submitted', ?)
            """, (directory_name, dir_row["url"], now))

        self.db.commit()
        self.record_action(directory_name)
        self._log_action("submit_directory", directory_name, details=live_url)
        log.info(f"Marked {directory_name} as submitted")

    def mark_live(self, directory_name, live_url, is_dofollow=False):
        """Mark a directory listing as live (approved and visible)."""
        now = datetime.now().isoformat()
        self.db.execute("""
            UPDATE directories SET status = 'live', approved_at = ?,
                   live_url = ?, last_live_at = ?, is_dofollow = ?
            WHERE name = ?
        """, (now, live_url, now, 1 if is_dofollow else 0, directory_name))
        self.db.execute("""
            UPDATE backlinks SET status = 'live', last_live_at = ?,
                   is_dofollow = ?
            WHERE source_name = ?
        """, (now, 1 if is_dofollow else 0, directory_name))
        self.db.commit()
        self._log_action("mark_live", directory_name, details=live_url)
        log.info(f"Marked {directory_name} as LIVE at {live_url}")

    def submit_next(self):
        """Get the next pending directory and print submission instructions."""
        if self.get_total_submissions_today() >= MAX_SUBMISSIONS_PER_DAY:
            log.info(f"Daily limit reached ({MAX_SUBMISSIONS_PER_DAY} submissions)")
            return None

        pending = self.get_pending_directories()
        if not pending:
            log.info("No pending directories to submit to!")
            return None

        # Find one we can act on
        for d in pending:
            if self.can_act(d["name"]):
                print(f"\n{'='*60}")
                print(f"SUBMIT TO: {d['name']}")
                print(f"{'='*60}")
                print(f"URL:       {d['submit_url']}")
                print(f"Est. DA:   {d['estimated_da']}")
                print(f"Category:  {d['category']}")
                if d["notes"]:
                    print(f"Notes:     {d['notes']}")
                print(f"\nSubmission Details:")
                print(f"  Name:        BoTTube")
                print(f"  URL:         {BOTTUBE_URL}")
                print(f"  GitHub:      {BOTTUBE_GITHUB}")
                print(f"  Category:    {BOTTUBE_CATEGORY}")
                print(f"  Tagline:     {BOTTUBE_SHORT}")
                print(f"  Description: {BOTTUBE_DESCRIPTION}")
                print(f"  Tags:        {', '.join(BOTTUBE_TAGS)}")
                print(f"  Pricing:     Free / Open Source")
                print(f"\nAfter submitting, run:")
                print(f"  python3 {sys.argv[0]} --mark-submitted '{d['name']}'")
                print(f"{'='*60}\n")
                return d

        log.info("All pending directories are rate-limited. Try again later.")
        return None

    # ── Health Monitoring ────────────────────────────────────────────

    def check_health(self):
        """Check all submitted/live directory listings for link health."""
        dirs = self.db.execute("""
            SELECT * FROM directories
            WHERE status IN ('submitted', 'live', 'approved')
            AND live_url IS NOT NULL
        """).fetchall()

        if not dirs:
            log.info("No live/submitted links to check")
            return

        results = {"live": 0, "dead": 0, "error": 0}
        headers = {"User-Agent": "Mozilla/5.0 (compatible; BoTTubeHealthCheck/1.0)"}

        for d in dirs:
            try:
                resp = requests.get(d["live_url"], headers=headers, timeout=15,
                                    allow_redirects=True)
                now = datetime.now().isoformat()

                # Check if our URL appears on the page
                page_text = resp.text.lower()
                is_live = ("bottube" in page_text or
                           "bottube.ai" in page_text or
                           "elyan labs" in page_text)

                # Check dofollow
                is_dofollow = False
                if is_live and "bottube.ai" in page_text:
                    # Simple check: if there's a link without rel="nofollow"
                    if 'href="https://bottube.ai"' in resp.text:
                        nofollow_pattern = re.search(
                            r'<a[^>]*href="https://bottube\.ai"[^>]*rel="nofollow"',
                            resp.text, re.IGNORECASE)
                        is_dofollow = nofollow_pattern is None

                status = "live" if is_live else "not_found"
                self.db.execute("""
                    UPDATE directories SET last_checked = ?, status = ?,
                           is_dofollow = ?
                    WHERE id = ?
                """, (now, status if is_live else d["status"],
                      1 if is_dofollow else 0, d["id"]))

                if is_live:
                    self.db.execute(
                        "UPDATE directories SET last_live_at = ? WHERE id = ?",
                        (now, d["id"]))
                    results["live"] += 1
                    log.info(f"  LIVE: {d['name']} ({'dofollow' if is_dofollow else 'nofollow'})")
                else:
                    results["dead"] += 1
                    log.warning(f"  NOT FOUND: {d['name']} at {d['live_url']}")

                # Record health history
                self.db.execute("""
                    INSERT INTO health_history (directory_id, status, response_code)
                    VALUES (?, ?, ?)
                """, (d["id"], status, resp.status_code))

            except requests.RequestException as e:
                results["error"] += 1
                log.error(f"  ERROR: {d['name']} — {e}")
                self.db.execute("""
                    INSERT INTO health_history (directory_id, status, response_code)
                    VALUES (?, 'error', 0)
                """, (d["id"],))

        self.db.commit()
        print(f"\nHealth Check: {results['live']} live, "
              f"{results['dead']} not found, {results['error']} errors")
        self._log_action("health_check", details=json.dumps(results))

    # ── Opportunity Discovery ────────────────────────────────────────

    def scan_reddit(self):
        """Scan Reddit for relevant threads where BoTTube could be mentioned."""
        headers = {"User-Agent": "BoTTubeResearch/1.0 (by /u/crypteauxcajun)"}
        total_found = 0

        for target in REDDIT_TARGETS:
            sub = target["sub"]
            for kw in target["keywords"]:
                if not self.can_act(f"reddit_scan_{sub}"):
                    continue

                url = (f"https://www.reddit.com/r/{sub}/search.json"
                       f"?q={quote_plus(kw)}&sort=new&t=week&limit=10")
                try:
                    resp = requests.get(url, headers=headers, timeout=10)
                    if resp.status_code == 429:
                        log.warning("Reddit rate limited, backing off")
                        time.sleep(60)
                        continue
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    children = data.get("data", {}).get("children", [])

                    for post in children:
                        pd = post.get("data", {})
                        permalink = pd.get("permalink", "")
                        title = pd.get("title", "")
                        selftext = pd.get("selftext", "")[:300]
                        score = pd.get("score", 0)
                        num_comments = pd.get("num_comments", 0)

                        # Skip low-engagement posts
                        if score < 2 and num_comments < 2:
                            continue

                        full_url = f"https://reddit.com{permalink}"
                        relevance = self._score_relevance(title + " " + selftext)

                        if relevance >= 0.2:
                            try:
                                self.db.execute("""
                                    INSERT OR IGNORE INTO opportunities
                                    (platform, url, title, body_preview, relevance_score)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (f"reddit/r/{sub}", full_url, title,
                                      selftext[:300], relevance))
                                total_found += 1
                            except sqlite3.IntegrityError:
                                pass  # Already tracked

                except requests.RequestException as e:
                    log.warning(f"Reddit scan failed for r/{sub}/{kw}: {e}")

                time.sleep(REDDIT_SCAN_DELAY_SEC)

            self.record_action(f"reddit_scan_{sub}")

        self.db.commit()
        log.info(f"Reddit scan complete: {total_found} new opportunities found")
        self._log_action("reddit_scan", details=f"{total_found} opportunities")

    def scan_hackernews(self):
        """Scan Hacker News for relevant threads."""
        keywords = ["ai video", "ai agent", "bot platform", "youtube alternative",
                     "video generation", "ai content creation"]
        total_found = 0

        for kw in keywords:
            url = f"https://hn.algolia.com/api/v1/search_by_date?query={quote_plus(kw)}&tags=story&hitsPerPage=10"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    continue

                hits = resp.json().get("hits", [])
                for hit in hits:
                    title = hit.get("title", "")
                    story_url = f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
                    points = hit.get("points", 0)
                    comments = hit.get("num_comments", 0)

                    if points < 3 and comments < 3:
                        continue

                    relevance = self._score_relevance(title)
                    if relevance >= 0.2:
                        try:
                            self.db.execute("""
                                INSERT OR IGNORE INTO opportunities
                                (platform, url, title, relevance_score)
                                VALUES (?, ?, ?, ?)
                            """, ("hackernews", story_url, title, relevance))
                            total_found += 1
                        except sqlite3.IntegrityError:
                            pass

            except requests.RequestException as e:
                log.warning(f"HN scan failed for '{kw}': {e}")

            time.sleep(1)

        self.db.commit()
        log.info(f"HN scan complete: {total_found} new opportunities found")
        self._log_action("hn_scan", details=f"{total_found} opportunities")

    def _score_relevance(self, text):
        """Score how relevant a thread is to BoTTube."""
        text_lower = text.lower()
        keywords = {
            "ai video": 0.3,
            "ai content": 0.2,
            "video generation": 0.3,
            "ai agent": 0.2,
            "bot platform": 0.3,
            "youtube alternative": 0.3,
            "autonomous": 0.1,
            "text to video": 0.2,
            "ai creator": 0.2,
            "video platform": 0.2,
            "open source ai": 0.15,
            "python sdk": 0.1,
            "content creation": 0.1,
        }
        score = sum(weight for kw, weight in keywords.items() if kw in text_lower)
        return min(score, 1.0)

    def show_opportunities(self, limit=20):
        """Show unacted opportunities sorted by relevance."""
        opps = self.db.execute("""
            SELECT * FROM opportunities
            WHERE acted_on = 0
            ORDER BY relevance_score DESC, discovered_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

        if not opps:
            print("No pending opportunities.")
            return

        print(f"\n{'='*70}")
        print(f"PENDING OPPORTUNITIES ({len(opps)} found)")
        print(f"{'='*70}")
        for o in opps:
            print(f"\n  [{o['relevance_score']:.1f}] {o['platform']}")
            print(f"  Title: {o['title'][:80]}")
            print(f"  URL:   {o['url']}")
            if o["body_preview"]:
                print(f"  Preview: {o['body_preview'][:100]}...")
            print(f"  Found: {o['discovered_at']}")

    def mark_opportunity_acted(self, opp_id, notes=None):
        """Mark an opportunity as acted on (human reviewed and responded)."""
        self.db.execute(
            "UPDATE opportunities SET acted_on = 1, notes = ? WHERE id = ?",
            (notes, opp_id))
        self.db.commit()

    # ── Reporting ────────────────────────────────────────────────────

    def report(self):
        """Generate comprehensive status report."""
        print(f"\n{'='*60}")
        print(f"  BOTTUBE BACKLINK AGENT — STATUS REPORT")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}")

        # Directory status
        for status in ["pending", "submitted", "live", "dead", "not_found"]:
            count = self.db.execute(
                "SELECT COUNT(*) as c FROM directories WHERE status=?", (status,)
            ).fetchone()["c"]
            if count > 0:
                label = status.upper().ljust(12)
                print(f"  Directories {label}: {count}")

        # Dofollow vs nofollow
        dofollow = self.db.execute(
            "SELECT COUNT(*) as c FROM directories WHERE status='live' AND is_dofollow=1"
        ).fetchone()["c"]
        nofollow = self.db.execute(
            "SELECT COUNT(*) as c FROM directories WHERE status='live' AND is_dofollow=0"
        ).fetchone()["c"]
        if dofollow + nofollow > 0:
            print(f"\n  Live Links:  {dofollow} dofollow, {nofollow} nofollow")

        # Total estimated DA
        live_dirs = self.db.execute(
            "SELECT estimated_da FROM directories WHERE status='live'"
        ).fetchall()
        if live_dirs:
            avg_da = sum(d["estimated_da"] for d in live_dirs) / len(live_dirs)
            print(f"  Avg DA:      {avg_da:.0f}")

        # Opportunities
        opp_count = self.db.execute(
            "SELECT COUNT(*) as c FROM opportunities WHERE acted_on=0"
        ).fetchone()["c"]
        print(f"\n  Pending Opportunities: {opp_count}")

        # Today's activity
        today_subs = self.get_total_submissions_today()
        print(f"  Submissions Today:     {today_subs}/{MAX_SUBMISSIONS_PER_DAY}")

        # Recent actions
        recent = self.db.execute("""
            SELECT action, target, timestamp FROM action_log
            ORDER BY id DESC LIMIT 5
        """).fetchall()
        if recent:
            print(f"\n  Recent Actions:")
            for a in recent:
                print(f"    {a['timestamp'][:16]}  {a['action']}  {a['target'] or ''}")

        # Top directories by DA (pending)
        top_pending = self.db.execute("""
            SELECT name, estimated_da, category FROM directories
            WHERE status = 'pending'
            ORDER BY estimated_da DESC LIMIT 5
        """).fetchall()
        if top_pending:
            print(f"\n  Priority Submissions (highest DA pending):")
            for d in top_pending:
                print(f"    DA {d['estimated_da']:>3}  {d['name']} ({d['category']})")

        print(f"\n{'='*60}\n")

    # ── Daemon Mode ──────────────────────────────────────────────────

    def run_daily_cycle(self):
        """Run the full daily automation cycle."""
        log.info("Starting daily cycle...")

        # 1. Check health of existing links
        log.info("Phase 1: Health check")
        self.check_health()

        # 2. Submit to next pending directory (print instructions)
        log.info("Phase 2: Directory submission")
        self.submit_next()

        # 3. Scan for opportunities
        log.info("Phase 3: Opportunity discovery")
        self.scan_reddit()
        self.scan_hackernews()

        # 4. Report
        log.info("Phase 4: Report")
        self.report()

    def run_daemon(self, interval_hours=6):
        """Run as a continuous daemon."""
        log.info(f"Backlink agent daemon starting (interval: {interval_hours}h)")
        while True:
            try:
                self.run_daily_cycle()
            except Exception as e:
                log.error(f"Cycle error: {e}")
                self._log_action("cycle_error", details=str(e), success=False)
            log.info(f"Sleeping {interval_hours} hours...")
            time.sleep(interval_hours * 3600)


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BoTTube Backlink Agent")
    parser.add_argument("--submit", action="store_true",
                        help="Show next directory to submit to")
    parser.add_argument("--mark-submitted", metavar="NAME",
                        help="Mark a directory as submitted")
    parser.add_argument("--mark-live", nargs=2, metavar=("NAME", "URL"),
                        help="Mark a directory as live with its URL")
    parser.add_argument("--check", action="store_true",
                        help="Check health of all live links")
    parser.add_argument("--discover", action="store_true",
                        help="Scan Reddit/HN for opportunities")
    parser.add_argument("--opportunities", action="store_true",
                        help="Show pending opportunities")
    parser.add_argument("--report", action="store_true",
                        help="Print status report")
    parser.add_argument("--daemon", action="store_true",
                        help="Run as continuous daemon")
    parser.add_argument("--interval", type=int, default=6,
                        help="Daemon interval in hours (default: 6)")
    parser.add_argument("--db", default=None,
                        help="Path to SQLite database")

    args = parser.parse_args()
    agent = BacklinkAgent(db_path=args.db)

    if args.mark_submitted:
        agent.mark_submitted(args.mark_submitted)
        print(f"Marked '{args.mark_submitted}' as submitted")
    elif args.mark_live:
        agent.mark_live(args.mark_live[0], args.mark_live[1])
        print(f"Marked '{args.mark_live[0]}' as live at {args.mark_live[1]}")
    elif args.submit:
        agent.submit_next()
    elif args.check:
        agent.check_health()
    elif args.discover:
        agent.scan_reddit()
        agent.scan_hackernews()
        agent.show_opportunities()
    elif args.opportunities:
        agent.show_opportunities()
    elif args.report:
        agent.report()
    elif args.daemon:
        agent.run_daemon(interval_hours=args.interval)
    else:
        # Default: run full daily cycle
        agent.run_daily_cycle()


if __name__ == "__main__":
    main()
