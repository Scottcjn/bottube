"""Tests for /api/trending parameter validation and wiring."""
import json
import os
import sqlite3
import tempfile
import time

import pytest


class TestTrendingParamParsing:
    """Verify that malformed params are rejected with 400.

    Uses a minimal Flask app that reproduces the validation logic from
    the trending() handler.
    """

    def _client(self):
        from flask import Flask, jsonify, request

        app = Flask(__name__)

        def _parse_positive_int_query(name, default, min_value=1, max_value=None):
            raw_value = request.args.get(name)
            if raw_value is None or raw_value == "":
                return default, None
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                return None, (jsonify({"error": f"{name} must be an integer"}), 400)
            if value < min_value:
                return None, (jsonify({"error": f"{name} must be >= {min_value}"}), 400)
            if max_value is not None and value > max_value:
                return None, (jsonify({"error": f"{name} must be <= {max_value}"}), 400)
            return value, None

        @app.route("/api/trending")
        def trending():
            limit, err = _parse_positive_int_query("limit", 20, max_value=50)
            if err:
                return err
            days = None
            since = None
            raw_days = request.args.get("days")
            raw_since = request.args.get("since")
            if raw_days is not None and raw_since is not None:
                return jsonify({"error": "days and since are mutually exclusive"}), 400
            if raw_days is not None and raw_days != "":
                days, err = _parse_positive_int_query("days", 1, max_value=90)
                if err:
                    return err
            if raw_since is not None and raw_since != "":
                since, err = _parse_positive_int_query("since", 0, min_value=0)
                if err:
                    return err
            return jsonify({"limit": limit, "days": days, "since": since})

        return app.test_client()

    def test_default_limit(self):
        r = self._client().get("/api/trending")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["limit"] == 20
        assert data["days"] is None
        assert data["since"] is None

    def test_custom_limit(self):
        r = self._client().get("/api/trending?limit=5")
        assert r.status_code == 200
        assert json.loads(r.data)["limit"] == 5

    def test_limit_too_high(self):
        r = self._client().get("/api/trending?limit=51")
        assert r.status_code == 400

    def test_limit_zero(self):
        r = self._client().get("/api/trending?limit=0")
        assert r.status_code == 400

    def test_limit_negative(self):
        r = self._client().get("/api/trending?limit=-1")
        assert r.status_code == 400

    def test_limit_malformed(self):
        r = self._client().get("/api/trending?limit=abc")
        assert r.status_code == 400

    def test_days_valid(self):
        r = self._client().get("/api/trending?days=7")
        assert r.status_code == 200
        assert json.loads(r.data)["days"] == 7

    def test_days_too_high(self):
        r = self._client().get("/api/trending?days=91")
        assert r.status_code == 400

    def test_days_zero(self):
        r = self._client().get("/api/trending?days=0")
        assert r.status_code == 400

    def test_days_malformed(self):
        r = self._client().get("/api/trending?days=abc")
        assert r.status_code == 400

    def test_since_valid(self):
        r = self._client().get("/api/trending?since=1700000000")
        assert r.status_code == 200
        assert json.loads(r.data)["since"] == 1700000000

    def test_since_negative(self):
        r = self._client().get("/api/trending?since=-1")
        assert r.status_code == 400

    def test_since_malformed(self):
        r = self._client().get("/api/trending?since=abc")
        assert r.status_code == 400

    def test_days_and_since_mutually_exclusive(self):
        r = self._client().get("/api/trending?days=7&since=1700000000")
        assert r.status_code == 400
        assert "mutually exclusive" in json.loads(r.data)["error"]


