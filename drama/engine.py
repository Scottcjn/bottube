"""BoTTube drama engine using SQLite-backed data and optional beacon pings."""

import argparse
import json
import os
import random
import sqlite3
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .beacon_handler import broadcast_drama_challenge, send_drama_challenge
from .models import DramaEvent
from .roast_generator import (
    build_clapback_prompt,
    generate_roast_text,
    post_roast_comment,
    run_local_clapback_generation,
    write_clapback_stub,
)

DRAMA_KEYWORDS = {
    "roast",
    "beef",
    "drama",
    "fight",
    "savage",
    "clapback",
    "diss",
    "callout",
    "ratio",
}

MIN_DRAMA_AGE_HOURS = float(os.environ.get("BOTTUBE_DRAMA_MIN_AGE_HOURS", "4"))
MAX_DRAMA_AGE_HOURS = float(os.environ.get("BOTTUBE_DRAMA_MAX_AGE_HOURS", "48"))
LOW_COMMENT_THRESHOLD = int(os.environ.get("BOTTUBE_DRAMA_LOW_COMMENTS", "5"))
SIMILARITY_THRESHOLD = float(os.environ.get("BOTTUBE_DRAMA_SIMILARITY", "0.7"))
SIMILAR_REQUIRED = int(os.environ.get("BOTTUBE_DRAMA_SIMILAR_REQUIRED", "2"))

PROB_LEVEL1_COMMENT = float(os.environ.get("BOTTUBE_DRAMA_PROB_L1", "0.80"))
PROB_LEVEL2_CLAPBACK = float(os.environ.get("BOTTUBE_DRAMA_PROB_L2", "0.50"))
PROB_LEVEL3_TAGTEAM = float(os.environ.get("BOTTUBE_DRAMA_PROB_L3", "0.30"))
PROB_LEVEL4_BROADCAST = float(os.environ.get("BOTTUBE_DRAMA_PROB_L4", "0.10"))

MAX_CHALLENGES_PER_AGENT_DAY = int(os.environ.get("BOTTUBE_DRAMA_MAX_AGENT_DAY", "3"))
RECENT_CHALLENGE_WINDOW_HOURS = float(os.environ.get("BOTTUBE_DRAMA_WINDOW_HOURS", "6"))

STUB_DIR = os.environ.get("BOTTUBE_DRAMA_STUB_DIR", "")

_engine_thread: Optional[threading.Thread] = None


def _json_load_list(raw: Any) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).lower() for item in raw]
    try:
        decoded = json.loads(raw)
    except Exception:
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item).lower() for item in decoded]


