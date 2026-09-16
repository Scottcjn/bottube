# SPDX-License-Identifier: MIT
"""Upload moderation regression tests for BoTTube.

Pins the moderation pipeline on BOTH upload surfaces so it cannot silently
regress:

    POST /api/upload   (agent API, X-API-Key)
    POST /upload       (web form, logged-in human session + CSRF)

For each surface we assert five behaviours:

1. Metadata blocklist — a blocked term in title / description / tags is
   rejected: no ``videos`` row, no RTC, no search-engine ping, a coaching
   hold is queued.
2. Hash check FAIL-CLOSED — if ``ts_inspect_uploaded_file`` raises, the
   upload is NOT published and no RTC is paid.
3. Hash match — a file whose SHA-256 is on ``content_blocklist`` is
   rejected (451), quarantined, the uploader is suspended, no RTC.
4. Vision screen "failed" — the row is inserted with ``is_removed = 1``,
   ``award_rtc`` is NOT called for the upload, and neither IndexNow nor
   Google Indexing is pinged.
5. Clean upload — published with ``is_removed = 0``, RTC awarded exactly
   once for ``video_upload``, search engines pinged once.

Everything external is stubbed (ffmpeg/ffprobe helpers, vision screener,
IndexNow, Google Indexing, captions, provenance, renditions, embeddings,
subscriber fan-out, Banano). ``award_rtc`` is wrapped in a spy that still
performs the real ledger write so both the call count and the ``earnings``
table can be asserted.

Run:
    python3 -m pytest tests/test_upload_moderation.py -q
"""

import hashlib
import io
import shutil
import sqlite3
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Bytes that look enough like an MP4 for extension/save logic. ffmpeg is
# never invoked because the media helpers are stubbed in ``hermetic``.
FAKE_VIDEO = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isomiso2mp41" + (b"bottube-test-frame-" * 64)
FAKE_VIDEO_SHA256 = hashlib.sha256(FAKE_VIDEO).hexdigest()

BLOCKED_TERM = "beheading"  # present in bottube_server._CONTENT_BLOCKLIST
CSRF = "test-csrf"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def srv(app):
    """The freshly imported ``bottube_server`` module behind the ``app`` fixture.

    ``tests/conftest.py`` re-imports the server for every test, so a
    module-level ``import bottube_server`` would be stale. Always go through
    ``sys.modules`` after the ``app`` fixture has run.
    """
    return sys.modules["bottube_server"]


@pytest.fixture
def hermetic(srv, monkeypatch):
    """Stub every external side effect of the two upload handlers."""

    # --- media pipeline (ffmpeg / ffprobe) --------------------------------
    def fake_transcode(input_path, output_path, *args, **kwargs):
        shutil.copyfile(str(input_path), str(output_path))
        return True

    monkeypatch.setattr(srv, "get_video_metadata", lambda path: (2.0, 320, 240))
    monkeypatch.setattr(srv, "transcode_video", fake_transcode)
    monkeypatch.setattr(srv, "generate_thumbnail", lambda video_path, thumb_path: False)

    # --- RTC award: spy that still performs the real ledger write ----------
    real_award_rtc = srv.award_rtc
    award_spy = MagicMock(side_effect=real_award_rtc)
    monkeypatch.setattr(srv, "award_rtc", award_spy)

    # --- search-engine pings ----------------------------------------------
    indexnow = MagicMock(name="_ping_indexnow")
    google = MagicMock(name="ping_google_indexing")
    monkeypatch.setattr(srv, "_ping_indexnow", indexnow)
    monkeypatch.setattr(srv, "ping_google_indexing", google)

    # --- vision screener (default: clean) ---------------------------------
    screen = MagicMock(
        name="screen_video",
        return_value={"status": "passed", "tier_reached": 1, "summary": "clean"},
    )
    monkeypatch.setattr(srv, "screen_video", screen)

    # --- background workers / fan-out that would spawn threads ------------
    for name in (
        "_notify_subscribers_new_video",
        "generate_captions_async",
        "_provenance_record_for_upload",
        "_renditions_process_video_async",
        "_ue_record_for_video_async",
    ):
        monkeypatch.setattr(srv, name, MagicMock(name=name))

    # --- Banano rewards (separate ledger, not under test) -----------------
    monkeypatch.setattr(srv, "award_ban_upload", MagicMock(name="award_ban_upload"))
    monkeypatch.setattr(srv, "award_ban_video_gen", MagicMock(name="award_ban_video_gen", return_value=0.0))

    return SimpleNamespace(
        award_rtc=award_spy,
        indexnow=indexnow,
        google=google,
        screen=screen,
    )


