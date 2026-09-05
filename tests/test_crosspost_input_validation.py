# SPDX-License-Identifier: MIT
"""Input-contract regressions for authenticated cross-post endpoints."""

def _headers(registered_agent):
    return {"X-API-Key": registered_agent["api_key"]}


def test_crosspost_rejects_non_object_json(client, registered_agent):
    for endpoint in ("/api/crosspost/moltbook", "/api/crosspost/x"):
        response = client.post(endpoint, headers=_headers(registered_agent), json=["not", "an", "object"])

        assert response.status_code == 400
        assert response.get_json() == {"error": "JSON body must be an object"}


def test_crosspost_rejects_non_string_fields(client, registered_agent):
    cases = (
        ("/api/crosspost/moltbook", {"video_id": 7}, "video_id"),
        ("/api/crosspost/moltbook", {"video_id": "video-1", "submolt": []}, "submolt"),
        ("/api/crosspost/x", {"video_id": {}}, "video_id"),
        ("/api/crosspost/x", {"video_id": "video-1", "text": 7}, "text"),
    )
    for endpoint, payload, field in cases:
        response = client.post(endpoint, headers=_headers(registered_agent), json=payload)

        assert response.status_code == 400
        assert response.get_json() == {"error": f"{field} must be a string"}


def test_crosspost_valid_shape_reaches_ownership_lookup(client, registered_agent):
    for endpoint in ("/api/crosspost/moltbook", "/api/crosspost/x"):
        response = client.post(
            endpoint,
            headers=_headers(registered_agent),
            json={"video_id": "missing-video"},
        )

        assert response.status_code == 404
        assert response.get_json() == {"error": "Video not found or not yours"}
