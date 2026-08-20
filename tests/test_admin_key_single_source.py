# SPDX-License-Identifier: MIT
"""The two admin gates must resolve the same secret.

`bottube_server` has two independent admin checks:

* `_require_admin()` (24 call sites) compared against the module constant
  `ADMIN_KEY`, which was read from **BOTTUBE_ADMIN_KEY only**.
* `_ts_admin_ok()` (15 trust-and-safety call sites, including the
  `/admin/blocklist/add` hash blocklist) read
  **BOTTUBE_ADMIN_KEY or RC_ADMIN_KEY**.

So an operator who configured only `RC_ADMIN_KEY` got a split brain: the
trust-and-safety endpoints accepted their key while all 24 `_require_admin`
endpoints rejected it — and because an unset `BOTTUBE_ADMIN_KEY` makes the
module fall back to `secrets.token_hex(32)`, those endpoints would only
accept a random ephemeral key printed once at boot.

Both gates now resolve through `_admin_key_from_env()`.
"""

import importlib

import pytest


@pytest.fixture()
def server(app):
    """The already-imported bottube_server module (app fixture builds it)."""
    import bottube_server

    return bottube_server


@pytest.mark.parametrize(
    "env, expected",
    [
        ({"BOTTUBE_ADMIN_KEY": "primary"}, "primary"),
        ({"RC_ADMIN_KEY": "alias"}, "alias"),
        ({"BOTTUBE_ADMIN_KEY": "primary", "RC_ADMIN_KEY": "alias"}, "primary"),
        ({}, ""),
    ],
    ids=["primary-only", "alias-only", "both-primary-wins", "neither"],
)
def test_admin_key_resolution(server, monkeypatch, env, expected):
    monkeypatch.delenv("BOTTUBE_ADMIN_KEY", raising=False)
    monkeypatch.delenv("RC_ADMIN_KEY", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    assert server._admin_key_from_env() == expected


def test_both_gates_agree_on_the_alias(server, monkeypatch, app):
    """RC_ADMIN_KEY alone must open both gates, not just the T&S one."""
    monkeypatch.delenv("BOTTUBE_ADMIN_KEY", raising=False)
    monkeypatch.setenv("RC_ADMIN_KEY", "alias-secret")
    monkeypatch.setattr(server, "ADMIN_KEY", server._admin_key_from_env())

    with app.test_request_context(
        "/admin/moderation/reports", headers={"X-Admin-Key": "alias-secret"}
    ):
        assert server._ts_admin_ok() is True
        assert server._require_admin() is None  # None == allowed


def test_both_gates_reject_a_wrong_key(server, monkeypatch, app):
    monkeypatch.delenv("BOTTUBE_ADMIN_KEY", raising=False)
    monkeypatch.setenv("RC_ADMIN_KEY", "alias-secret")
    monkeypatch.setattr(server, "ADMIN_KEY", server._admin_key_from_env())

    with app.test_request_context(
        "/admin/moderation/reports", headers={"X-Admin-Key": "nope"}
    ):
        assert server._ts_admin_ok() is False
        assert server._require_admin() is not None


def test_ts_gate_fails_closed_without_any_env(server, monkeypatch, app):
    monkeypatch.delenv("BOTTUBE_ADMIN_KEY", raising=False)
    monkeypatch.delenv("RC_ADMIN_KEY", raising=False)

    with app.test_request_context(
        "/admin/moderation/reports", headers={"X-Admin-Key": ""}
    ):
        assert server._ts_admin_ok() is False
