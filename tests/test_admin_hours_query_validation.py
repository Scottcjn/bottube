# SPDX-License-Identifier: MIT
"""Regression coverage for strict admin time-window query validation."""

import pytest


ADMIN_HEADERS = {"X-Admin-Key": "test-admin"}
ROUTES = ("/api/admin/visitors", "/api/admin/scan-content")


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("hours", ("abc", "0", "-1", "169", "1.5"))
def test_admin_hours_rejects_malformed_or_out_of_range_values(
    client, monkeypatch, route, hours
):
    import bottube_server

    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "test-admin", raising=False)
    response = client.get(f"{route}?hours={hours}", headers=ADMIN_HEADERS)

    assert response.status_code == 400
    assert "hours" in response.get_json()["error"]


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("hours", ("1", "168"))
def test_admin_hours_accepts_documented_boundaries(client, monkeypatch, route, hours):
    import bottube_server

    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "test-admin", raising=False)
    response = client.get(f"{route}?hours={hours}", headers=ADMIN_HEADERS)

    assert response.status_code == 200
