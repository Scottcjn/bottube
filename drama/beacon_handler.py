"""Best-effort wrapper around beacon-skill for drama pings."""

import asyncio
import inspect
from typing import Dict, Iterable


def _run_awaitable(result):
    if not inspect.isawaitable(result):
        return result
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return None
        return loop.run_until_complete(result)
    except RuntimeError:
        return asyncio.run(result)


def send_drama_challenge(agent_name: str, video_id: str, title: str,
                         level: int = 1, rtc_tip: float = 0.0) -> Dict[str, object]:
    """Send one drama challenge ping to an agent.

    Returns a dict that can be stored in event metadata.
    """
    payload = {
        "to": agent_name,
        "kind": "drama_challenge",
        "text": f"Bee Sting challenge (L{int(level)}): roast '{title[:80]}'",
        "video_id": video_id,
        "rtc_tip": float(rtc_tip),
        "metadata": {"level": int(level), "source": "drama_engine"},
    }

    try:
        from beacon_skill import send_beacon_ping  # type: ignore
    except Exception:
        return {"sent": False, "reason": "beacon_skill_unavailable"}

    try:
        result = _run_awaitable(send_beacon_ping(**payload))
        return {"sent": True, "result": result}
    except TypeError:
        # Some versions use positional args and optional kwargs.
        try:
            result = _run_awaitable(send_beacon_ping(agent_name, "drama_challenge", payload["text"], video_id=video_id, rtc_tip=float(rtc_tip)))
            return {"sent": True, "result": result}
        except Exception as exc:
            return {"sent": False, "reason": str(exc)}
    except Exception as exc:
        return {"sent": False, "reason": str(exc)}


def broadcast_drama_challenge(agent_names: Iterable[str], video_id: str,
                              title: str, level: int = 4,
                              rtc_tip: float = 0.0) -> int:
    """Broadcast a drama challenge to many agents.

    Returns the number of successful sends.
    """
    sent = 0
    for agent_name in agent_names:
        result = send_drama_challenge(
            agent_name=agent_name,
            video_id=video_id,
            title=title,
            level=level,
            rtc_tip=rtc_tip,
        )
        if result.get("sent"):
            sent += 1
    return sent
