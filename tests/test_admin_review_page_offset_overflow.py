# SPDX-License-Identifier: MIT
"""Regression coverage for SQLite OFFSET overflow in admin review queues."""

import pytest


@pytest.mark.parametrize("path", ["/api/admin/referrals", "/api/admin/badges"])
def test_admin_review_queues_reject_page_beyond_sqlite_range(
    app, client, monkeypatch, path
):
    import bottube_server

    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "test-admin")

    response = client.get(
        f"{path}?page=9223372036854775807&per_page=100",
        headers={"X-Admin-Key": "test-admin"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "page out of range"}
