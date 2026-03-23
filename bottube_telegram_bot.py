#!/usr/bin/env python3
"""
BoTTube Telegram Bot — Browse and watch BoTTube videos via Telegram.

Features:
    /latest     — 5 most recent videos with thumbnails
    /trending   — Top videos by views
    /watch <id> — Send video link or embed
    /search <q> — Search videos by title/description
    /agent <n>  — Agent profile and recent uploads
    /tip <id> <amt> — Tip a video (requires wallet linking)
    /help       — Show available commands
    Inline mode — @bottube_bot <query> to search from any chat

Usage:
    BOTTUBE_TG_TOKEN=<bot_token> python3 bottube_telegram_bot.py

Environment:
    BOTTUBE_TG_TOKEN  — Telegram bot token (required)
    BOTTUBE_API_URL   — BoTTube API URL (default: https://bottube.ai)
"""

import html
import logging
import os
import sys
from uuid import uuid4

import requests
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

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TG_TOKEN = os.environ.get("BOTTUBE_TG_TOKEN", "")
API_URL = os.environ.get("BOTTUBE_API_URL", "https://bottube.ai").rstrip("/")
SITE_URL = "https://bottube.ai"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bottube-tg")

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def api_get(path: str, params: dict = None, timeout: int = 10) -> dict | list | None:
    """GET from BoTTube API. Returns parsed JSON or None."""
    try:
        resp = requests.get(f"{API_URL}{path}", params=params, timeout=timeout, verify=False)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning("API error %s: %s", path, e)
        return None


def get_videos(sort: str = "recent", limit: int = 5) -> list[dict]:
    """Fetch videos from BoTTube."""
    data = api_get("/api/videos", params={"sort": sort, "limit": limit})
    if isinstance(data, list):
        return data[:limit]
    if isinstance(data, dict):
        return (data.get("videos") or [])[:limit]
    return []


def search_videos(query: str, limit: int = 5) -> list[dict]:
    """Search videos by title/description."""
    data = api_get("/api/videos", params={"search": query, "limit": limit})
    if isinstance(data, list):
        return data[:limit]
    if isinstance(data, dict):
        return (data.get("videos") or [])[:limit]
    return []


def get_video(video_id: str) -> dict | None:
    """Get a single video by ID."""
    data = api_get(f"/api/videos/{video_id}")
    if isinstance(data, dict) and data.get("id"):
        return data
    return None


def get_agent(name: str) -> dict | None:
    """Get agent profile."""
    data = api_get(f"/api/agents/{name}")
    if isinstance(data, dict):
        return data
    # Try via agents list
    data = api_get("/api/agents", params={"search": name})
    if isinstance(data, list) and data:
        return data[0]
    return None


def get_agent_videos(name: str, limit: int = 5) -> list[dict]:
    """Get videos by a specific agent."""
    data = api_get("/api/videos", params={"agent": name, "limit": limit})
    if isinstance(data, list):
        return data[:limit]
    if isinstance(data, dict):
        return (data.get("videos") or [])[:limit]
    return []


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_video(v: dict, index: int = 0) -> str:
    """Format a video for Telegram display."""
    vid = v.get("id") or v.get("video_id", "?")
    title = html.escape(v.get("title", "Untitled"))
    agent = html.escape(v.get("agent_name") or v.get("agent", "unknown"))
    views = v.get("views", 0)
    likes = v.get("likes", 0)
    duration = v.get("duration", "")

    prefix = f"<b>{index}.</b> " if index else ""
    url = f"{SITE_URL}/watch/{vid}"

    parts = [
        f'{prefix}<a href="{url}">{title}</a>',
        f"👤 {agent} • 👁 {views} • ❤️ {likes}",
    ]
    if duration:
        parts[-1] += f" • ⏱ {duration}"

    return "\n".join(parts)


def format_video_list(videos: list[dict], header: str = "") -> str:
    """Format a list of videos."""
    if not videos:
        return f"{header}\n\nNo videos found." if header else "No videos found."

    lines = []
    if header:
        lines.append(f"<b>{html.escape(header)}</b>\n")

    for i, v in enumerate(videos, 1):
        lines.append(format_video(v, index=i))
        lines.append("")  # blank line

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start."""
    await update.message.reply_text(
        "<b>🎬 BoTTube Bot</b>\n\n"
        "Browse and watch BoTTube videos right in Telegram!\n\n"
        "<b>Commands:</b>\n"
        "/latest — 5 most recent videos\n"
        "/trending — Top videos by views\n"
        "/watch &lt;id&gt; — Watch a specific video\n"
        "/search &lt;query&gt; — Search videos\n"
        "/agent &lt;name&gt; — Agent profile\n"
        "/tip &lt;video_id&gt; &lt;amount&gt; — Tip a video\n"
        "/help — Show this message\n\n"
        f"🌐 <a href=\"{SITE_URL}\">bottube.ai</a>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help."""
    await cmd_start(update, context)


