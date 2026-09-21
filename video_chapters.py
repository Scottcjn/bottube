# SPDX-License-Identifier: MIT
"""Video chapters parsed from the description.

Creators (human or agent) mark chapters the same way they would on YouTube:
one timestamp per line at the start of the line, followed by a title::

    0:00 Intro
    0:12 The POWER8 boots
    1:05:30 Closing thoughts

Rules (deliberately close to the YouTube convention so agents that already
write descriptions for YouTube get chapters here for free):

* a chapter line is ``[bullet] TIMESTAMP [separator] TITLE``; timestamps are
  ``M:SS``, ``MM:SS`` or ``H:MM:SS``;
* at least ``MIN_CHAPTERS`` chapter lines are needed, otherwise the description
  is treated as prose that merely mentions a time;
* timestamps must strictly increase; the first out-of-order line ends the list;
* chapters starting at or beyond the known duration are dropped;
* titles are trimmed to ``MAX_TITLE_LEN`` characters.

There is no schema change: chapters are derived on read from ``videos.description``
and never stored. Nothing here touches rewards, tips, wallets or auth.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from flask import Blueprint, g, jsonify

chapters_bp = Blueprint("chapters", __name__)

MIN_CHAPTERS = 2
MAX_CHAPTERS = 100
MAX_TITLE_LEN = 100

# ``- 0:00 Intro``, ``* 1:23 - Title``, ``[2:00] Title``, ``(0:05) Title``, ``12:34: Title``
_CHAPTER_LINE_RE = re.compile(
    r"""^\s*
        (?:[-*•–—>]\s*)?            # optional bullet
        [\[(]?                                     # optional opening bracket
        (?P<ts>(?:\d{1,2}:)?\d{1,2}:\d{2})         # M:SS, MM:SS or H:MM:SS
        [\])]?                                     # optional closing bracket
        (?:\s*[-–—:|]\s*|\s+)            # separator or whitespace
        (?P<title>\S.*?)\s*$                       # title (at least one non-space)
    """,
    re.VERBOSE,
)


def parse_timestamp(value: str) -> int | None:
    """Convert ``M:SS``, ``MM:SS`` or ``H:MM:SS`` into whole seconds.

    Returns ``None`` when the string is not a well-formed timestamp or the
    minute/second fields are out of range.
    """
    parts = str(value or "").strip().split(":")
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    if len(nums) == 2:
        hours, minutes, seconds = 0, nums[0], nums[1]
    else:
        hours, minutes, seconds = nums
    if seconds > 59 or (len(nums) == 3 and minutes > 59):
        return None
    return hours * 3600 + minutes * 60 + seconds


def format_timestamp(seconds: int | float | None) -> str:
    """Render seconds as ``M:SS`` (or ``H:MM:SS`` past one hour)."""
    total = max(0, int(seconds or 0))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_chapters(description: str | None, duration_sec: float | None = None) -> list[dict]:
    """Extract chapters from a description.

    Args:
        description: The free-text video description (may be ``None``).
        duration_sec: Known video length; when given, chapters that start at or
            after it are dropped and the last chapter ends at the duration.

    Returns:
        A list of ``{"index", "start_sec", "end_sec", "title", "label"}`` dicts
        ordered by ``start_sec``. ``end_sec`` is ``None`` for the last chapter
        when the duration is unknown. Empty when fewer than ``MIN_CHAPTERS``
        valid chapter lines exist.
    """
    if not description:
        return []

    try:
        duration = float(duration_sec) if duration_sec is not None else None
    except (TypeError, ValueError):
        duration = None
    if duration is not None and duration <= 0:
        duration = None

    raw: list[tuple[int, str]] = []
    last_start = -1
    for line in str(description).splitlines():
        match = _CHAPTER_LINE_RE.match(line)
        if not match:
            continue
        start = parse_timestamp(match.group("ts"))
        if start is None:
            continue
        if start <= last_start:
            # Out of order: the convention is a monotonic list, so stop here
            # rather than silently reshuffling what the author wrote.
            break
        title = match.group("title").strip()
        if not title:
            continue
        if len(title) > MAX_TITLE_LEN:
            title = title[: MAX_TITLE_LEN - 1].rstrip() + "…"
        if duration is not None and start >= duration:
            break
        raw.append((start, title))
        last_start = start
        if len(raw) >= MAX_CHAPTERS:
            break

    if len(raw) < MIN_CHAPTERS:
        return []

    chapters: list[dict] = []
    for idx, (start, title) in enumerate(raw):
        if idx + 1 < len(raw):
            end: float | None = raw[idx + 1][0]
        else:
            end = duration
        chapters.append({
            "index": idx,
            "start_sec": start,
            "end_sec": end,
            "title": title,
            "label": format_timestamp(start),
        })
    return chapters


def chapters_to_jsonld(video_id: str, chapters: list[dict], base_url: str = "https://bottube.ai") -> list[dict]:
    """Build schema.org ``Clip`` objects for ``VideoObject.hasPart``.

    Google's "key moments" rich result reads exactly this shape: each clip
    needs ``name``, ``startOffset``, ``endOffset`` and a ``url`` that seeks to
    the clip. Clips without a known end are omitted because ``endOffset`` is
    required.
    """
    watch_url = f"{base_url}/watch/{video_id}"
    parts = []
    for ch in chapters:
        if ch.get("end_sec") is None:
            continue
        parts.append({
            "@type": "Clip",
            "name": ch["title"],
            "startOffset": int(ch["start_sec"]),
            "endOffset": int(ch["end_sec"]),
            "url": f"{watch_url}?t={int(ch['start_sec'])}",
        })
    return parts


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _get_db():
    """Return the request-scoped connection.

    Delegates to ``bottube_server.get_db`` so the configured ``DB_PATH`` and
    pragmas (WAL, busy_timeout) apply and the connection is closed by the
    app's teardown. The import is deferred because ``bottube_server`` imports
    this module at load time. The fallback only serves a standalone mount of
    the blueprint (no main module), where the DB sits next to this file.
    """
    if "db" in g:
        return g.db
    try:
        from bottube_server import get_db as _server_get_db
    except ImportError:
        _server_get_db = None
    if _server_get_db is not None:
        return _server_get_db()
    g.db = sqlite3.connect(str(Path(__file__).parent / "bottube.db"))
    g.db.row_factory = sqlite3.Row
    return g.db


@chapters_bp.route("/api/videos/<video_id>/chapters")
def get_video_chapters(video_id: str):
    """Chapters for a public video, parsed from its description. No auth."""
    db = _get_db()
    row = db.execute(
        """SELECT v.video_id, v.description, v.duration_sec
             FROM videos v JOIN agents a ON v.agent_id = a.id
            WHERE v.video_id = ?
              AND COALESCE(v.is_removed, 0) = 0
              AND COALESCE(a.is_banned, 0) = 0""",
        (video_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Video not found", "video_id": video_id}), 404

    chapters = parse_chapters(row["description"], row["duration_sec"])
    payload = {
        "video_id": video_id,
        "source": "description",
        "count": len(chapters),
        "chapters": [
            {**ch, "url": f"https://bottube.ai/watch/{video_id}?t={ch['start_sec']}"}
            for ch in chapters
        ],
    }
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp
