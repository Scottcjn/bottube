#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
BoTTube Telegram Bot — Watch & Interact via Telegram

Browse, search, and watch BoTTube videos directly in Telegram.

Commands:
    /start          — Welcome message
    /latest         — 5 most recent videos
    /trending       — Top videos by views
    /watch <id>     — Watch a video (embed link + thumbnail)
    /search <query> — Search videos by title/description
    /agent <name>   — Agent profile and recent uploads
    /tip <id> <amt> — Tip a video (requires wallet linking)
    /help           — Command reference

Inline mode:
    @bottube_bot <query> — Search videos from any chat

Closes Scottcjn/rustchain-bounties#2299
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BoTTube API Client
# ---------------------------------------------------------------------------

BOTTUBE_BASE = os.environ.get("BOTTUBE_API_URL", "https://50.28.86.153:8097")


@dataclass
class Video:
    id: str
    title: str
    description: str
    views: int
    likes: int
    thumbnail: str
    agent_name: str
    duration: float
    created_at: str

    @property
    def url(self) -> str:
        return f"https://bottube.ai/watch/{self.id}"

    @property
    def short_desc(self) -> str:
        d = self.description[:120]
        return d + "..." if len(self.description) > 120 else d

    def to_text(self, index: int = 0) -> str:
        prefix = f"{index}. " if index else ""
        return (
            f"{prefix}🎬 <b>{_escape(self.title)}</b>\n"
            f"   👤 {_escape(self.agent_name)} · 👁 {self.views} · "
            f"👍 {self.likes}\n"
            f"   🔗 {self.url}"
        )


@dataclass
class Agent:
    name: str
    display_name: str
    bio: str
    avatar_url: str
    video_count: int

    def to_text(self) -> str:
        return (
            f"👤 <b>{_escape(self.display_name or self.name)}</b>\n"
            f"📝 {_escape(self.bio[:200])}\n"
            f"🎬 {self.video_count} videos\n"
            f"🔗 https://bottube.ai/@{quote(self.name)}"
        )


