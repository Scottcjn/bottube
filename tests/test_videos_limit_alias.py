# SPDX-License-Identifier: MIT
"""
Regression tests for the `limit` query-parameter alias on `/api/videos`
and `/api/v1/videos`.

Bottube issue #1414: third-party bot clients (and a documentation
snippet in the issue report) send ``?limit=N`` to size the page, but
``list_videos`` only parses ``per_page``. The result was that every
``limit`` request silently coerced to the default page size of 20.

This test asserts:
- ``?limit=N`` is honoured as an alias for ``?per_page=N``.
- ``?per_page=N`` still wins (regression for the original parameter).
- Supplying both returns HTTP 400 with a clear ``error`` message.
- ``/api/v1/videos`` (the canonical alias added in PR #1408 / Bottube
  #1383) inherits the same behaviour.
- Existing pagination-validation behaviour for ``per_page`` is unchanged
  (out-of-range / malformed values still 400).
"""

import time


def _seed_agent_and_videos():
    import bottube_server

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        existing = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            ("limit_alias_bot",),
        ).fetchone()
        if existing:
            return int(existing["id"])
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio,
                 avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', 0, ?, ?)
            """,
            (
                "limit_alias_bot",
                "Limit Alias Bot",
                "bottube_sk_limit_alias",
                time.time(),
                time.time(),
            ),
        )
        agent_id = int(cur.lastrowid)
        for idx in range(8):
            video_id = f"limitvid{idx:02d}"
            db.execute(
                """
                INSERT INTO videos
                    (video_id, agent_id, title, filename, created_at,
                     is_removed)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (
                    video_id,
                    agent_id,
                    f"Limit Alias Video {idx}",
                    f"{video_id}.mp4",
                    time.time() + idx,
                ),
            )
        db.commit()
        return agent_id


# ---------- /api/videos ----------


def test_list_videos_limit_alias_honoured(client):
    _seed_agent_and_videos()

    response = client.get("/api/videos?limit=3")
    assert response.status_code == 200
    data = response.get_json()
    assert data["per_page"] == 3
    assert len(data["videos"]) == 3


def test_list_videos_limit_alias_accepts_max_boundary(client):
    _seed_agent_and_videos()

    response = client.get("/api/videos?limit=50")
    assert response.status_code == 200
    data = response.get_json()
    assert data["per_page"] == 50
    assert len(data["videos"]) == 8  # only 8 seeded, less than cap


def test_list_videos_limit_alias_rejects_above_max(client):
    _seed_agent_and_videos()

    response = client.get("/api/videos?limit=51")
    assert response.status_code == 400
    data = response.get_json()
    assert "limit" in data["error"]
    assert "<= 50" in data["error"]


def test_list_videos_limit_alias_rejects_malformed(client):
    _seed_agent_and_videos()

    response = client.get("/api/videos?limit=abc")
    assert response.status_code == 400
    data = response.get_json()
    assert "limit" in data["error"]


def test_list_videos_limit_alias_rejects_zero(client):
    _seed_agent_and_videos()

    response = client.get("/api/videos?limit=0")
    assert response.status_code == 400


def test_list_videos_per_page_still_wins_over_limit(client):
    """When both are supplied, the request is rejected outright so
    the precedence is explicit rather than silently dropped."""
    _seed_agent_and_videos()

    response = client.get("/api/videos?per_page=4&limit=4")
    assert response.status_code == 400
    data = response.get_json()
    assert "per_page" in data["error"]
    assert "limit" in data["error"]
    assert "mutually exclusive" in data["error"]


def test_list_videos_per_page_only_still_works(client):
    """Backwards-compat regression: per_page alone still honours."""
    _seed_agent_and_videos()

    response = client.get("/api/videos?per_page=2")
    assert response.status_code == 200
    data = response.get_json()
    assert data["per_page"] == 2
    assert len(data["videos"]) == 2


def test_list_videos_default_page_size_unchanged_when_no_param(client):
    """Regression: no limit + no per_page -> default 20."""
    response = client.get("/api/videos")
    assert response.status_code == 200
    data = response.get_json()
    assert data["per_page"] == 20


# ---------- /api/v1/videos (canonical alias from PR #1408 / Bottube #1383) ----------


def test_list_videos_v1_alias_honours_limit(client):
    _seed_agent_and_videos()

    response = client.get("/api/v1/videos?limit=2")
    assert response.status_code == 200
    data = response.get_json()
    assert data["per_page"] == 2
    assert len(data["videos"]) == 2


def test_list_videos_v1_alias_rejects_both_params(client):
    _seed_agent_and_videos()

    response = client.get("/api/v1/videos?per_page=3&limit=3")
    assert response.status_code == 400
    data = response.get_json()
    assert "mutually exclusive" in data["error"]


# ---------- _make_param_conflict_error helper ----------


def test_make_param_conflict_error_shape(app):
    with app.test_request_context("/api/videos?per_page=4&limit=4"):
        from bottube_server import _make_param_conflict_error

        response, status = _make_param_conflict_error("per_page", "limit")
        assert status == 400
        body = response.get_json()
        assert body["error"]
        assert "per_page" in body["error"]
        assert "limit" in body["error"]


# ---------- `page` upper bound (issue #1414 follow-up) ----------
#
# Bottube's live production binary (v1.2.0, months behind
# `scottcjn/main`) lets `?page=99999` through and returns
# `{"page":99999,"per_page":20,"total":1860,"videos":[]}`, an unbounded
# SQLite OFFSET scan + a useless empty page. The 2026-06-14 live check
# on bottube.ai reproduced this; the same call after the fix in this
# branch returns HTTP 400 with a clear error so the client knows the
# request is invalid. The cap is 10000 (i.e. ~500k rows even at the
# `per_page<=50` ceiling), which is well past the current catalogue of
# ~1860 videos so no legitimate pagination is affected.


def test_list_videos_page_rejects_over_max(client):
    """`page=99999` is rejected with HTTP 400 (defense in depth)."""
    response = client.get("/api/videos?page=99999")
    assert response.status_code == 400
    data = response.get_json()
    assert "page" in data["error"]
    assert "<= 10000" in data["error"]


def test_list_videos_page_accepts_max_boundary(client):
    """`page=10000` (the cap) is accepted and clamped server-side."""
    response = client.get("/api/videos?page=10000")
    assert response.status_code == 200
    data = response.get_json()
    # The actual returned `page` may be even lower when the catalogue is
    # shorter than 10000 pages, but it must be a positive integer and
    # not 99999.
    assert isinstance(data["page"], int)
    assert 1 <= data["page"] <= 10000


def test_list_videos_page_rejects_just_above_max(client):
    """`page=10001` is rejected (off-by-one around the cap)."""
    response = client.get("/api/videos?page=10001")
    assert response.status_code == 400
    data = response.get_json()
    assert "page" in data["error"]


def test_list_videos_v1_alias_page_rejects_over_max(client):
    """The /api/v1/videos alias inherits the new page cap."""
    response = client.get("/api/v1/videos?page=99999")
    assert response.status_code == 400
    data = response.get_json()
    assert "page" in data["error"]