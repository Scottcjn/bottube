# SPDX-License-Identifier: MIT
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import feed_cowatch  # noqa: E402

HOT = "50.28.86.153"  # e.g. the host's own bot fleet


def _db(hot_videos=300):
    db = sqlite3.connect(":memory:")
    db.executescript(
        """CREATE TABLE views (id INTEGER PRIMARY KEY, video_id TEXT, agent_id INTEGER,
                               ip_address TEXT, created_at REAL);
           CREATE INDEX idx_views_dedup ON views(video_id, ip_address, created_at);
           CREATE INDEX idx_views_ip_video ON views(ip_address, video_id);"""
    )
    rows = []
    # Two real viewers who watched the anchor and "b"; one who watched anchor and "c".
    for ip, vids in (("1.1.1.1", ["anchor", "b"]), ("2.2.2.2", ["anchor", "b"]),
                     ("3.3.3.3", ["anchor", "c"])):
        rows += [(v, ip) for v in vids]
    # One hot IP that "watched" the anchor and hundreds of other videos.
    rows += [("anchor", HOT)] + [(f"bot{i}", HOT) for i in range(hot_videos)]
    db.executemany("INSERT INTO views (video_id, ip_address, created_at) VALUES (?, ?, 0)", rows)
    return db


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("BOTTUBE_COWATCH_MAX_IP_VIDEOS", raising=False)
    monkeypatch.delenv("BOTTUBE_COWATCH_EXCLUDE_IPS", raising=False)
    feed_cowatch.reset_cache()
    yield
    feed_cowatch.reset_cache()


def test_hot_ip_is_excluded_but_real_cowatchers_still_count():
    scores = feed_cowatch.cowatch_scores(_db(), ["anchor"])
    assert scores == {"b": 2, "c": 1}
    assert not any(v.startswith("bot") for v in scores)


def test_without_exclusion_the_hot_ip_links_everything(monkeypatch):
    monkeypatch.setenv("BOTTUBE_COWATCH_MAX_IP_VIDEOS", "0")  # disabled
    scores = feed_cowatch.cowatch_scores(_db(), ["anchor"])
    assert scores["b"] == 2
    assert sum(v.startswith("bot") for v in scores) == 300


def test_threshold_is_strictly_greater_than(monkeypatch):
    # HOT has viewed 301 distinct videos (anchor + 300).
    monkeypatch.setenv("BOTTUBE_COWATCH_MAX_IP_VIDEOS", "301")
    assert HOT not in feed_cowatch.hot_ips(_db())
    feed_cowatch.reset_cache()
    monkeypatch.setenv("BOTTUBE_COWATCH_MAX_IP_VIDEOS", "300")
    assert HOT in feed_cowatch.hot_ips(_db())


def test_static_exclude_list_applies_below_threshold(monkeypatch):
    monkeypatch.setenv("BOTTUBE_COWATCH_EXCLUDE_IPS", " 3.3.3.3 , ")
    scores = feed_cowatch.cowatch_scores(_db(), ["anchor"])
    assert scores == {"b": 2}


def test_hot_set_is_cached_until_ttl_then_refreshed():
    db = _db()
    first = feed_cowatch.hot_ips(db, now=1000.0)
    assert HOT in first
    db.execute("DELETE FROM views WHERE ip_address = ?", (HOT,))
    assert feed_cowatch.hot_ips(db, now=1000.0 + feed_cowatch.HOT_IP_TTL_SECONDS - 1) == first
    assert HOT not in feed_cowatch.hot_ips(db, now=1000.0 + feed_cowatch.HOT_IP_TTL_SECONDS + 1)


def test_refresh_failure_keeps_last_good_set():
    db = _db()
    good = feed_cowatch.hot_ips(db, now=0.0)

    class Broken:
        def execute(self, *a, **k):
            raise sqlite3.OperationalError("database is locked")

    assert feed_cowatch.hot_ips(Broken(), now=10_000.0) == good


def test_empty_anchor_list_returns_empty():
    assert feed_cowatch.cowatch_scores(_db(), []) == {}


def test_exclusion_keeps_indexed_plan():
    db = _db()
    excluded = '["%s"]' % HOT
    plan = [r[3] for r in db.execute(
        """EXPLAIN QUERY PLAN
           SELECT v2.video_id, COUNT(DISTINCT v1.ip_address)
             FROM views v1 JOIN views v2
               ON v1.ip_address = v2.ip_address AND v1.video_id != v2.video_id
            WHERE v1.video_id IN (?) AND v1.ip_address IS NOT NULL AND v1.ip_address != ''
              AND v1.ip_address NOT IN (SELECT value FROM json_each(?))
            GROUP BY v2.video_id""",
        ("anchor", excluded),
    )]
    assert any("SEARCH v2 USING COVERING INDEX idx_views_ip_video" in p for p in plan), plan
    assert not any(p.startswith("SCAN v2") for p in plan), plan
