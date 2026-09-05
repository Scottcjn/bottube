# SPDX-License-Identifier: MIT


def test_duplicate_comment_cleanup_rejects_invalid_window(client, app):
    admin_key = app.view_functions["admin_duplicate_comments"].__globals__["ADMIN_KEY"]

    for query in ("window_h=abc", "window_h=-1", "window_h=8761"):
        response = client.get(
            f"/api/admin/duplicate-comments?{query}",
            headers={"X-Admin-Key": admin_key},
        )

        assert response.status_code == 400, query
        assert response.get_json()["error"], query

    valid = client.get(
        "/api/admin/duplicate-comments?window_h=24",
        headers={"X-Admin-Key": admin_key},
    )
    assert valid.status_code == 200
    assert valid.get_json()["dry_run"] is True

    unauthorized = client.get("/api/admin/duplicate-comments?window_h=abc")
    assert unauthorized.status_code == 403
