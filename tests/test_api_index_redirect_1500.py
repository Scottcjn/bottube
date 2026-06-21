# SPDX-License-Identifier: MIT
"""
Regression tests for the bare ``/api`` entry-point redirect (Refs #1500).

Bug covered:
- Bottube #1500: the bare ``/api`` path had no route, so it fell through to the
  catch-all and rendered the "Video Not Found" 404 page. The fix adds a thin
  ``/api`` -> ``/api/docs`` redirect, matching the additive alias-route pattern
  (Refs #1362, #1371).

These tests pin the intended behaviour so a future rename of
``api_docs_swagger_ui`` (which would make ``url_for`` raise ``BuildError`` at
request time) is caught in CI rather than in production:

- ``GET /api`` returns a permanent redirect (301/308), not a temporary 302.
- The ``Location`` header points at the Swagger UI docs (``/api/docs``).
- ``strict_slashes=False`` means the trailing-slash variant ``/api/`` resolves
  in a single redirect to the same target (no double round-trip via Flask's
  own slash-normalising 308).
"""


def _docs_target(client):
    """Resolve the canonical Swagger UI path via the app's own url_for."""
    from bottube_server import app, url_for

    with app.test_request_context():
        return url_for("api_docs_swagger_ui")


def test_api_returns_permanent_redirect(client):
    resp = client.get("/api", follow_redirects=False)
    assert resp.status_code in (301, 308), (
        "/api must be a permanent redirect (301/308) for a stable, indexed "
        f"developer entry point, not a temporary 302 — got {resp.status_code}"
    )


def test_api_redirects_to_docs(client):
    resp = client.get("/api", follow_redirects=False)
    location = resp.headers.get("Location", "")
    target = _docs_target(client)
    assert location.endswith(target) or target in location, (
        f"/api Location must point at the API docs ({target!r}), got {location!r}"
    )


def test_api_trailing_slash_single_redirect(client):
    # With strict_slashes=False the trailing-slash form must land on the same
    # docs target directly, not bounce through an extra slash-normalising hop.
    resp = client.get("/api/", follow_redirects=False)
    assert resp.status_code in (301, 308), (
        f"/api/ must redirect (301/308) in one hop, got {resp.status_code}"
    )
    location = resp.headers.get("Location", "")
    target = _docs_target(client)
    assert location.endswith(target) or target in location, (
        f"/api/ Location must point at the API docs ({target!r}), got {location!r}"
    )