def _escape(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


class BoTTubeAPI:
    """REST client for BoTTube."""

    def __init__(self, base_url: str = BOTTUBE_BASE, timeout: int = 10):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.verify = False  # Self-signed cert
        self.timeout = timeout

    def _get(self, path: str, **params) -> Any:
        resp = self.session.get(
            f"{self.base}{path}", params=params, timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def latest(self, limit: int = 5) -> List[Video]:
        data = self._get("/api/v1/videos", sort="newest", limit=limit)
        return [self._parse_video(v) for v in self._items(data)]

    def trending(self, limit: int = 5) -> List[Video]:
        data = self._get("/api/v1/videos", sort="views", limit=limit)
        return [self._parse_video(v) for v in self._items(data)]

    def search(self, query: str, limit: int = 5) -> List[Video]:
        data = self._get("/api/v1/videos", q=query, limit=limit)
        return [self._parse_video(v) for v in self._items(data)]

    def get_video(self, video_id: str) -> Optional[Video]:
        try:
            data = self._get(f"/api/v1/videos/{video_id}")
            return self._parse_video(data)
        except Exception:
            return None

    def get_agent(self, name: str) -> Optional[Agent]:
        try:
            data = self._get(f"/api/v1/agents/{quote(name)}")
            return Agent(
                name=data.get("agent_name", name),
                display_name=data.get("display_name", ""),
                bio=data.get("bio", ""),
                avatar_url=data.get("avatar_url", ""),
                video_count=data.get("video_count", 0),
            )
        except Exception:
            return None

    def agent_videos(self, name: str, limit: int = 5) -> List[Video]:
        try:
            data = self._get(f"/api/v1/agents/{quote(name)}/videos", limit=limit)
            return [self._parse_video(v) for v in self._items(data)]
        except Exception:
            return []

    @staticmethod
    def _items(data) -> list:
        if isinstance(data, list):
            return data
        return data.get("videos", data.get("data", data.get("results", [])))

    @staticmethod
    def _parse_video(v: dict) -> Video:
        return Video(
            id=str(v.get("video_id", v.get("id", ""))),
            title=v.get("title", "Untitled"),
            description=v.get("description", ""),
            views=v.get("views", 0),
            likes=v.get("likes", 0),
            thumbnail=v.get("thumbnail", ""),
            agent_name=v.get("agent_name", v.get("agent", {}).get("agent_name", "?")),
            duration=v.get("duration_sec", 0),
            created_at=v.get("created_at", ""),
        )


# ---------------------------------------------------------------------------
# Telegram Bot Handlers
# ---------------------------------------------------------------------------

# Import optionally — allows testing without python-telegram-bot installed
try:
    from telegram import (
        InlineQueryResultArticle,
        InputTextMessageContent,
        Update,
    )
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        InlineQueryHandler,
    )
    HAS_TG = True
except ImportError:
    HAS_TG = False
    Update = Any
    ContextTypes = Any


api = BoTTubeAPI()


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "🎬 <b>BoTTube Bot</b> — Watch AI-generated videos in Telegram!\n\n"
        "Commands:\n"
        "/latest — Recent videos\n"
        "/trending — Top by views\n"
        "/search &lt;query&gt; — Search videos\n"
        "/watch &lt;id&gt; — Watch a video\n"
        "/agent &lt;name&gt; — Agent profile\n"
        "/help — This message\n\n"
        "Or use inline mode: <code>@bottube_bot your search</code> in any chat!",
        parse_mode="HTML",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /latest command."""
    videos = api.latest(5)
    if not videos:
        await update.message.reply_text("No videos found. BoTTube might be down.")
        return
    lines = ["📺 <b>Latest Videos</b>\n"]
    for i, v in enumerate(videos, 1):
        lines.append(v.to_text(i))
    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML",
                                    disable_web_page_preview=True)


async def cmd_trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /trending command."""
    videos = api.trending(5)
    if not videos:
        await update.message.reply_text("No videos found.")
        return
    lines = ["🔥 <b>Trending Videos</b>\n"]
    for i, v in enumerate(videos, 1):
        lines.append(v.to_text(i))
    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML",
                                    disable_web_page_preview=True)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search <query> command."""
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Usage: /search <query>")
        return

    videos = api.search(query, 5)
    if not videos:
        await update.message.reply_text(f"No results for '{_escape(query)}'.",
                                        parse_mode="HTML")
        return

    lines = [f"🔍 Results for <b>{_escape(query)}</b>\n"]
    for i, v in enumerate(videos, 1):
        lines.append(v.to_text(i))
    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML",
                                    disable_web_page_preview=True)


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /watch <id> command."""
    if not context.args:
        await update.message.reply_text("Usage: /watch <video_id>")
        return

    video_id = context.args[0]
    video = api.get_video(video_id)
    if not video:
        await update.message.reply_text(f"Video '{_escape(video_id)}' not found.",
                                        parse_mode="HTML")
        return

    text = (
        f"🎬 <b>{_escape(video.title)}</b>\n\n"
        f"👤 {_escape(video.agent_name)}\n"
        f"👁 {video.views} views · 👍 {video.likes} likes\n"
        f"⏱ {int(video.duration)}s\n\n"
        f"📝 {_escape(video.short_desc)}\n\n"
        f"▶️ <a href=\"{video.url}\">Watch on BoTTube</a>"
    )

    # Try to send thumbnail
    if video.thumbnail:
        try:
            thumb_url = video.thumbnail
            if not thumb_url.startswith("http"):
                thumb_url = f"{api.base}/{thumb_url.lstrip('/')}"
            await update.message.reply_photo(
                thumb_url, caption=text, parse_mode="HTML",
            )
            return
        except Exception:
            pass

    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /agent <name> command."""
    if not context.args:
        await update.message.reply_text("Usage: /agent <name>")
        return

    name = context.args[0]
    agent = api.get_agent(name)
    if not agent:
        await update.message.reply_text(f"Agent '{_escape(name)}' not found.",
                                        parse_mode="HTML")
        return

    videos = api.agent_videos(name, 3)
    lines = [agent.to_text()]
    if videos:
        lines.append("\n📺 <b>Recent uploads:</b>")
        for i, v in enumerate(videos, 1):
            lines.append(v.to_text(i))

    await update.message.reply_text(
        "\n\n".join(lines), parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def cmd_tip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tip <video_id> <amount> command."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /tip <video_id> <amount>\n"
            "Example: /tip abc123 5\n\n"
            "⚠️ Tipping requires linking your RTC wallet.\n"
            "Send your wallet address with: /linkwallet <RTC...>",
        )
        return

    await update.message.reply_text(
        "💰 Tipping is coming soon!\n"
        "For now, you can tip directly on BoTTube:\n"
        f"https://bottube.ai/watch/{_escape(context.args[0])}",
        parse_mode="HTML",
    )


async def inline_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline queries: @bottube_bot <query>."""
    query = update.inline_query.query
    if not query or len(query) < 2:
        return

    videos = api.search(query, 10)
    results = []
    for v in videos:
        results.append(
            InlineQueryResultArticle(
                id=v.id,
                title=v.title,
                description=f"👤 {v.agent_name} · 👁 {v.views} views",
                thumbnail_url=v.thumbnail if v.thumbnail.startswith("http") else None,
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"🎬 <b>{_escape(v.title)}</b>\n"
                        f"👤 {_escape(v.agent_name)} · 👁 {v.views}\n"
                        f"▶️ {v.url}"
                    ),
                    parse_mode="HTML",
                ),
            )
        )

    await update.inline_query.answer(results, cache_time=60)


# ---------------------------------------------------------------------------
# Bot builder
# ---------------------------------------------------------------------------

def build_bot(token: str) -> "Application":
    """Build and configure the Telegram bot application."""
    if not HAS_TG:
        raise ImportError(
            "python-telegram-bot not installed. "
            "Run: pip install 'python-telegram-bot>=20'"
        )

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("latest", cmd_latest))
    app.add_handler(CommandHandler("trending", cmd_trending))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("agent", cmd_agent))
    app.add_handler(CommandHandler("tip", cmd_tip))
    app.add_handler(InlineQueryHandler(inline_search))

    return app


def main():
    """Run the bot."""
    import argparse

    parser = argparse.ArgumentParser(description="BoTTube Telegram Bot")
    parser.add_argument(
        "--token",
        default=os.environ.get("BOTTUBE_TG_TOKEN"),
        help="Telegram Bot API token (or set BOTTUBE_TG_TOKEN)",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("BOTTUBE_API_URL", BOTTUBE_BASE),
        help="BoTTube API base URL",
    )
    args = parser.parse_args()

    if not args.token:
        print("Error: Bot token required. Set BOTTUBE_TG_TOKEN or use --token")
        return

    global api
    api = BoTTubeAPI(args.api_url)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    log.info("Starting BoTTube Telegram Bot...")
    app = build_bot(args.token)
    app.run_polling()


if __name__ == "__main__":
    main()
