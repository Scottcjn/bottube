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
    """Plans the module's real query, so the SQL under test can't drift."""
    db = _db()
    sql = feed_cowatch.COWATCH_SQL.format(placeholders="?", limit=feed_cowatch.COWATCH_LIMIT)
    plan = [r[3] for r in db.execute("EXPLAIN QUERY PLAN " + sql, ("anchor", '["%s"]' % HOT))]
    assert any("SEARCH v2 USING COVERING INDEX idx_views_ip_video" in p for p in plan), plan
    assert not any(p.startswith("SCAN v2") for p in plan), plan


class _CountingBroken:
    def __init__(self):
        self.calls = 0

    def execute(self, *a, **k):
        self.calls += 1
        raise sqlite3.OperationalError("no such table: json_each")


def test_failed_refresh_is_retried_after_short_backoff():
    broken = _CountingBroken()
    retry = feed_cowatch.FAILED_RETRY_SECONDS
    feed_cowatch.hot_ips(broken, now=0.0)
    feed_cowatch.hot_ips(broken, now=1.0)
    feed_cowatch.hot_ips(broken, now=retry - 1)
    assert broken.calls == 1
    feed_cowatch.hot_ips(broken, now=retry + 1)
    assert broken.calls == 2


def test_recovery_after_failure_uses_full_ttl():
    feed_cowatch.hot_ips(_CountingBroken(), now=0.0)
    db = _db()
    assert HOT in feed_cowatch.hot_ips(db, now=feed_cowatch.FAILED_RETRY_SECONDS + 1)
    broken = _CountingBroken()
    feed_cowatch.hot_ips(broken, now=feed_cowatch.FAILED_RETRY_SECONDS + 100)
    assert broken.calls == 0  # healthy result is cached for the full TTL


def test_config_change_forces_refresh(monkeypatch):
    db = _db()
    assert HOT in feed_cowatch.hot_ips(db, now=0.0)
    monkeypatch.setenv("BOTTUBE_COWATCH_MAX_IP_VIDEOS", "1000")
    assert HOT not in feed_cowatch.hot_ips(db, now=1.0)  # within TTL, but the key changed


def test_only_one_thread_refreshes_at_a_time():
    import threading

    started, release = threading.Event(), threading.Event()
    calls = []

    class Slow:
        def execute(self, *a, **k):
            calls.append(1)
            started.set()
            release.wait(5)

            class R:
                def fetchall(self):
                    return [(HOT,)]
            return R()

    feed_cowatch.hot_ips(_db(), now=0.0)  # warm cache
    t = threading.Thread(target=feed_cowatch.hot_ips, args=(Slow(),), kwargs={"now": 10_000.0})
    t.start()
    assert started.wait(5)
    # A second caller during the refresh gets the stale set without querying.
    assert HOT in feed_cowatch.hot_ips(Slow(), now=10_000.5)
    release.set()
    t.join(5)
    assert not t.is_alive()
    assert len(calls) == 1


def _slow_db(calls, started, release):
    class Slow:
        def execute(self, *a, **k):
            calls.append(1)
            started.set()
            release.wait(5)

            class R:
                def fetchall(self):
                    return [(HOT,)]
            return R()
    return Slow()


def test_cold_cache_has_a_single_refresher():
    import threading

    started, release, calls = threading.Event(), threading.Event(), []
    t = threading.Thread(target=feed_cowatch.hot_ips,
                         args=(_slow_db(calls, started, release),), kwargs={"now": 0.0})
    t.start()
    assert started.wait(5)
    # Cold cache: a concurrent caller gets the static list, without a second scan.
    assert feed_cowatch.hot_ips(_slow_db(calls, started, release), now=0.1) == frozenset()
    release.set()
    t.join(5)
    assert not t.is_alive()
    assert len(calls) == 1
    assert HOT in feed_cowatch.hot_ips(_db(), now=0.2)


def test_stale_refresh_from_old_config_is_discarded(monkeypatch):
    import threading

    started, release, calls = threading.Event(), threading.Event(), []
    t = threading.Thread(target=feed_cowatch.hot_ips,
                         args=(_slow_db(calls, started, release),), kwargs={"now": 0.0})
    t.start()
    assert started.wait(5)
    monkeypatch.setenv("BOTTUBE_COWATCH_MAX_IP_VIDEOS", "1000")  # config changes mid-refresh
    assert HOT not in feed_cowatch.hot_ips(_db(), now=0.1)       # new-config refresh publishes
    release.set()
    t.join(5)
    assert not t.is_alive()
    # The old-config refresh finished later but must not overwrite the new result.
    assert HOT not in feed_cowatch.hot_ips(_db(), now=0.2)
