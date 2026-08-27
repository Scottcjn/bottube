# SPDX-License-Identifier: MIT
def _auth_headers(api_key):
    return {"X-API-Key": api_key}


def _assert_json_object_required(resp):
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}


def test_authenticated_utility_routes_reject_non_object_json(client, registered_agent):
    """Verify authenticated utility routes reject non-object JSON bodies.

    Four authenticated POST/PUT endpoints (notifications/read, webhooks,
    agents/me/wallet, notifications/preferences) share the same JSON-body
    validation contract: the body must be a JSON object. Sending a JSON
    array must 400 with the canonical 'JSON body must be an object' error
    on every endpoint, so client SDKs can centralize the validation
    message rather than branching per route.
    """
    headers = _auth_headers(registered_agent["api_key"])

    cases = [
        ("post", "/api/agents/me/notifications/read", ["bad"]),
        ("post", "/api/webhooks", ["bad"]),
        ("post", "/api/agents/me/wallet", ["rtc_wallet"]),
        ("put", "/api/notifications/preferences", ["comments"]),
    ]

    for method, path, payload in cases:
        resp = getattr(client, method)(path, headers=headers, json=payload)
        _assert_json_object_required(resp)


def test_playlist_routes_reject_non_object_json(client, registered_agent):
    """Verify playlist create/update/add-item routes reject non-object JSON.

    The three playlist endpoints (POST /api/playlists, PATCH
    /api/playlists/{id}, POST /api/playlists/{id}/items) must all reject
    non-object JSON bodies with the canonical 400 error. The test first
    creates a valid playlist (to obtain a real playlist_id) and then
    runs the bad-shape requests against the update and add-item routes
    so the validation is exercised on real, existing resources.
    """
    headers = _auth_headers(registered_agent["api_key"])

    create_bad = client.post("/api/playlists", headers=headers, json=["bad"])
    _assert_json_object_required(create_bad)

    create_ok = client.post(
        "/api/playlists",
        headers=headers,
        json={"title": "Validation Mix"},
    )
    assert create_ok.status_code == 201
    playlist_id = create_ok.get_json()["playlist_id"]

    update_bad = client.patch(
        f"/api/playlists/{playlist_id}",
        headers=headers,
        json=["title"],
    )
    _assert_json_object_required(update_bad)

    add_bad = client.post(
        f"/api/playlists/{playlist_id}/items",
        headers=headers,
        json=["video_id"],
    )
    _assert_json_object_required(add_bad)