@pytest.fixture
def api_agent(srv, client, registered_agent):
    """Registered agent plus its numeric id."""
    with srv.app.app_context():
        row = srv.get_db().execute(
            "SELECT id FROM agents WHERE agent_name = ?", (registered_agent["agent_name"],)
        ).fetchone()
    return SimpleNamespace(
        id=int(row["id"]),
        name=registered_agent["agent_name"],
        api_key=registered_agent["api_key"],
    )


@pytest.fixture
def web_user(srv, client):
    """A logged-in human account (session cookie + CSRF token) for /upload."""
    with srv.app.app_context():
        db = srv.get_db()
        cur = db.execute(
            """INSERT INTO agents
                   (agent_name, display_name, api_key, bio, avatar_url, is_human, created_at, last_active)
               VALUES (?, ?, ?, '', '', 1, ?, ?)""",
            ("web_upload_human", "Web Upload Human", "bottube_sk_web_upload_human", time.time(), time.time()),
        )
        db.commit()
        user_id = int(cur.lastrowid)

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = CSRF

    return SimpleNamespace(id=user_id, name="web_upload_human")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _connect(srv):
    conn = sqlite3.connect(str(srv.DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _videos_for(srv, agent_id):
    with _connect(srv) as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM videos WHERE agent_id = ?", (agent_id,)
        ).fetchall()]


def _earnings_for(srv, agent_id, reason="video_upload"):
    with _connect(srv) as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM earnings WHERE agent_id = ? AND reason = ?", (agent_id, reason)
        ).fetchall()]


def _holds(srv, source):
    with _connect(srv) as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM moderation_holds WHERE source = ?", (source,)
        ).fetchall()]


def _agent(srv, agent_id):
    with _connect(srv) as conn:
        return dict(conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone())


def _upload_award_calls(mocks):
    """award_rtc calls whose reason is the upload reward (ignores quest rewards)."""
    return [c for c in mocks.award_rtc.call_args_list if c.args[3] == "video_upload"]


def _published_files(srv):
    return sorted(p.name for p in srv.VIDEO_DIR.iterdir() if p.is_file())


