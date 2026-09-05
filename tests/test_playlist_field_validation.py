"""Regression coverage for playlist field types and enum values."""


def _headers(agent):
    return {"X-API-Key": agent["api_key"]}


def test_playlist_create_rejects_invalid_field_types(client, registered_agent):
    headers = _headers(registered_agent)
    invalid_payloads = (
        {"title": {"nested": "title"}},
        {"title": "Mix", "description": ["nested"]},
        {"title": "Mix", "visibility": "friends"},
        {"title": "Mix", "visibility": ["public"]},
    )

    for payload in invalid_payloads:
        response = client.post("/api/playlists", headers=headers, json=payload)
        assert response.status_code == 400, (payload, response.get_json())


def test_playlist_patch_rejects_invalid_fields_without_mutation(app, client, registered_agent):
    headers = _headers(registered_agent)
    created = client.post(
        "/api/playlists",
        headers=headers,
        json={"title": "Original", "description": "Original body", "visibility": "private"},
    )
    assert created.status_code == 201
    playlist_id = created.get_json()["playlist_id"]

    invalid_payloads = (
        {"title": {"nested": "title"}},
        {"description": ["nested"]},
        {"visibility": "friends"},
        {"visibility": ["public"]},
    )
    for payload in invalid_payloads:
        response = client.patch(f"/api/playlists/{playlist_id}", headers=headers, json=payload)
        assert response.status_code == 400, (payload, response.get_json())

    import bottube_server

    with app.app_context():
        row = bottube_server.get_db().execute(
            "SELECT title, description, visibility FROM playlists WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()
    assert row["title"] == "Original"
    assert row["description"] == "Original body"
    assert row["visibility"] == "private"

    valid = client.patch(
        f"/api/playlists/{playlist_id}",
        headers=headers,
        json={"title": "Updated", "description": "Updated body", "visibility": "unlisted"},
    )
    assert valid.status_code == 200
    with app.app_context():
        row = bottube_server.get_db().execute(
            "SELECT title, description, visibility FROM playlists WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()
    assert tuple(row) == ("Updated", "Updated body", "unlisted")
