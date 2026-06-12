# SPDX-License-Identifier: MIT
"""
Tests for Bounty #2161: Creator Collaboration Features (Issue #427)
Tests the split-tip logic on co-uploaded videos.

The conftest re-imports the `bottube_server` module per test to reset
DB_PATH, so we cannot cache it as a top-level name. We resolve the live
module from `sys.modules` on every helper call.
"""
import json
import sqlite3
import sys
import time

import pytest


def _live():
    """Return the live bottube_server module the conftest is using right now."""
    for mod in list(sys.modules.values()):
        if mod is not None and mod.__name__ == "bottube_server":
            return mod
    raise RuntimeError("bottube_server not in sys.modules")


def _conn():
    import os
    server = _live()
    path = str(server.DB_PATH)
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    return sqlite3.connect(path)


def _register(app, name):
    server = _live()
    client = app.test_client()
    resp = client.post(
        "/api/register",
        json={"agent_name": name, "display_name": name.title()},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["api_key"]


def _accept_terms(app, name):
    server = _live()
    api_key = _register(app, name)
    client = app.test_client()
    tos_resp = client.post(
        "/api/agents/me/accept-terms",
        json={"version": server.TOS_VERSION},
        headers={"X-API-Key": api_key},
    )
    assert tos_resp.status_code == 200, tos_resp.get_json()
    return api_key


def _set_balance(name, balance):
    conn = _conn()
    conn.execute(
        "UPDATE agents SET rtc_balance = ? WHERE agent_name = ?",
        (balance, name),
    )
    conn.commit()
    conn.close()


def _get_balance(name):
    conn = _conn()
    row = conn.execute(
        "SELECT rtc_balance FROM agents WHERE agent_name = ?", (name,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _get_id(name):
    conn = _conn()
    row = conn.execute(
        "SELECT id FROM agents WHERE agent_name = ?", (name,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _insert_video_with_collabs(owner_name, collaborator_names, video_id):
    owner_id = _get_id(owner_name)
    collab_ids = [_get_id(n) for n in collaborator_names]
    conn = _conn()
    conn.execute(
        """INSERT INTO videos
           (video_id, agent_id, title, filename, description, created_at, collaborator_ids)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            video_id,
            owner_id,
            "Co-uploaded video",
            f"{video_id}.mp4",
            "Bounty #2161 test video",
            time.time(),
            json.dumps(collab_ids),
        ),
    )
    conn.commit()
    conn.close()


def _query(sql, params=()):
    conn = _conn()
    cur = conn.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows


class TestCollabTipSplit:
    """Bounty #2161: split-tip behavior on co-uploaded videos."""

    def test_tip_with_no_collaborators_full_to_primary(self, app, client):
        _accept_terms(app, "test_2161_p_nc")
        tipper_key = _accept_terms(app, "test_2161_t_nc")
        _set_balance("test_2161_p_nc", 0)
        _set_balance("test_2161_t_nc", 100)
        _insert_video_with_collabs("test_2161_p_nc", [], "vid_2161_nc")

        response = client.post(
            "/api/videos/vid_2161_nc/tip",
            json={"amount": 0.12, "message": "no split"},
            headers={"X-API-Key": tipper_key},
        )
        assert response.status_code == 200, response.get_json()
        assert _get_balance("test_2161_p_nc") == pytest.approx(0.12, abs=1e-6)
        assert _get_balance("test_2161_t_nc") == pytest.approx(99.88, abs=1e-6)

        tips = _query("SELECT to_agent_id, amount FROM tips WHERE video_id = ?", ("vid_2161_nc",))
        assert len(tips) == 1
        assert tips[0][1] == pytest.approx(0.12, abs=1e-6)

    def test_tip_with_two_collaborators_splits_evenly(self, app, client):
        _accept_terms(app, "test_2161_p_2c")
        _accept_terms(app, "test_2161_ca_2c")
        _accept_terms(app, "test_2161_cb_2c")
        tipper_key = _accept_terms(app, "test_2161_t_2c")
        _set_balance("test_2161_p_2c", 0)
        _set_balance("test_2161_t_2c", 100)
        _set_balance("test_2161_ca_2c", 0)
        _set_balance("test_2161_cb_2c", 0)
        _insert_video_with_collabs(
            "test_2161_p_2c", ["test_2161_ca_2c", "test_2161_cb_2c"], "vid_2161_2c"
        )

        response = client.post(
            "/api/videos/vid_2161_2c/tip",
            json={"amount": 0.12, "message": "split 3-way"},
            headers={"X-API-Key": tipper_key},
        )
        assert response.status_code == 200, response.get_json()

        # 0.12 / 3 = 0.04 each
        assert _get_balance("test_2161_p_2c") == pytest.approx(0.04, abs=1e-6)
        assert _get_balance("test_2161_ca_2c") == pytest.approx(0.04, abs=1e-6)
        assert _get_balance("test_2161_cb_2c") == pytest.approx(0.04, abs=1e-6)
        assert _get_balance("test_2161_t_2c") == pytest.approx(99.88, abs=1e-6)

        tips = _query("SELECT to_agent_id, amount FROM tips WHERE video_id = ? ORDER BY to_agent_id", ("vid_2161_2c",))
        assert len(tips) == 3
        assert all(t[1] == pytest.approx(0.04, abs=1e-6) for t in tips)

        earnings = _query("SELECT agent_id, amount, reason FROM earnings WHERE video_id = ?", ("vid_2161_2c",))
        assert len(earnings) == 3
        reasons = {e[0]: e[2] for e in earnings}
        assert reasons[_get_id("test_2161_p_2c")] == "tip_split_primary"
        assert reasons[_get_id("test_2161_ca_2c")] == "tip_split_collab"
        assert reasons[_get_id("test_2161_cb_2c")] == "tip_split_collab"

    def test_tip_rounding_diff_to_primary(self, app, client):
        _accept_terms(app, "test_2161_p_r")
        _accept_terms(app, "test_2161_ca_r")
        _accept_terms(app, "test_2161_cb_r")
        tipper_key = _accept_terms(app, "test_2161_t_r")
        _set_balance("test_2161_t_r", 100)
        _insert_video_with_collabs(
            "test_2161_p_r", ["test_2161_ca_r", "test_2161_cb_r"], "vid_2161_r"
        )

        response = client.post(
            "/api/videos/vid_2161_r/tip",
            json={"amount": 0.10, "message": "rounding test"},
            headers={"X-API-Key": tipper_key},
        )
        assert response.status_code == 200

        # 0.10 / 3 = 0.0333... per_share = 0.033333; diff = 0.10 - 0.099999 = 0.000001
        # primary gets per_share + diff = 0.033334, collabs get 0.033333
        assert _get_balance("test_2161_p_r") == pytest.approx(0.033334, abs=1e-6)
        assert _get_balance("test_2161_ca_r") == pytest.approx(0.033333, abs=1e-6)
        assert _get_balance("test_2161_cb_r") == pytest.approx(0.033333, abs=1e-6)
        total = (
            (_get_balance("test_2161_p_r") or 0)
            + (_get_balance("test_2161_ca_r") or 0)
            + (_get_balance("test_2161_cb_r") or 0)
        )
        assert total == pytest.approx(0.10, abs=1e-6)

    def test_self_in_collaborators_filtered_out(self, app, client):
        _accept_terms(app, "test_2161_p_s")
        _accept_terms(app, "test_2161_ca_s")
        tipper_key = _accept_terms(app, "test_2161_t_s")
        _set_balance("test_2161_t_s", 100)
        # Tipper registers themselves as a collaborator on the video
        _insert_video_with_collabs(
            "test_2161_p_s", ["test_2161_t_s", "test_2161_ca_s"], "vid_2161_s"
        )

        response = client.post(
            "/api/videos/vid_2161_s/tip",
            json={"amount": 0.10, "message": "self filter"},
            headers={"X-API-Key": tipper_key},
        )
        assert response.status_code == 200

        # 0.10 split between primary + collab_a only (tipper filtered)
        assert _get_balance("test_2161_p_s") == pytest.approx(0.05, abs=1e-6)
        assert _get_balance("test_2161_ca_s") == pytest.approx(0.05, abs=1e-6)
        assert _get_balance("test_2161_t_s") == pytest.approx(99.90, abs=1e-6)
        self_tips = _query("SELECT COUNT(*) AS n FROM tips WHERE to_agent_id = ?", (_get_id("test_2161_t_s"),))
        assert self_tips[0][0] == 0

    def test_insufficient_balance_no_partial_split(self, app, client):
        _accept_terms(app, "test_2161_p_ib")
        _accept_terms(app, "test_2161_ca_ib")
        tipper_key = _accept_terms(app, "test_2161_t_ib")
        _set_balance("test_2161_t_ib", 100)
        _insert_video_with_collabs(
            "test_2161_p_ib", ["test_2161_ca_ib"], "vid_2161_ib"
        )

        response = client.post(
            "/api/videos/vid_2161_ib/tip",
            json={"amount": 200, "message": "too big"},
            headers={"X-API-Key": tipper_key},
        )
        assert response.status_code == 400
        assert _query("SELECT COUNT(*) AS n FROM tips WHERE video_id = ?", ("vid_2161_ib",))[0][0] == 0
        assert _get_balance("test_2161_t_ib") == pytest.approx(100, abs=1e-6)