class TestTrendingWindowWiring:
    """Verify that days/since actually filter the result set.

    These tests use an in-memory SQLite database to confirm the wiring:
    videos created outside the window should NOT appear in results when
    days or since is specified.
    """

    def _make_db(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row

        now = time.time()
        cutoff_24h = now - 86400
        cutoff_6h = now - 21600
        old_ts = now - (30 * 86400)  # 30 days ago

        db.executescript("""
            CREATE TABLE videos (
                video_id TEXT PRIMARY KEY,
                agent_id INTEGER,
                title TEXT,
                created_at REAL,
                likes INTEGER DEFAULT 0,
                category TEXT,
                is_removed INTEGER DEFAULT 0,
                novelty_score REAL DEFAULT 0.5,
                novelty_flags TEXT DEFAULT ''
            );
            CREATE TABLE agents (
                id INTEGER PRIMARY KEY,
                agent_name TEXT,
                display_name TEXT,
                avatar_url TEXT,
                is_human INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0
            );
            CREATE TABLE views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                created_at REAL
            );
            CREATE TABLE comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                created_at REAL
            );
        """)

        db.execute("INSERT INTO agents (id, agent_name) VALUES (1, 'test_agent')")
        db.execute(
            "INSERT INTO videos (video_id, agent_id, title, created_at, likes) "
            "VALUES ('recent', 1, 'Recent Video', ?, 10)",
            (cutoff_6h + 3600,),
        )
        db.execute(
            "INSERT INTO videos (video_id, agent_id, title, created_at, likes) "
            "VALUES ('old', 1, 'Old Video', ?, 100)",
            (old_ts,),
        )
        db.commit()
        return db

    def test_days_window_excludes_old_videos(self):
        """With days=1, a video from 30 days ago should not appear."""
        db = self._make_db()
        now = time.time()
        days = 1
        window_cutoff = now - (days * 86400)
        cutoff_24h = now - 86400
        cutoff_6h = now - 21600

        params = [
            cutoff_6h, cutoff_24h, window_cutoff, window_cutoff, window_cutoff,
        ]
        params.extend([cutoff_6h, cutoff_24h, 0.5, 5.0, 3.0, 60])

        rows = db.execute(
            """SELECT v.video_id, v.created_at,
                  COALESCE(rv.recent_views, 0) AS recent_views,
                  COALESCE(rc.recent_comments, 0) AS recent_comments,
                  CASE WHEN v.created_at > ? THEN 10
                       WHEN v.created_at > ? THEN 5
                       ELSE 0 END AS recency_bonus
               FROM videos v
               JOIN agents a ON v.agent_id = a.id
               LEFT JOIN (
                   SELECT video_id, COUNT(*) AS recent_views
                   FROM views WHERE created_at > ?
                   GROUP BY video_id
               ) rv ON rv.video_id = v.video_id
               LEFT JOIN (
                   SELECT video_id, COUNT(*) AS recent_comments
                   FROM comments WHERE created_at > ?
                   GROUP BY video_id
               ) rc ON rc.video_id = v.video_id
               WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0
                 AND v.created_at >= ?
               ORDER BY (
                   COALESCE(rv.recent_views, 0) * 2
                   + v.likes * 3
                   + COALESCE(rc.recent_comments, 0) * 4
                   + CASE WHEN v.created_at > ? THEN 10
                          WHEN v.created_at > ? THEN 5 ELSE 0 END
                   + (v.novelty_score * ?)
                   + CASE WHEN v.novelty_flags LIKE '%high_similarity%' THEN -? ELSE 0 END
                   + CASE WHEN v.novelty_flags LIKE '%low_info%' THEN -? ELSE 0 END
               ) DESC, v.created_at DESC
               LIMIT ?""",
            params,
        ).fetchall()

        video_ids = [r["video_id"] for r in rows]
        assert "recent" in video_ids
        assert "old" not in video_ids, (
            "Video from 30 days ago should be excluded with days=1"
        )

    def test_since_filter_excludes_old_videos(self):
        """With since=24h_ago, a 30-day-old video should not appear."""
        db = self._make_db()
        now = time.time()
        since = now - 86400
        cutoff_24h = now - 86400
        cutoff_6h = now - 21600

        params = [since, since, since]
        params.extend([cutoff_6h, cutoff_24h, 0.5, 5.0, 3.0, 60])

        rows = db.execute(
            """SELECT v.video_id
               FROM videos v
               JOIN agents a ON v.agent_id = a.id
               LEFT JOIN (
                   SELECT video_id, COUNT(*) AS recent_views
                   FROM views WHERE created_at > ?
                   GROUP BY video_id
               ) rv ON rv.video_id = v.video_id
               LEFT JOIN (
                   SELECT video_id, COUNT(*) AS recent_comments
                   FROM comments WHERE created_at > ?
                   GROUP BY video_id
               ) rc ON rc.video_id = v.video_id
               WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0
                 AND v.created_at >= ?
               ORDER BY (
                   COALESCE(rv.recent_views, 0) * 2
                   + v.likes * 3
                   + COALESCE(rc.recent_comments, 0) * 4
                   + CASE WHEN v.created_at > ? THEN 10
                          WHEN v.created_at > ? THEN 5 ELSE 0 END
                   + (v.novelty_score * ?)
                   + CASE WHEN v.novelty_flags LIKE '%high_similarity%' THEN -? ELSE 0 END
                   + CASE WHEN v.novelty_flags LIKE '%low_info%' THEN -? ELSE 0 END
               ) DESC, v.created_at DESC
               LIMIT ?""",
            params,
        ).fetchall()

        video_ids = [r["video_id"] for r in rows]
        assert "recent" in video_ids
        assert "old" not in video_ids

    def test_no_window_returns_all(self):
        """Without days/since, both old and new videos should appear."""
        db = self._make_db()
        now = time.time()
        cutoff_24h = now - 86400
        cutoff_6h = now - 21600

        params = [cutoff_24h, cutoff_24h]
        params.extend([cutoff_6h, cutoff_24h, 0.5, 5.0, 3.0, 60])

        rows = db.execute(
            """SELECT v.video_id
               FROM videos v
               JOIN agents a ON v.agent_id = a.id
               LEFT JOIN (
                   SELECT video_id, COUNT(*) AS recent_views
                   FROM views WHERE created_at > ?
                   GROUP BY video_id
               ) rv ON rv.video_id = v.video_id
               LEFT JOIN (
                   SELECT video_id, COUNT(*) AS recent_comments
                   FROM comments WHERE created_at > ?
                   GROUP BY video_id
               ) rc ON rc.video_id = v.video_id
               WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0
               ORDER BY (
                   COALESCE(rv.recent_views, 0) * 2
                   + v.likes * 3
                   + COALESCE(rc.recent_comments, 0) * 4
                   + CASE WHEN v.created_at > ? THEN 10
                          WHEN v.created_at > ? THEN 5 ELSE 0 END
                   + (v.novelty_score * ?)
                   + CASE WHEN v.novelty_flags LIKE '%high_similarity%' THEN -? ELSE 0 END
                   + CASE WHEN v.novelty_flags LIKE '%low_info%' THEN -? ELSE 0 END
               ) DESC, v.created_at DESC
               LIMIT ?""",
            params,
        ).fetchall()

        video_ids = [r["video_id"] for r in rows]
        assert "recent" in video_ids
        assert "old" in video_ids

    def test_recency_bonus_anchored_to_24h(self):
        """The recency_bonus +5 tier must always use 24h, not the window."""
        db = self._make_db()
        now = time.time()
        cutoff_24h = now - 86400
        cutoff_6h = now - 21600
        window_90d = now - (90 * 86400)

        ts_48h = now - 172800
        db.execute(
            "INSERT INTO videos (video_id, agent_id, title, created_at, likes) "
            "VALUES ('two_day', 1, '48h Video', ?, 50)",
            (ts_48h,),
        )
        db.commit()

        params = [
            cutoff_6h, cutoff_24h, window_90d, window_90d, window_90d,
        ]
        params.extend([cutoff_6h, cutoff_24h, 0.5, 5.0, 3.0, 60])

        rows = db.execute(
            """SELECT v.video_id,
                  CASE WHEN v.created_at > ? THEN 10
                       WHEN v.created_at > ? THEN 5
                       ELSE 0 END AS recency_bonus
               FROM videos v
               JOIN agents a ON v.agent_id = a.id
               LEFT JOIN (
                   SELECT video_id, COUNT(*) AS recent_views
                   FROM views WHERE created_at > ?
                   GROUP BY video_id
               ) rv ON rv.video_id = v.video_id
               LEFT JOIN (
                   SELECT video_id, COUNT(*) AS recent_comments
                   FROM comments WHERE created_at > ?
                   GROUP BY video_id
               ) rc ON rc.video_id = v.video_id
               WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0
                 AND v.created_at >= ?
               ORDER BY (
                   COALESCE(rv.recent_views, 0) * 2
                   + v.likes * 3
                   + COALESCE(rc.recent_comments, 0) * 4
                   + CASE WHEN v.created_at > ? THEN 10
                          WHEN v.created_at > ? THEN 5 ELSE 0 END
                   + (v.novelty_score * ?)
                   + CASE WHEN v.novelty_flags LIKE '%high_similarity%' THEN -? ELSE 0 END
                   + CASE WHEN v.novelty_flags LIKE '%low_info%' THEN -? ELSE 0 END
               ) DESC, v.created_at DESC
               LIMIT ?""",
            params,
        ).fetchall()

        for row in rows:
            if row["video_id"] == "two_day":
                assert row["recency_bonus"] == 0, (
                    "48h-old video should get 0 recency_bonus even with days=90"
                )
            elif row["video_id"] == "recent":
                assert row["recency_bonus"] == 10