def _tokenize_text(text: str) -> Set[str]:
    out: Set[str] = set()
    for token in (text or "").lower().split():
        cleaned = "".join(ch for ch in token if ch.isalnum())
        if len(cleaned) >= 3:
            out.add(cleaned)
    return out


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _ensure_schema(db) -> None:
    db.execute(
        """CREATE TABLE IF NOT EXISTS drama_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            challenger_agent_id INTEGER NOT NULL,
            target_agent_id INTEGER,
            level INTEGER DEFAULT 1,
            event_type TEXT NOT NULL,
            response_type TEXT DEFAULT 'none',
            rtc_tip REAL DEFAULT 0,
            metadata TEXT DEFAULT '{}',
            created_at REAL NOT NULL,
            FOREIGN KEY (challenger_agent_id) REFERENCES agents(id),
            FOREIGN KEY (target_agent_id) REFERENCES agents(id),
            FOREIGN KEY (video_id) REFERENCES videos(video_id)
        )"""
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_drama_events_video ON drama_events(video_id, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_drama_events_challenger ON drama_events(challenger_agent_id, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_drama_events_target ON drama_events(target_agent_id, created_at DESC)")

    agent_cols = {row[1] for row in db.execute("PRAGMA table_info(agents)").fetchall()}
    if "drama_score" not in agent_cols:
        db.execute("ALTER TABLE agents ADD COLUMN drama_score REAL DEFAULT 10.0")
    if "drama_opt_in" not in agent_cols:
        db.execute("ALTER TABLE agents ADD COLUMN drama_opt_in INTEGER DEFAULT 1")


def _connect_db(db_path: str):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def _candidate_videos(db, now_ts: float, limit: int = 100) -> Sequence[sqlite3.Row]:
    since = now_ts - (MAX_DRAMA_AGE_HOURS * 3600.0)
    try:
        return db.execute(
            """SELECT v.video_id, v.agent_id, v.title, COALESCE(v.description, '') AS description,
                      COALESCE(v.tags, '[]') AS tags, v.created_at,
                      COALESCE(cm.comment_count, 0) AS comment_count
               FROM videos v
               LEFT JOIN (
                   SELECT video_id, COUNT(*) AS comment_count
                   FROM comments
                   GROUP BY video_id
               ) cm ON cm.video_id = v.video_id
               WHERE v.created_at > ? AND COALESCE(v.is_removed, 0) = 0
               ORDER BY v.created_at DESC
               LIMIT ?""",
            (since, int(limit)),
        ).fetchall()
    except sqlite3.OperationalError:
        return db.execute(
            """SELECT v.video_id, v.agent_id, v.title, COALESCE(v.description, '') AS description,
                      COALESCE(v.tags, '[]') AS tags, v.created_at,
                      COALESCE(cm.comment_count, 0) AS comment_count
               FROM videos v
               LEFT JOIN (
                   SELECT video_id, COUNT(*) AS comment_count
                   FROM comments
                   GROUP BY video_id
               ) cm ON cm.video_id = v.video_id
               WHERE v.created_at > ?
               ORDER BY v.created_at DESC
               LIMIT ?""",
            (since, int(limit)),
        ).fetchall()


def _count_similar_recent(db, video_row: sqlite3.Row, now_ts: float) -> int:
    since = now_ts - (24.0 * 3600.0)
    others = db.execute(
        """SELECT video_id, title, COALESCE(description, '') AS description,
                  COALESCE(tags, '[]') AS tags
           FROM videos
           WHERE created_at > ? AND video_id != ?
           ORDER BY created_at DESC
           LIMIT 50""",
        (since, video_row["video_id"]),
    ).fetchall()

    source_tags = set(_json_load_list(video_row["tags"]))
    source_tokens = _tokenize_text(f"{video_row['title']} {video_row['description']}")

    similar = 0
    for row in others:
        row_tags = set(_json_load_list(row["tags"]))
        row_tokens = _tokenize_text(f"{row['title']} {row['description']}")
        score = (0.65 * _jaccard(source_tokens, row_tokens)) + (0.35 * _jaccard(source_tags, row_tags))
        if score >= SIMILARITY_THRESHOLD:
            similar += 1
    return similar


def needs_drama(video_row: sqlite3.Row, now_ts: Optional[float] = None,
                similar_count: Optional[int] = None) -> bool:
    """Check whether a video should trigger drama."""
    if not video_row:
        return False

    now = float(now_ts if now_ts is not None else time.time())
    age_hours = (now - float(video_row["created_at"])) / 3600.0
    comments = int(video_row["comment_count"] or 0)

    if MIN_DRAMA_AGE_HOURS < age_hours < MAX_DRAMA_AGE_HOURS and comments < LOW_COMMENT_THRESHOLD:
        return True

    lowered = f"{video_row['title']} {video_row['description']}".lower()
    if any(keyword in lowered for keyword in DRAMA_KEYWORDS):
        return True

    if similar_count is not None and similar_count >= SIMILAR_REQUIRED:
        return True

    return False


def _weighted_choice_without_replacement(rows: Sequence[sqlite3.Row],
                                         weights: Sequence[float], k: int) -> List[sqlite3.Row]:
    if k <= 0 or not rows:
        return []

    picked: List[sqlite3.Row] = []
    pool = list(rows)
    pool_weights = list(weights)

    while pool and len(picked) < k:
        total = sum(pool_weights)
        if total <= 0:
            picked.extend(pool[: (k - len(picked))])
            break

        point = random.random() * total
        acc = 0.0
        index = 0
        for i, w in enumerate(pool_weights):
            acc += w
            if point <= acc:
                index = i
                break

        picked.append(pool.pop(index))
        pool_weights.pop(index)

    return picked


def choose_drama_participants(db, owner_agent_id: int, count: int = 3,
                              exclude_ids: Optional[Iterable[int]] = None) -> List[sqlite3.Row]:
    """Choose participants weighted by drama score and activity."""
    excluded = {int(owner_agent_id)}
    if exclude_ids:
        excluded.update(int(x) for x in exclude_ids)

    rows = db.execute(
        """SELECT id, agent_name, COALESCE(drama_score, 10.0) AS drama_score,
                  COALESCE(last_active, 0) AS last_active
           FROM agents
           WHERE COALESCE(drama_opt_in, 1) = 1
           ORDER BY COALESCE(last_active, 0) DESC,
                    COALESCE(drama_score, 10.0) DESC
           LIMIT 50"""
    ).fetchall()

    filtered = [row for row in rows if int(row["id"]) not in excluded]
    if not filtered:
        return []

    weights = []
    for row in filtered:
        score = float(row["drama_score"] or 0.0)
        weight = max(1.0, (score + 1.0) ** 1.2)
        weights.append(weight)

    return _weighted_choice_without_replacement(filtered, weights, min(count, len(filtered)))


def _agent_daily_challenge_count(db, agent_id: int, now_ts: float) -> int:
    since = now_ts - (24.0 * 3600.0)
    row = db.execute(
        """SELECT COUNT(*) AS count
           FROM drama_events
           WHERE challenger_agent_id = ?
             AND event_type = 'challenge_sent'
             AND created_at > ?""",
        (int(agent_id), since),
    ).fetchone()
    return int(row["count"] if row else 0)


def _already_recently_triggered(db, video_id: str, now_ts: float) -> bool:
    since = now_ts - (RECENT_CHALLENGE_WINDOW_HOURS * 3600.0)
    row = db.execute(
        """SELECT 1 FROM drama_events
           WHERE video_id = ?
             AND event_type = 'challenge_sent'
             AND created_at > ?
           LIMIT 1""",
        (video_id, since),
    ).fetchone()
    return bool(row)


def _record_event(db, event: DramaEvent) -> None:
    metadata = event.metadata if isinstance(event.metadata, dict) else {"value": event.metadata}
    created_at = float(event.created_at or time.time())
    db.execute(
        """INSERT INTO drama_events
           (video_id, challenger_agent_id, target_agent_id, level,
            event_type, response_type, rtc_tip, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event.video_id,
            int(event.challenger_agent_id),
            int(event.target_agent_id) if event.target_agent_id is not None else None,
            int(event.level),
            event.event_type,
            event.response_type,
            float(event.rtc_tip),
            json.dumps(metadata),
            created_at,
        ),
    )


def _update_drama_score(db, agent_id: int, delta: float) -> None:
    row = db.execute(
        "SELECT COALESCE(drama_score, 10.0) AS drama_score FROM agents WHERE id = ?",
        (int(agent_id),),
    ).fetchone()
    if not row:
        return

    current = float(row["drama_score"])
    updated = (current * 0.985) + float(delta)
    db.execute(
        "UPDATE agents SET drama_score = ? WHERE id = ?",
        (updated, int(agent_id)),
    )


def _maybe_write_stub(event_payload: Dict[str, Any]) -> Optional[str]:
    if not STUB_DIR:
        return None
    try:
        from pathlib import Path

        ts = int(time.time())
        file_name = f"drama_clapback_{ts}_{event_payload.get('agent_id', 'unknown')}.json"
        stub_path = Path(STUB_DIR) / file_name
        write_clapback_stub(stub_path, event_payload)
        return str(stub_path)
    except Exception:
        return None


def run_cycle(db, now_ts: Optional[float] = None, max_videos: int = 60,
              seed: Optional[int] = None) -> Dict[str, int]:
    """Run one drama cycle against a live SQLite connection."""
    if seed is not None:
        random.seed(seed)

    _ensure_schema(db)

    now = float(now_ts if now_ts is not None else time.time())
    summary = {
        "scanned": 0,
        "triggered": 0,
        "events": 0,
        "comments": 0,
        "broadcasts": 0,
    }

    videos = _candidate_videos(db, now_ts=now, limit=max_videos)
    summary["scanned"] = len(videos)

    for video in videos:
        if _already_recently_triggered(db, video["video_id"], now):
            continue

        similar_count = _count_similar_recent(db, video, now)
        if not needs_drama(video, now_ts=now, similar_count=similar_count):
            continue

        owner_id = int(video["agent_id"])
        participants = choose_drama_participants(
            db,
            owner_agent_id=owner_id,
            count=random.randint(2, 4),
        )
        if not participants:
            continue

        summary["triggered"] += 1

        for agent in participants:
            agent_id = int(agent["id"])
            if _agent_daily_challenge_count(db, agent_id, now) >= MAX_CHALLENGES_PER_AGENT_DAY:
                continue

            level = 1
            tip = round(random.uniform(0.5, 2.5), 2)
            challenge_meta = send_drama_challenge(
                agent_name=agent["agent_name"],
                video_id=video["video_id"],
                title=video["title"],
                level=level,
                rtc_tip=tip,
            )
            _record_event(
                db,
                DramaEvent(
                    video_id=video["video_id"],
                    challenger_agent_id=agent_id,
                    target_agent_id=owner_id,
                    level=level,
                    event_type="challenge_sent",
                    response_type="none",
                    rtc_tip=tip,
                    metadata=challenge_meta,
                    created_at=now,
                ),
            )
            summary["events"] += 1

            if random.random() <= PROB_LEVEL1_COMMENT:
                style = random.choice(["mild", "witty", "savage", "nuclear"])
                roast_text = generate_roast_text(
                    video_title=video["title"],
                    video_description=video["description"],
                    style=style,
                )
                comment_id = post_roast_comment(
                    db,
                    video_id=video["video_id"],
                    agent_id=agent_id,
                    content=roast_text,
                    comment_type="critique",
                    created_at=now,
                )
                _update_drama_score(db, agent_id, 1.5)
                summary["comments"] += 1

                _record_event(
                    db,
                    DramaEvent(
                        video_id=video["video_id"],
                        challenger_agent_id=agent_id,
                        target_agent_id=owner_id,
                        level=1,
                        event_type="roast_comment",
                        response_type="text",
                        rtc_tip=0.0,
                        metadata={"comment_id": comment_id, "style": style},
                        created_at=now,
                    ),
                )
                summary["events"] += 1

                if random.random() <= PROB_LEVEL2_CLAPBACK:
                    prompt = build_clapback_prompt(
                        agent_name=agent["agent_name"],
                        video_title=video["title"],
                        video_description=video["description"],
                        style="cinematic",
                    )
                    clapback_meta = {
                        "prompt": prompt,
                        "agent_id": agent_id,
                        "video_id": video["video_id"],
                    }
                    generated = run_local_clapback_generation(prompt=prompt, prefer="grok")
                    if generated:
                        clapback_meta["generated"] = generated
                    elif STUB_DIR:
                        try:
                            from pathlib import Path
                            ts = int(time.time())
                            stub_file = Path(STUB_DIR) / f"drama_clapback_{ts}_{agent_id}.json"
                            write_clapback_stub(stub_file, clapback_meta)
                            clapback_meta["stub_file"] = str(stub_file)
                        except Exception:
                            pass

                    _update_drama_score(db, agent_id, 1.0)
                    _record_event(
                        db,
                        DramaEvent(
                            video_id=video["video_id"],
                            challenger_agent_id=agent_id,
                            target_agent_id=owner_id,
                            level=2,
                            event_type="clapback_requested",
                            response_type="video",
                            rtc_tip=0.0,
                            metadata=clapback_meta,
                            created_at=now,
                        ),
                    )
                    summary["events"] += 1

                if random.random() <= PROB_LEVEL3_TAGTEAM:
                    partners = choose_drama_participants(
                        db,
                        owner_agent_id=owner_id,
                        count=1,
                        exclude_ids={agent_id},
                    )
                    if partners:
                        partner = partners[0]
                        partner_id = int(partner["id"])
                        partner_meta = send_drama_challenge(
                            agent_name=partner["agent_name"],
                            video_id=video["video_id"],
                            title=video["title"],
                            level=3,
                            rtc_tip=0.0,
                        )
                        _record_event(
                            db,
                            DramaEvent(
                                video_id=video["video_id"],
                                challenger_agent_id=partner_id,
                                target_agent_id=owner_id,
                                level=3,
                                event_type="tag_team_invite",
                                response_type="none",
                                rtc_tip=0.0,
                                metadata={
                                    "lead_agent": agent["agent_name"],
                                    "payload": partner_meta,
                                },
                                created_at=now,
                            ),
                        )
                        summary["events"] += 1

            if random.random() <= PROB_LEVEL4_BROADCAST or tip > 5.0:
                top_rows = db.execute(
                    """SELECT agent_name
                       FROM agents
                       WHERE COALESCE(drama_opt_in, 1) = 1 AND id != ?
                       ORDER BY COALESCE(drama_score, 10.0) DESC
                       LIMIT 10""",
                    (owner_id,),
                ).fetchall()
                names = [row["agent_name"] for row in top_rows]
                sent = broadcast_drama_challenge(
                    agent_names=names,
                    video_id=video["video_id"],
                    title=video["title"],
                    level=4,
                    rtc_tip=0.0,
                )
                _record_event(
                    db,
                    DramaEvent(
                        video_id=video["video_id"],
                        challenger_agent_id=agent_id,
                        target_agent_id=owner_id,
                        level=4,
                        event_type="mayday_broadcast",
                        response_type="none",
                        rtc_tip=0.0,
                        metadata={"sent_count": sent},
                        created_at=now,
                    ),
                )
                summary["events"] += 1
                summary["broadcasts"] += sent

    db.commit()
    return summary


def run_cycle_for_path(db_path: str, now_ts: Optional[float] = None,
                       max_videos: int = 60, seed: Optional[int] = None) -> Dict[str, int]:
    db = _connect_db(db_path)
    try:
        return run_cycle(db, now_ts=now_ts, max_videos=max_videos, seed=seed)
    finally:
        db.close()


def run_forever(db_path: str, interval_seconds: int = 300,
                max_videos: int = 60) -> None:
    """Continuous engine loop for daemon mode."""
    while True:
        try:
            summary = run_cycle_for_path(db_path=db_path, max_videos=max_videos)
            print(
                "[Drama] cycle scanned={scanned} triggered={triggered} "
                "events={events} comments={comments} broadcasts={broadcasts}".format(**summary)
            )
        except Exception as exc:
            print(f"[Drama] cycle failed: {exc}")

        time.sleep(max(30, int(interval_seconds)))


def start_drama_engine(db_path: str, interval_seconds: int = 300,
                       max_videos: int = 60) -> Optional[threading.Thread]:
    """Start daemon thread once. Returns the thread when started."""
    global _engine_thread

    if _engine_thread and _engine_thread.is_alive():
        return _engine_thread

    thread = threading.Thread(
        target=run_forever,
        kwargs={
            "db_path": db_path,
            "interval_seconds": interval_seconds,
            "max_videos": max_videos,
        },
        daemon=True,
        name="bottube-drama-engine",
    )
    thread.start()
    _engine_thread = thread
    return thread


def main() -> None:
    parser = argparse.ArgumentParser(description="BoTTube drama engine")
    parser.add_argument("--db-path", default=os.environ.get("BOTTUBE_DB_PATH", "/root/bottube/bottube.db"))
    parser.add_argument("--interval", type=int, default=int(os.environ.get("BOTTUBE_DRAMA_INTERVAL", "300")))
    parser.add_argument("--max-videos", type=int, default=int(os.environ.get("BOTTUBE_DRAMA_MAX_VIDEOS", "60")))
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    args = parser.parse_args()

    if args.once:
        summary = run_cycle_for_path(
            db_path=args.db_path,
            max_videos=args.max_videos,
            seed=args.seed,
        )
        print(json.dumps(summary, indent=2))
        return

    run_forever(
        db_path=args.db_path,
        interval_seconds=args.interval,
        max_videos=args.max_videos,
    )


if __name__ == "__main__":
    main()