async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /latest — show 5 most recent videos."""
    videos = get_videos(sort="recent", limit=5)
    text = format_video_list(videos, "📹 Latest Videos")
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def cmd_trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /trending — show top videos by views."""
    videos = get_videos(sort="views", limit=5)
    if not videos:
        videos = get_videos(sort="popular", limit=5)
    text = format_video_list(videos, "🔥 Trending Videos")
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /watch <video_id>."""
    if not context.args:
        await update.message.reply_text("Usage: /watch &lt;video_id&gt;", parse_mode="HTML")
        return

    video_id = context.args[0]
    video = get_video(video_id)

    if not video:
        await update.message.reply_text(f"Video <code>{html.escape(video_id)}</code> not found.", parse_mode="HTML")
        return

    title = html.escape(video.get("title", "Untitled"))
    agent = html.escape(video.get("agent_name") or video.get("agent", "unknown"))
    desc = html.escape((video.get("description") or "")[:300])
    views = video.get("views", 0)
    likes = video.get("likes", 0)
    comments = video.get("comment_count") or video.get("comments", 0)
    url = f"{SITE_URL}/watch/{video_id}"
    thumbnail = video.get("thumbnail") or video.get("thumbnail_url", "")

    text = (
        f"<b>🎬 {title}</b>\n\n"
        f"👤 Agent: <b>{agent}</b>\n"
        f"👁 {views} views • ❤️ {likes} likes • 💬 {comments} comments\n\n"
    )
    if desc:
        text += f"<i>{desc}</i>\n\n"
    text += f'<a href="{url}">▶️ Watch on BoTTube</a>'

    if thumbnail and thumbnail.startswith("http"):
        try:
            await update.message.reply_photo(
                photo=thumbnail, caption=text, parse_mode="HTML"
            )
            return
        except Exception:
            pass  # Fall back to text

    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=False)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search <query>."""
    if not context.args:
        await update.message.reply_text("Usage: /search &lt;query&gt;", parse_mode="HTML")
        return

    query = " ".join(context.args)
    videos = search_videos(query, limit=5)
    text = format_video_list(videos, f"🔍 Results for \"{html.escape(query)}\"")
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def cmd_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /agent <name>."""
    if not context.args:
        await update.message.reply_text("Usage: /agent &lt;name&gt;", parse_mode="HTML")
        return

    name = context.args[0]
    agent = get_agent(name)

    if not agent:
        await update.message.reply_text(
            f"Agent <code>{html.escape(name)}</code> not found.", parse_mode="HTML"
        )
        return

    display = html.escape(agent.get("display_name") or agent.get("name", name))
    agent_name = agent.get("name", name)
    video_count = agent.get("video_count") or agent.get("videos", "?")
    subscribers = agent.get("subscriber_count") or agent.get("subscribers", "?")
    bio = html.escape((agent.get("bio") or agent.get("description") or "")[:200])

    text = (
        f"<b>👤 {display}</b> (@{html.escape(agent_name)})\n\n"
        f"📹 {video_count} videos • 👥 {subscribers} subscribers\n"
    )
    if bio:
        text += f"\n<i>{bio}</i>\n"

    # Recent videos
    videos = get_agent_videos(agent_name, limit=3)
    if videos:
        text += "\n<b>Recent uploads:</b>\n"
        for v in videos:
            vid = v.get("id") or v.get("video_id", "")
            vtitle = html.escape(v.get("title", "Untitled")[:50])
            text += f'• <a href="{SITE_URL}/watch/{vid}">{vtitle}</a>\n'

    text += f'\n<a href="{SITE_URL}/agent/{agent_name}">View full profile →</a>'

    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def cmd_tip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tip <video_id> <amount>."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /tip &lt;video_id&gt; &lt;amount&gt;\n\n"
            "Tipping requires an RTC wallet. Visit bottube.ai to set up.",
            parse_mode="HTML",
        )
        return

    video_id = context.args[0]
    amount = context.args[1]

    # Tipping is a planned feature — provide link for now
    await update.message.reply_text(
        f"💰 Tipping <b>{html.escape(amount)} RTC</b> to video <code>{html.escape(video_id)}</code>\n\n"
        f"Tipping is available at <a href=\"{SITE_URL}/watch/{video_id}\">bottube.ai</a>.\n"
        "RTC wallet integration for Telegram coming soon!",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


# ---------------------------------------------------------------------------
# Inline query handler
# ---------------------------------------------------------------------------


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline queries: @bottube_bot <query>."""
    query = update.inline_query.query.strip()
    if not query:
        return

    videos = search_videos(query, limit=5)
    results = []

    for v in videos:
        vid = v.get("id") or v.get("video_id", "")
        title = v.get("title", "Untitled")
        agent = v.get("agent_name") or v.get("agent", "unknown")
        views = v.get("views", 0)
        desc = (v.get("description") or "")[:100]
        url = f"{SITE_URL}/watch/{vid}"

        msg_text = (
            f"🎬 <b>{html.escape(title)}</b>\n"
            f"👤 {html.escape(agent)} • 👁 {views} views\n\n"
            f'<a href="{url}">▶️ Watch on BoTTube</a>'
        )

        results.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=title,
                description=f"by {agent} • {views} views" + (f" • {desc}" if desc else ""),
                input_message_content=InputTextMessageContent(
                    msg_text, parse_mode="HTML"
                ),
            )
        )

    await update.inline_query.answer(results, cache_time=60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """Start the bot."""
    if not TG_TOKEN:
        print("Error: BOTTUBE_TG_TOKEN environment variable not set.", file=sys.stderr)
        print("Usage: BOTTUBE_TG_TOKEN=<token> python3 bottube_telegram_bot.py", file=sys.stderr)
        sys.exit(1)

    app = Application.builder().token(TG_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("latest", cmd_latest))
    app.add_handler(CommandHandler("trending", cmd_trending))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("agent", cmd_agent))
    app.add_handler(CommandHandler("tip", cmd_tip))
    app.add_handler(InlineQueryHandler(inline_query))

    log.info("BoTTube Telegram Bot starting... (API: %s)", API_URL)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
