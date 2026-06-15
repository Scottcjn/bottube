# SPDX-License-Identifier: MIT
"""Regression tests for non-object JSON bodies on the agent referral routes.

Before the fix, ``POST /api/agents/me/referral`` and
``POST /api/agents/me/referral/apply`` did ``request.get_json(silent=True) or
request.form.to_dict() or {}`` and then called ``.get()`` on the result.  A
valid-but-non-object JSON body (a list, string or number is truthy) flowed
straight through the ``or`` and raised ``AttributeError`` on ``.get()`` —
returning HTTP 500 instead of a deterministic 400.
"""


def _auth_headers(api_key):
    return {"X-API-Key": api_key}


def _assert_json_object_required(resp):
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert resp.get_json() == {"error": "JSON body must be an object"}


def test_referral_me_rejects_non_object_json(client, registered_agent):
    headers = _auth_headers(registered_agent["api_key"])

    for payload in (["bad"], "bad", 5, True):
        resp = client.post("/api/agents/me/referral", headers=headers, json=payload)
        _assert_json_object_required(resp)


def test_referral_apply_rejects_non_object_json(client, registered_agent):
    headers = _auth_headers(registered_agent["api_key"])

    for payload in (["bad"], "bad", 5):
        resp = client.post(
            "/api/agents/me/referral/apply", headers=headers, json=payload
        )
        _assert_json_object_required(resp)


def test_referral_me_get_still_works(client, registered_agent):
    headers = _auth_headers(registered_agent["api_key"])
    resp = client.get("/api/agents/me/referral", headers=headers)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("ok") is True
    assert body.get("code")


def test_referral_me_empty_object_still_works(client, registered_agent):
    headers = _auth_headers(registered_agent["api_key"])
    resp = client.post("/api/agents/me/referral", headers=headers, json={})
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True


def test_referral_apply_missing_code_returns_400(client, registered_agent):
    """A valid object body without ref_code keeps the original 400 contract."""
    headers = _auth_headers(registered_agent["api_key"])
    resp = client.post("/api/agents/me/referral/apply", headers=headers, json={})
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "ref_code is required"}
