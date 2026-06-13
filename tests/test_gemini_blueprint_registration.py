# SPDX-License-Identifier: MIT
"""Validation tests for Gemini blueprint registration in bottube_server.

Regression target: Bottube issue #1428 — `/api/gemini/status` and
`/api/transcript/search` returned 404 in production because the
`gemini_blueprint` module existed on disk but was never imported and
registered with the Flask app. The whisper blueprint had the same shape
and was already registered next to it; this test pins the gemini
blueprint into that same registration block.
"""

import importlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest


def _read_server_registration_block():
    """Pull the gemini registration try/except block out of bottube_server
    without booting the whole monolith (it has many side-effecting
    imports). We only need to confirm the wiring is present and shaped
    like the whisper block.
    """
    server_path = Path(__file__).resolve().parent.parent / "bottube_server.py"
    text = server_path.read_text()
    # Find the gemini registration marker we added
    marker = "# Gemini video/image generation API (Bounty #1102 fix for #1428)"
    assert marker in text, (
        "Expected the gemini blueprint registration block to be present "
        "in bottube_server.py — see Bottube issue #1428."
    )
    return text


def test_gemini_registration_block_present():
    text = _read_server_registration_block()
    assert "from gemini_blueprint import gemini_bp, init_gemini_tables" in text
    assert "app.register_blueprint(gemini_bp)" in text
    assert "init_gemini_tables()" in text
    assert "GEMINI_API_ENABLED = True" in text
    assert "GEMINI_API_ENABLED = False" in text


def test_gemini_registration_block_is_safe_under_missing_module(monkeypatch):
    """The block must be wrapped in try/except ImportError so a missing
    google-genai SDK does not crash the whole server boot, matching the
    pattern used by whisper_bp and the other deferred blueprints.
    """
    text = _read_server_registration_block()
    snippet = text.split("# Gemini video/image generation API (Bounty #1102 fix for #1428)", 1)[1]
    snippet = snippet.split("# ---------------------------------------------------------------------------", 2)[1]  # grab the body until the next divider
    assert "try:" in snippet
    assert "except ImportError:" in snippet
    assert "init_gemini_tables()" in snippet


def test_gemini_bp_blueprint_registers_routes_in_isolation(tmp_path):
    """In a minimal Flask app, registering gemini_bp should expose the
    status route, the transcript search route, and the rest of the
    gemini surfaces. This is a fast unit check that does not need the
    full server.
    """
    db_path = tmp_path / "gemini.db"
    os.environ["BOTTUBE_DB"] = str(db_path)

    from flask import Flask
    import gemini_blueprint
    import whisper_transcription_blueprint

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(gemini_blueprint.gemini_bp)
    app.register_blueprint(whisper_transcription_blueprint.whisper_bp)

    client = app.test_client()

    # Status route: must return JSON, not 404
    resp = client.get("/api/gemini/status")
    assert resp.status_code == 200, (
        f"/api/gemini/status should be registered; got HTTP {resp.status_code}"
    )
    body = resp.get_json()
    assert isinstance(body, dict)
    for key in ("available", "sdk_installed", "api_key_set", "video_model", "image_model", "limits"):
        assert key in body, f"status response missing key: {key}"

    # Transcript search route: must return JSON, not 404
    resp = client.get("/api/transcript/search?q=test")
    assert resp.status_code == 200, (
        f"/api/transcript/search should be registered; got HTTP {resp.status_code}"
    )
    body = resp.get_json()
    assert isinstance(body, dict)
    for key in ("query", "count", "video_ids"):
        assert key in body, f"transcript search response missing key: {key}"
