# SPDX-License-Identifier: MIT
"""Co-watch scoring for the hybrid feed.

"Viewers who watched X also watched Y" is keyed by viewer IP. That only means
something when an IP is roughly one person. A small number of addresses are
not: the bot fleet that runs on the BoTTube host itself (recorded under the
server's own public IP), crawlers, and large shared NATs. On production
(2026-09-26) 180 of ~182,000 IPs held 46% of all view rows, and the server's
own address alone had ~78,000 views across ~2,150 videos. Every one of those
"hot" IPs links every video it touched to every other, so

  * the co-watch self-join fans out through them (127 s for the three
    busiest videos; ~1 s for the default anonymous-feed anchors), and
  * their links drown out the signal from real viewers.

So co-watch ignores any IP that has viewed more than a threshold of distinct
videos. The hot set is computed with one GROUP BY over the covering index
``idx_views_ip_video`` (~0.2 s on production) and cached per process.

Environment:
  BOTTUBE_COWATCH_MAX_IP_VIDEOS  distinct-video threshold (default 200;
                                 0 or negative disables the exclusion)
  BOTTUBE_COWATCH_EXCLUDE_IPS    extra comma-separated IPs to always ignore
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

HOT_IP_TTL_SECONDS = 600
COWATCH_LIMIT = 400

_cache_lock = threading.Lock()
_cache = {"ts": 0.0, "key": None, "ips": frozenset(), "refreshing": False}


def _max_ip_videos() -> int:
    try:
        return int(os.environ.get("BOTTUBE_COWATCH_MAX_IP_VIDEOS", "200"))
    except ValueError:
        return 200


def _static_excluded_ips() -> frozenset:
    raw = os.environ.get("BOTTUBE_COWATCH_EXCLUDE_IPS", "")
    return frozenset(ip.strip() for ip in raw.split(",") if ip.strip())


def hot_ips(db, now=None) -> frozenset:
    """IPs excluded from co-watch: static list plus any IP over the threshold.

    Cached for HOT_IP_TTL_SECONDS. Only one thread refreshes at a time; the
    others keep serving the previous set meanwhile. A failed refresh is cached
    too (keeping the last good set), so a broken query is retried once per TTL
    rather than on every feed request.
    """
    now = time.time() if now is None else now
    threshold = _max_ip_videos()
    static = _static_excluded_ips()
    key = (threshold, static)
    with _cache_lock:
        fresh = _cache["key"] == key and now - _cache["ts"] < HOT_IP_TTL_SECONDS
        if fresh or (_cache["refreshing"] and _cache["key"] == key):
            return _cache["ips"]
        _cache["refreshing"] = True
        previous = _cache["ips"] if _cache["key"] == key else static
    ips = previous
    try:
        dynamic = frozenset()
        if threshold > 0:
            rows = db.execute(
                """SELECT ip_address FROM views
                    WHERE ip_address IS NOT NULL AND ip_address != ''
                    GROUP BY ip_address
                   HAVING COUNT(DISTINCT video_id) > ?""",
                (threshold,),
            ).fetchall()
            dynamic = frozenset(r[0] for r in rows)
        ips = dynamic | static
    except Exception as exc:
        log.warning("co-watch hot-IP refresh failed, keeping previous set: %s", exc)
        ips = previous | static
    finally:
        with _cache_lock:
            _cache.update(ts=now, key=key, ips=ips, refreshing=False)
    return ips


def reset_cache() -> None:
    """Forget the cached hot-IP set (tests, or after a config change)."""
    with _cache_lock:
        _cache.update(ts=0.0, key=None, ips=frozenset(), refreshing=False)


COWATCH_SQL = """SELECT v2.video_id AS vid,
                   COUNT(DISTINCT v1.ip_address) AS cnt
              FROM views v1
              JOIN views v2
                ON v1.ip_address = v2.ip_address
               AND v1.video_id != v2.video_id
             WHERE v1.video_id IN ({placeholders})
               AND v1.ip_address IS NOT NULL
               AND v1.ip_address != ''
               AND v1.ip_address NOT IN (SELECT value FROM json_each(?))
             GROUP BY v2.video_id
             ORDER BY cnt DESC
             LIMIT {limit}"""


def cowatch_scores(db, anchor_video_ids) -> dict:
    """Map video_id -> number of distinct (non-hot) IPs that watched it and an anchor."""
    if not anchor_video_ids:
        return {}
    excluded = json.dumps(sorted(hot_ips(db)))
    placeholders = ",".join("?" for _ in anchor_video_ids)
    rows = db.execute(
        COWATCH_SQL.format(placeholders=placeholders, limit=COWATCH_LIMIT),
        [*anchor_video_ids, excluded],
    ).fetchall()
    return {r[0]: int(r[1]) for r in rows}
