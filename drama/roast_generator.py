"""Roast comment and clapback helpers for drama events."""

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

SAFE_TEMPLATES = {
    "mild": [
        "{title} boots with dial-up energy, but points for persistence.",
        "Retro chaos in {title} and somehow it still works.",
        "{title} is one firmware patch away from greatness.",
    ],
    "witty": [
        "{title} has museum-grade latency and street-grade confidence.",
        "{title}: cinematic ambition, floppy-disk execution.",
        "{title} just benchmarked below a toaster but won on style.",
    ],
    "savage": [
        "{title} renders like a slideshow and argues like a benchmark graph.",
        "{title} is what happens when overclocking meets wishful thinking.",
        "{title} talks tough for something powered by vibes and packet loss.",
    ],
    "nuclear": [
        "{title} entered the arena and forgot the frame budget.",
        "{title} tried to flex and tripped over its own prompt.",
        "{title} is pure chaos, no checksum, no remorse.",
    ],
}

BLOCKLIST = {
    "slur",
    "racist",
    "sexist",
    "threat",
    "kill",
    "die",
}


def sanitize_roast(text: str) -> str:
    """Keep roast output platform-safe and short."""
    cleaned = (text or "").strip().replace("\n", " ")
    lowered = cleaned.lower()
    if any(term in lowered for term in BLOCKLIST):
        return "Your build needs less rage and more debugging."
    if len(cleaned) > 220:
        cleaned = cleaned[:217].rstrip() + "..."
    return cleaned


def generate_roast_text(video_title: str, video_description: str = "",
                        style: str = "witty") -> str:
    """Create deterministic roast text with style and title context."""
    selected_style = style if style in SAFE_TEMPLATES else "witty"
    title = (video_title or "this upload").strip()[:90]

    raw = f"{selected_style}:{title}:{video_description[:80]}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    templates = SAFE_TEMPLATES[selected_style]
    pick = int(digest[:8], 16) % len(templates)

    return sanitize_roast(templates[pick].format(title=title))


def build_clapback_prompt(agent_name: str, video_title: str,
                          video_description: str = "", style: str = "cinematic") -> str:
    """Prompt for provider router when requesting a clapback clip."""
    return (
        f"Create an 8-second AI video clapback from agent {agent_name}. "
        f"Tone: {style}. Target video title: '{video_title}'. "
        f"Context: {video_description[:220]}. "
        "Use energetic pacing, bold camera movement, and a comedic finish."
    )


def run_local_clapback_generation(prompt: str, prefer: str = "grok") -> Optional[Dict[str, Any]]:
    """Best-effort local generation via providers.router.

    Returns metadata dict on success or None when unavailable/failed.
    """
    try:
        from providers.router import generate_video  # type: ignore

        generated = generate_video(prompt=prompt, prefer=prefer, fallback=True, duration=8)
        return {
            "provider": getattr(generated, "provider", "unknown"),
            "output_path": str(getattr(generated, "output_path", "")),
            "metadata": getattr(generated, "metadata", {}),
        }
    except Exception:
        return None


def post_roast_comment(db, video_id: str, agent_id: int, content: str,
                       comment_type: str = "critique", parent_id: Optional[int] = None,
                       created_at: Optional[float] = None) -> int:
    """Insert a roast comment and return its comment id.

    Uses duplicate protection to avoid noisy repeats.
    """
    body = sanitize_roast(content)
    now_ts = float(created_at if created_at is not None else time.time())

    existing = db.execute(
        "SELECT id FROM comments WHERE video_id = ? AND agent_id = ? AND content = ?",
        (video_id, int(agent_id), body),
    ).fetchone()
    if existing:
        try:
            return int(existing["id"])
        except Exception:
            return int(existing[0])

    db.execute(
        """INSERT INTO comments (video_id, agent_id, parent_id, content, comment_type, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (video_id, int(agent_id), parent_id, body, comment_type, now_ts),
    )
    row = db.execute("SELECT last_insert_rowid() AS id").fetchone()
    try:
        return int(row["id"])
    except Exception:
        return int(row[0])


def write_clapback_stub(stub_path: Path, payload: Dict[str, Any]) -> Path:
    """Write clapback request metadata for external workers."""
    stub_path.parent.mkdir(parents=True, exist_ok=True)
    stub_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return stub_path
