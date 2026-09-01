# SPDX-License-Identifier: MIT


def test_comment_cleanup_rejects_ambiguous_json_types(client, app):
    admin_key = app.view_functions["admin_comment_cleanup"].__globals__["ADMIN_KEY"]
    headers = {"X-Admin-Key": admin_key}
    invalid_payloads = (
        {"force_remove": "false", "remove_dupes": False, "max_similar": 0},
        {"force_remove": 1},
        {"remove_dupes": "false"},
        {"max_similar": "3"},
        {"max_similar": True},
        {"max_similar": -1},
        {"max_similar": 101},
        [],
    )

    for payload in invalid_payloads:
        response = client.post(
            "/api/admin/comment-cleanup",
            headers=headers,
            json=payload,
        )

        assert response.status_code == 400, payload
        assert response.get_json()["error"], payload

    valid = client.post(
        "/api/admin/comment-cleanup",
        headers=headers,
        json={"force_remove": False, "remove_dupes": True, "max_similar": 3},
    )
    assert valid.status_code == 200
    assert valid.get_json()["mode"] == "coach_and_hold"

    unauthorized = client.post(
        "/api/admin/comment-cleanup",
        json={"force_remove": "false"},
    )
    assert unauthorized.status_code == 403
