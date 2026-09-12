# SPDX-License-Identifier: MIT
"""
Regression tests for GET /api and GET /api/ redirects (Fixes #2244).

Bugs covered:
- BoTTube #2244: Production /api returns 404 although current main redirects it to /docs.
  Verifies that both /api and /api/ cleanly return 302 redirects pointing to /docs.
"""


def test_api_redirects_to_docs(client):
    """GET /api must return 302 redirect to /docs."""
    resp = client.get("/api", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert location.endswith("/docs") or "/docs" in location, (
        f"/api Location must point to /docs, got {location!r}"
    )


def test_api_trailing_slash_redirects_to_docs(client):
    """GET /api/ must return 302 redirect to /docs."""
    resp = client.get("/api/", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert location.endswith("/docs") or "/docs" in location, (
        f"/api/ Location must point to /docs, got {location!r}"
    )


def test_api_head_requests_redirect_to_docs(client):
    """HEAD /api and HEAD /api/ must return 302 redirect to /docs."""
    for path in ("/api", "/api/"):
        resp = client.head(path, follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers.get("Location", "")
        assert "/docs" in location, f"HEAD {path} Location must contain /docs, got {location!r}"


def test_api_routes_registered_in_url_map():
    """Both /api and /api/ rules must be registered in the Flask URL map."""
    import bottube_server

    flask_app = bottube_server.app
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    assert "/api" in rules, "/api rule missing from url_map"
    assert "/api/" in rules, "/api/ rule missing from url_map"
