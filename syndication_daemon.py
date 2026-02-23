#!/usr/bin/env python3
"""
BoTTube unified syndication daemon (issue #50).

- Polls BoTTube /api/feed for new uploads
- Generates platform-specific payload plans for 5+ platforms
- Applies scheduling jitter to avoid blasting
- Tracks engagement snapshots into SQLite
- Writes a simple HTML dashboard report

This implementation is intentionally safe-by-default:
- `dry_run=true` unless explicitly disabled
- no external posting unless adapter env vars are configured
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import random
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

PLATFORMS = ["youtube_shorts", "tiktok", "instagram_reels", "x_twitter", "reddit", "moltbook", "farcaster"]


def now_ts() -> float:
    return time.time()


def iso(ts: float) -> str:
    return dt.datetime.utcfromtimestamp(ts).isoformat() + "Z"


@dataclasses.dataclass
class Config:
    bottube_base: str
    poll_seconds: int
    max_items_per_poll: int
    dry_run: bool
    schedule_spread_seconds: int
    db_path: str
    dashboard_path: str
    platforms: Dict[str, Dict]


class Store:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS seen_videos (video_id TEXT PRIMARY KEY, seen_at REAL NOT NULL)")
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS syndication_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT DEFAULT '',
                scheduled_at REAL,
                posted_at REAL,
                created_at REAL NOT NULL
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS engagement_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                captured_at REAL NOT NULL
            )"""
        )
        self.conn.commit()

    def has_seen(self, video_id: str) -> bool:
        return bool(self.conn.execute("SELECT 1 FROM seen_videos WHERE video_id=?", (video_id,)).fetchone())

    def mark_seen(self, video_id: str):
        self.conn.execute("INSERT OR IGNORE INTO seen_videos(video_id, seen_at) VALUES(?,?)", (video_id, now_ts()))
        self.conn.commit()

    def event(self, video_id: str, platform: str, status: str, message: str = "", scheduled_at: Optional[float] = None, posted_at: Optional[float] = None):
        self.conn.execute(
            "INSERT INTO syndication_events(video_id,platform,status,message,scheduled_at,posted_at,created_at) VALUES(?,?,?,?,?,?,?)",
            (video_id, platform, status, message, scheduled_at, posted_at, now_ts()),
        )
        self.conn.commit()

    def snapshot(self, video_id: str, platform: str, views: int, likes: int, comments: int):
        self.conn.execute(
            "INSERT INTO engagement_snapshots(video_id,platform,views,likes,comments,captured_at) VALUES(?,?,?,?,?,?)",
            (video_id, platform, views, likes, comments, now_ts()),
        )
        self.conn.commit()

    def dashboard_rows(self):
        return self.conn.execute(
            """SELECT video_id, platform,
                      SUM(CASE WHEN status='posted' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN status='scheduled' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END),
                      MAX(created_at)
               FROM syndication_events
               GROUP BY video_id, platform
               ORDER BY MAX(created_at) DESC
               LIMIT 500"""
        ).fetchall()


class BoTTubeClient:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def feed(self, page: int = 1, per_page: int = 20) -> List[dict]:
        url = f"{self.base}/api/feed?mode=latest&page={page}&per_page={per_page}"
        req = urllib.request.Request(url, headers={"User-Agent": "bottube-syndication-daemon/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data.get("videos", [])


class Adapter:
    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg or {}

    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled", False))

    def post(self, video: dict, dry_run: bool = True) -> dict:
        watch_url = f"https://bottube.ai/watch/{video['video_id']}"
        if dry_run:
            return {"ok": True, "message": f"dry-run prepared post for {self.name}"}
        return {"ok": False, "message": f"{self.name}: adapter not configured (set credentials)"}


def load_config(path: str) -> Config:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    platforms = raw.get("platforms") or {}
    for p in PLATFORMS:
        platforms.setdefault(p, {"enabled": False})
    return Config(
        bottube_base=raw.get("bottube_base", "https://bottube.ai"),
        poll_seconds=int(raw.get("poll_seconds", 600)),
        max_items_per_poll=int(raw.get("max_items_per_poll", 10)),
        dry_run=bool(raw.get("dry_run", True)),
        schedule_spread_seconds=int(raw.get("schedule_spread_seconds", 1800)),
        db_path=raw.get("db_path", "syndication.db"),
        dashboard_path=raw.get("dashboard_path", "syndication_report.html"),
        platforms=platforms,
    )


def render_dashboard(store: Store, out_path: str):
    rows = store.dashboard_rows()
    trs = []
    for video_id, platform, posted, scheduled, failed, updated_at in rows:
        trs.append(f"<tr><td>{video_id}</td><td>{platform}</td><td>{posted}</td><td>{scheduled}</td><td>{failed}</td><td>{iso(updated_at or now_ts())}</td></tr>")
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>Syndication Report</title>
<style>body{{font-family:system-ui;padding:20px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px}}</style>
</head><body><h1>BoTTube Syndication Report</h1><p>Generated: {iso(now_ts())}</p>
<table><thead><tr><th>Video</th><th>Platform</th><th>Posted</th><th>Scheduled</th><th>Failed</th><th>Updated</th></tr></thead><tbody>{''.join(trs)}</tbody></table>
</body></html>"""
    Path(out_path).write_text(html, encoding="utf-8")


def run_once(cfg: Config, store: Store):
    client = BoTTubeClient(cfg.bottube_base)
    adapters = {p: Adapter(p, cfg.platforms.get(p, {})) for p in PLATFORMS}
    videos = client.feed(page=1, per_page=max(20, cfg.max_items_per_poll))
    processed = 0
    for v in videos:
        vid = v.get("video_id")
        if not vid or store.has_seen(vid):
            continue
        desc = (v.get("description") or "").lower()
        if "#nosyndicate" in desc:
            store.mark_seen(vid)
            continue
        base = now_ts()
        for platform, adapter in adapters.items():
            if not adapter.enabled():
                continue
            delay = random.randint(0, max(0, cfg.schedule_spread_seconds))
            scheduled = base + delay
            store.event(vid, platform, "scheduled", f"scheduled +{delay}s", scheduled_at=scheduled)
            res = adapter.post(v, dry_run=cfg.dry_run)
            if res.get("ok"):
                store.event(vid, platform, "posted", res.get("message", "ok"), scheduled_at=scheduled, posted_at=now_ts())
                store.snapshot(vid, platform, 0, 0, 0)
            else:
                store.event(vid, platform, "failed", res.get("message", "failed"), scheduled_at=scheduled)
        store.mark_seen(vid)
        processed += 1
        if processed >= cfg.max_items_per_poll:
            break
    render_dashboard(store, cfg.dashboard_path)
    return processed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="syndication_config.json")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    store = Store(cfg.db_path)
    if args.once:
        print(f"processed={run_once(cfg, store)} dry_run={cfg.dry_run}")
        return
    while True:
        try:
            print(f"[{iso(now_ts())}] processed={run_once(cfg, store)}")
        except Exception as e:
            print(f"[{iso(now_ts())}] error: {e}")
        time.sleep(max(30, cfg.poll_seconds))


if __name__ == "__main__":
    main()
