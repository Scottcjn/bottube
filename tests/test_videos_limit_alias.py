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
    """Verify /api/videos honours ?limit=N as an alias for ?per_page=N.

    Regression for Bottube #1414: third-party bot clients send ?limit=N
    but list_videos only parsed per_page, silently coercing to the
    default of 20. This test asserts the alias is now recognised and
    the returned page has exactly limit items (capped by total seeded).
    """
    _seed_agent_and_videos()

    response = client.get("/api/videos?limit=3")
    assert response.status_code == 200
    data = response.get_json()
    assert data["per_page"] == 3
    assert len(data["videos"]) == 3


def test_list_videos_limit_alias_accepts_max_boundary(client):
    """Verify ?limit=50 is accepted and the page size is 50.

    Boundary check for the validator: the inclusive upper bound (50)
    must be accepted. The test seeds 8 videos so the returned list is
    shorter than 50 (sanity check that limit doesn't overflow into
    fabricated rows).
    """
    _seed_agent_and_videos()

    response = client.get("/api/videos?limit=50")
    assert response.status_code == 200
    data = response.get_json()
    assert data["per_page"] == 50
    assert len(data["videos"]) == 8  # only 8 seeded, less than cap


def test_list_videos_limit_alias_rejects_above_max(client):
    """Verify ?limit=51 is rejected with 400 and a clear error.

    Off-by-one guard for the upper bound: limit=51 (one past the cap)
    must 400 with an error message that mentions 'limit' and '<= 50'
    so clients can show a precise validation hint instead of silently
    coercing to the cap.
    """
    _seed_agent_and_videos()

    response = client.get("/api/videos?limit=51")
    assert response.status_code == 400
    data = response.get_json()
    assert "limit" in data["error"]
    assert "<= 50" in data["error"]


def test_list_videos_limit_alias_rejects_malformed(client):
    """Verify ?limit=abc is rejected with 400.

    Non-integer values must fail validation with an error mentioning
    'limit' so the SDK can distinguish from a per_page failure (which
    would have a different message key).
    """
    _seed_agent_and_videos()

    response = client.get("/api/videos?limit=abc")
    assert response.status_code == 400
    data = response.get_json()
    assert "limit" in data["error"]


def test_list_videos_limit_alias_rejects_zero(client):
    """Verify ?limit=0 is rejected with 400.

    Lower bound guard: limit must be >= 1 (zero would return an empty
    page which is confusing UX and likely a client bug).
    """
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
    """Verify /api/v1/videos inherits the ?limit alias support.

    The /v1 alias must mirror /api/videos behaviour so old SDKs
    hitting the alias get the same page-size semantics.
    """
    _seed_agent_and_videos()

    response = client.get("/api/v1/videos?limit=2")
    assert response.status_code == 200
    data = response.get_json()
    assert data["per_page"] == 2
    assert len(data["videos"]) == 2


def test_list_videos_v1_alias_rejects_both_params(client):
    """Verify /api/v1/videos also rejects per_page+limit supplied together.

    Same mutual-exclusivity contract as the canonical route. Without
    this the alias would silently accept both and pick one, leading
    to confusion when a client expects deterministic precedence.
    """
    _seed_agent_and_videos()

    response = client.get("/api/v1/videos?per_page=3&limit=3")
    assert response.status_code == 400
    data = response.get_json()
    assert "mutually exclusive" in data["error"]


# ---------- _make_param_conflict_error helper ----------


def test_make_param_conflict_error_shape(app):
    """Verify _make_param_conflict_error returns 400 with a clear error body.

    Unit-style test for the helper that powers the mutual-exclusivity
    responses. It must return the canonical (response, 400) tuple and
    the JSON body must include both parameter names so clients can
    pinpoint the conflict without parsing the message string.
    """
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
    """Verify ?page=99999 is rejected with 400 to prevent unbounded OFFSET scans.

    Regression for Bottube #1414 follow-up: pre-fix, ?page=99999 silently
    triggered a SQLite OFFSET scan that returned empty pages and wasted
    CPU. The fix caps `page` at 10000 (well above the catalogue size)
    and 400s anything above that. This test pins the message to mention
    'page' and '<= 10000' so clients can show the precise reason.
    """
    response = client.get("/api/videos?page=99999")
    assert response.status_code == 400
    data = response.get_json()
    assert "page" in data["error"]
    assert "<= 10000" in data["error"]


def test_list_videos_page_accepts_max_boundary(client):
    """Verify ?page=10000 (the cap) is accepted and clamped server-side.

    Boundary test: the inclusive upper bound must 200 (not 400) and the
    returned page field must be in [1, 10000]. The actual value may be
    lower when the catalogue is shorter than 10000 pages, but it must
    never be 99999 (which is what an uncapped response would echo back).
    """
    response = client.get("/api/videos?page=10000")
    assert response.status_code == 200
    data = response.get_json()
    # The actual returned `page` may be even lower when the catalogue is
    # shorter than 10000 pages, but it must be a positive integer and
    # not 99999.
    assert isinstance(data["page"], int)
    assert 1 <= data["page"] <= 10000


def test_list_videos_page_rejects_just_above_max(client):
    """Verify ?page=10001 is rejected (off-by-one around the cap).

    Off-by-one guard mirroring the limit-alias test above: page=10001
    must 400 so a client using <= comparison instead of < is caught.
    """
    response = client.get("/api/videos?page=10001")
    assert response.status_code == 400
    data = response.get_json()
    assert "page" in data["error"]


def test_list_videos_v1_alias_page_rejects_over_max(client):
    """Verify /api/v1/videos inherits the new page cap.

    The /v1 alias must apply the same upper bound as the canonical
    route, otherwise a client could bypass the cap by switching to
    /v1 paths.
    """
    response = client.get("/api/v1/videos?page=99999")
    assert response.status_code == 400
    data = response.get_json()
    assert "page" in data["error"]