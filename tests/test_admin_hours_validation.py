# SPDX-License-Identifier: MIT
"""Strict time-window contracts for admin analytics endpoints."""

import sys


def test_admin_analytics_reject_invalid_hours(
    app, client, monkeypatch, tmp_path,
):
    server = sys.modules["bottube_server"]
    monkeypatch.setattr(server, "ADMIN_KEY", "test-admin-key")
    monkeypatch.setattr(
        server, "_VISITOR_LOG_PATH", tmp_path / "missing-visitors.jsonl",
    )
    headers = {"X-Admin-Key": "test-admin-key"}
    invalid_values = ["abc", "1.5", "0", "-1", "169"]
    routes = ["/api/admin/visitors", "/api/admin/scan-content"]

    for route in routes:
        for value in invalid_values:
            response = client.get(
                route, query_string={"hours": value}, headers=headers,
            )
            assert response.status_code == 400, (
                route, value, response.get_json(),
            )
            assert response.get_json().get("error")

        for value in [None, "1", "168"]:
            query = {} if value is None else {"hours": value}
            response = client.get(route, query_string=query, headers=headers)
            assert response.status_code == 200, (
                route, value, response.get_json(),
            )
            assert response.get_json()["hours"] == int(value or 24)
