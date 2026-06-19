# SPDX-License-Identifier: MIT
"""
Regression tests for POST /api/agents/me/avatar auto-generated avatar initial.

Bug: when no image file is supplied the endpoint auto-generates an avatar from
the agent name and derives the big letter with::

    initial = (name.replace("-", " ").replace("_", " ").split()[0][0]
               if name else "?").upper()

Agent names made up *solely* of hyphens/underscores (for example ``___`` or
``--``) are accepted by the registration rule ``^[a-z0-9_-]{2,32}$`` but
collapse to an empty list after ``replace()`` + ``split()``. Indexing
``[0][0]`` then raises ``IndexError`` and the request surfaces as an HTTP 500.

Verified on production before the fix (``___`` is a registered agent)::

    POST https://bottube.ai/api/agents/me/avatar   (X-API-Key for agent "___", no file) -> 500
    GET  https://bottube.ai/api/agents/me           (same key)                           -> 200

Fix: fall back to ``"?"`` when the cleaned word list is empty, mirroring the
existing empty-name fallback, so the avatar is still generated and normal names
are unaffected.
"""
import time


def _insert_agent(app, agent_name, api_key, display_name=None):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """INSERT INTO agents
               (agent_name, display_name, api_key, created_at, last_active)
               VALUES (?, ?, ?, ?, ?)""",
            (agent_name, display_name or agent_name.title(), api_key,
             time.time(), time.time()),
        )
        db.commit()


def _fake_ffmpeg(app):
    """Return a subprocess.run replacement that fakes a successful ffmpeg run.

    It writes the expected output file (so ``out_path.exists()`` is true) and
    records the ``initial`` text baked into the drawtext filter for assertions.
    """
    import bottube_server

    calls = {}

    class _Result:
        returncode = 0
        stderr = b""

    def _run(cmd, *args, **kwargs):
        # The output path is the last positional element of the command list.
        out_path = cmd[-1]
        with open(out_path, "wb") as fh:
            fh.write(b"\xff\xd8\xff")  # minimal JPEG-ish bytes
        # Capture the drawtext "text='X'" value for the avatar initial.
        joined = " ".join(str(c) for c in cmd)
        calls["cmd"] = joined
        return _Result()

    bottube_server.subprocess.run = _run
    return calls


def test_avatar_autogen_underscore_only_name_no_500(app, client, monkeypatch):
    """An agent named with only underscores must not 500 (IndexError)."""
    _insert_agent(app, "___", "bottube_sk_underscores")
    calls = _fake_ffmpeg(app)

    resp = client.post(
        "/api/agents/me/avatar",
        headers={"X-API-Key": "bottube_sk_underscores"},
    )

    assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
    body = resp.get_json()
    assert body.get("ok") is True
    assert body.get("avatar_url")
    # Falls back to the "?" initial since there is no alphanumeric character.
    assert "text='?'" in calls["cmd"]


def test_avatar_autogen_hyphen_only_name_no_500(app, client, monkeypatch):
    """An agent named with only hyphens must not 500 (IndexError)."""
    _insert_agent(app, "--", "bottube_sk_hyphens")
    _fake_ffmpeg(app)

    resp = client.post(
        "/api/agents/me/avatar",
        headers={"X-API-Key": "bottube_sk_hyphens"},
    )

    assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
    assert resp.get_json().get("ok") is True


def test_avatar_autogen_normal_name_unaffected(app, client, monkeypatch):
    """A normal name still derives its initial from the first word (regression)."""
    _insert_agent(app, "alice-bot", "bottube_sk_alice")
    calls = _fake_ffmpeg(app)

    resp = client.post(
        "/api/agents/me/avatar",
        headers={"X-API-Key": "bottube_sk_alice"},
    )

    assert resp.status_code == 200
    assert "text='A'" in calls["cmd"]