def _blocklist_hash(srv, sha256_hex, category="csam"):
    with srv.app.app_context():
        srv._ensure_ts_schema()
    with _connect(srv) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO content_blocklist
                   (hash_sha256, hash_kind, category, source, notes, added_by, added_at)
               VALUES (?, 'file', ?, 'internal', 'test fixture', 'pytest', ?)""",
            (sha256_hex, category, time.time()),
        )
        conn.commit()


def _api_upload(client, api_key, *, data=FAKE_VIDEO, filename="clip.mp4", **form):
    payload = {"video": (io.BytesIO(data), filename), "title": "Moderation test clip"}
    payload.update(form)
    return client.post(
        "/api/upload",
        headers={"X-API-Key": api_key},
        content_type="multipart/form-data",
        data=payload,
    )


def _web_upload(client, *, data=FAKE_VIDEO, filename="clip.mp4", **form):
    payload = {
        "video": (io.BytesIO(data), filename),
        "title": "Moderation test clip",
        "csrf_token": CSRF,
    }
    payload.update(form)
    return client.post("/upload", content_type="multipart/form-data", data=payload)


def _assert_nothing_published(srv, mocks, agent_id):
    """Shared 'rejected' contract: no public row, no RTC, no ping."""
    rows = _videos_for(srv, agent_id)
    published = [r for r in rows if not r.get("is_removed")]
    assert published == [], f"video was published: {published}"
    assert _earnings_for(srv, agent_id) == [], "video_upload RTC was paid"
    assert _upload_award_calls(mocks) == [], "award_rtc(video_upload) was called"
    mocks.indexnow.assert_not_called()
    mocks.google.assert_not_called()


def _assert_web_not_redirected_to_watch(resp):
    assert not (resp.status_code in (301, 302, 303, 307, 308)
                and "/watch/" in resp.headers.get("Location", "")), \
        f"web upload redirected to a watch page: {resp.headers.get('Location')}"


# ===========================================================================
# POST /api/upload
# ===========================================================================

class TestApiUploadModeration:

    # 1. Metadata blocklist ---------------------------------------------------

    @pytest.mark.parametrize("field", ["title", "description", "tags"])
    def test_api_upload_rejects_blocklisted_metadata(self, srv, client, hermetic, api_agent, field):
        value = f"totally normal {BLOCKED_TERM} clip" if field != "tags" else f"fun,{BLOCKED_TERM},ai"
        resp = _api_upload(client, api_agent.api_key, **{field: value})

        assert resp.status_code == 422, resp.get_data(as_text=True)
        body = resp.get_json()
        assert body["code"] == "CONTENT_POLICY_VIOLATION"

        _assert_nothing_published(srv, hermetic, api_agent.id)
        assert _videos_for(srv, api_agent.id) == [], "a videos row was inserted"
        assert _published_files(srv) == [], "file was written to VIDEO_DIR"
        hermetic.screen.assert_not_called()

        holds = _holds(srv, "upload_blocklist")
        assert len(holds) == 1
        assert holds[0]["target_agent_id"] == api_agent.id
        assert BLOCKED_TERM in holds[0]["details"]

    # 2. Hash check must FAIL CLOSED ------------------------------------------

    def test_api_upload_hash_check_error_is_fail_closed(self, srv, client, hermetic, api_agent, monkeypatch):
        def boom(file_path, agent_id):
            raise RuntimeError("hash service unavailable")

        monkeypatch.setattr(srv, "ts_inspect_uploaded_file", boom)
        resp = _api_upload(client, api_agent.api_key)

        assert resp.status_code >= 400, (
            f"hash-check exception was swallowed and the upload was accepted "
            f"(HTTP {resp.status_code}): {resp.get_data(as_text=True)[:200]}"
        )
        _assert_nothing_published(srv, hermetic, api_agent.id)
        hermetic.screen.assert_not_called()

    # 3. Blocklisted hash -------------------------------------------------------

    def test_api_upload_rejects_blocklisted_hash(self, srv, client, hermetic, api_agent):
        _blocklist_hash(srv, FAKE_VIDEO_SHA256, category="csam")
        resp = _api_upload(client, api_agent.api_key)

        assert resp.status_code == 451, resp.get_data(as_text=True)
        assert resp.get_json()["category"] == "csam"

        _assert_nothing_published(srv, hermetic, api_agent.id)
        assert _videos_for(srv, api_agent.id) == []
        hermetic.screen.assert_not_called()

        # File is quarantined (moved out of VIDEO_DIR), uploader suspended.
        assert _published_files(srv) == []
        quarantined = list(srv.QUARANTINE_DIR.glob("csam_*.bin"))
        assert len(quarantined) == 1
        assert quarantined[0].read_bytes() == FAKE_VIDEO
        assert _agent(srv, api_agent.id)["is_suspended"] == 1

    # 4. Vision screen "failed" -------------------------------------------------

    @pytest.fixture
    def held_api_upload(self, srv, client, hermetic, api_agent):
        hermetic.screen.return_value = {
            "status": "failed", "tier_reached": 2, "summary": "nsfw frames detected",
        }
        resp = _api_upload(client, api_agent.api_key)
        return SimpleNamespace(resp=resp, agent=api_agent)

    def test_api_upload_vision_hold_marks_video_removed(self, srv, client, hermetic, held_api_upload):
        resp = held_api_upload.resp
        agent = held_api_upload.agent
        hermetic.screen.assert_called_once()

        rows = _videos_for(srv, agent.id)
        assert len(rows) == 1
        row = rows[0]
        assert row["is_removed"] == 1
        assert row["screening_status"] == "failed"
        assert row["removed_reason"].startswith("held_for_review")

        holds = _holds(srv, "vision_screening")
        assert len(holds) == 1 and holds[0]["target_ref"] == row["video_id"]

        # Held video is not publicly listed.
        listed = [v["video_id"] for v in client.get("/api/videos").get_json()["videos"]]
        assert row["video_id"] not in listed
        if resp.status_code == 201:
            assert resp.get_json()["screening"]["status"] == "failed"

    def test_api_upload_vision_hold_does_not_award_rtc(self, srv, hermetic, held_api_upload):
        agent = held_api_upload.agent
        assert _upload_award_calls(hermetic) == [], "award_rtc(video_upload) called for a held video"
        assert _earnings_for(srv, agent.id) == [], "video_upload RTC paid for a held video"

    def test_api_upload_vision_hold_does_not_ping_search_engines(self, hermetic, held_api_upload):
        hermetic.indexnow.assert_not_called()
        hermetic.google.assert_not_called()

    # 5. Clean upload -------------------------------------------------------------

    def test_api_upload_clean_publishes_and_awards_rtc_once(self, srv, client, hermetic, api_agent):
        resp = _api_upload(client, api_agent.api_key, description="a wholesome clip", tags="ai,art")

        assert resp.status_code == 201, resp.get_data(as_text=True)
        body = resp.get_json()
        video_id = body["video_id"]
        assert body["screening"]["status"] == "passed"
        hermetic.screen.assert_called_once()

        rows = _videos_for(srv, api_agent.id)
        assert len(rows) == 1
        assert rows[0]["video_id"] == video_id
        assert rows[0]["is_removed"] == 0
        assert rows[0]["screening_status"] == "passed"
        assert (srv.VIDEO_DIR / rows[0]["filename"]).exists()

        upload_calls = _upload_award_calls(hermetic)
        assert len(upload_calls) == 1
        assert upload_calls[0].args[1] == api_agent.id
        assert upload_calls[0].args[2] == srv.RTC_REWARD_UPLOAD
        assert upload_calls[0].args[4] == video_id

        earnings = _earnings_for(srv, api_agent.id)
        assert len(earnings) == 1
        assert earnings[0]["video_id"] == video_id
        assert earnings[0]["amount"] >= srv.RTC_REWARD_UPLOAD
        assert _agent(srv, api_agent.id)["rtc_balance"] >= srv.RTC_REWARD_UPLOAD

        hermetic.indexnow.assert_called_once_with(f"https://bottube.ai/watch/{video_id}")
        hermetic.google.assert_called_once_with(f"https://bottube.ai/watch/{video_id}")

        listed = [v["video_id"] for v in client.get("/api/videos").get_json()["videos"]]
        assert video_id in listed


# ===========================================================================
# POST /upload (web form, logged-in human)
# ===========================================================================

class TestWebUploadModeration:

    # 1. Metadata blocklist ---------------------------------------------------

    @pytest.mark.parametrize("field", ["title", "description", "tags"])
    def test_web_upload_rejects_blocklisted_metadata(self, srv, client, hermetic, web_user, field):
        value = f"totally normal {BLOCKED_TERM} clip" if field != "tags" else f"fun,{BLOCKED_TERM},ai"
        resp = _web_upload(client, **{field: value})

        _assert_web_not_redirected_to_watch(resp)
        _assert_nothing_published(srv, hermetic, web_user.id)
        assert _videos_for(srv, web_user.id) == [], "a videos row was inserted"
        assert _published_files(srv) == [], "file was written to VIDEO_DIR"
        hermetic.screen.assert_not_called()

        holds = _holds(srv, "upload_blocklist")
        assert len(holds) == 1
        assert holds[0]["target_agent_id"] == web_user.id
        assert BLOCKED_TERM in holds[0]["details"]

    # 2. Hash check must FAIL CLOSED ------------------------------------------

    def test_web_upload_hash_check_error_is_fail_closed(self, srv, client, hermetic, web_user, monkeypatch):
        def boom(file_path, agent_id):
            raise RuntimeError("hash service unavailable")

        monkeypatch.setattr(srv, "ts_inspect_uploaded_file", boom)
        resp = _web_upload(client)

        _assert_web_not_redirected_to_watch(resp)
        assert resp.status_code >= 400, (
            f"hash-check exception did not reject the web upload (HTTP {resp.status_code})"
        )
        _assert_nothing_published(srv, hermetic, web_user.id)
        assert _published_files(srv) == [], "unscreened file left in VIDEO_DIR"
        hermetic.screen.assert_not_called()

    # 3. Blocklisted hash -------------------------------------------------------

    def test_web_upload_rejects_blocklisted_hash(self, srv, client, hermetic, web_user):
        _blocklist_hash(srv, FAKE_VIDEO_SHA256, category="csam")
        resp = _web_upload(client)

        _assert_web_not_redirected_to_watch(resp)
        assert resp.status_code == 451, resp.get_data(as_text=True)[:300]
        _assert_nothing_published(srv, hermetic, web_user.id)
        assert _videos_for(srv, web_user.id) == []
        hermetic.screen.assert_not_called()

        assert _published_files(srv) == []
        quarantined = list(srv.QUARANTINE_DIR.glob("csam_*.bin"))
        assert len(quarantined) == 1
        assert quarantined[0].read_bytes() == FAKE_VIDEO
        assert _agent(srv, web_user.id)["is_suspended"] == 1

    # 4. Vision screen "failed" -------------------------------------------------

    @pytest.fixture
    def held_web_upload(self, srv, client, hermetic, web_user):
        hermetic.screen.return_value = {
            "status": "failed", "tier_reached": 2, "summary": "nsfw frames detected",
        }
        resp = _web_upload(client)
        return SimpleNamespace(resp=resp, user=web_user)

    def test_web_upload_vision_hold_marks_video_removed(self, srv, client, hermetic, held_web_upload):
        resp = held_web_upload.resp
        user = held_web_upload.user
        hermetic.screen.assert_called_once()
        _assert_web_not_redirected_to_watch(resp)

        rows = _videos_for(srv, user.id)
        assert len(rows) == 1
        row = rows[0]
        assert row["is_removed"] == 1
        assert row["screening_status"] == "failed"
        assert row["removed_reason"].startswith("held_for_review")

        holds = _holds(srv, "vision_screening")
        assert len(holds) == 1 and holds[0]["target_ref"] == row["video_id"]

        listed = [v["video_id"] for v in client.get("/api/videos").get_json()["videos"]]
        assert row["video_id"] not in listed

    def test_web_upload_vision_hold_does_not_award_rtc(self, srv, hermetic, held_web_upload):
        user = held_web_upload.user
        assert _upload_award_calls(hermetic) == [], "award_rtc(video_upload) called for a held video"
        assert _earnings_for(srv, user.id) == [], "video_upload RTC paid for a held video"

    def test_web_upload_vision_hold_does_not_ping_search_engines(self, hermetic, held_web_upload):
        hermetic.indexnow.assert_not_called()
        hermetic.google.assert_not_called()

    # 5. Clean upload -------------------------------------------------------------

    def test_web_upload_clean_publishes_and_awards_rtc_once(self, srv, client, hermetic, web_user):
        resp = _web_upload(client, description="a wholesome clip", tags="ai,art")

        assert resp.status_code in (302, 303), resp.get_data(as_text=True)[:300]
        location = resp.headers["Location"]
        assert "/watch/" in location
        video_id = location.rsplit("/watch/", 1)[1].split("?")[0]
        hermetic.screen.assert_called_once()

        rows = _videos_for(srv, web_user.id)
        assert len(rows) == 1
        assert rows[0]["video_id"] == video_id
        assert rows[0]["is_removed"] == 0
        assert (srv.VIDEO_DIR / rows[0]["filename"]).exists()

        upload_calls = _upload_award_calls(hermetic)
        assert len(upload_calls) == 1
        assert upload_calls[0].args[1] == web_user.id
        assert upload_calls[0].args[2] == srv.RTC_REWARD_UPLOAD
        assert upload_calls[0].args[4] == video_id

        earnings = _earnings_for(srv, web_user.id)
        assert len(earnings) == 1
        assert earnings[0]["video_id"] == video_id
        assert earnings[0]["amount"] >= srv.RTC_REWARD_UPLOAD
        assert _agent(srv, web_user.id)["rtc_balance"] >= srv.RTC_REWARD_UPLOAD

        hermetic.indexnow.assert_called_once_with(f"https://bottube.ai/watch/{video_id}")
        hermetic.google.assert_called_once_with(f"https://bottube.ai/watch/{video_id}")

        listed = [v["video_id"] for v in client.get("/api/videos").get_json()["videos"]]
        assert video_id in listed
