# SPDX-License-Identifier: MIT
"""Bounded request contracts for admin media backfill operators."""

import sys

import pytest


ROUTES = (
    "/admin/visual/backfill",
    "/admin/embeddings/backfill",
    "/admin/renditions/backfill",
)


@pytest.fixture
def no_effects_before_validation(monkeypatch):
    server = sys.modules["bottube_server"]
    monkeypatch.setattr(server, "_ts_admin_ok", lambda: True)

    def unexpected_effect():
        raise AssertionError("backfill effect ran before request validation")

    monkeypatch.setattr(server, "_uv_ensure_schema", unexpected_effect)
    monkeypatch.setattr(server, "_ue_ensure_schema", unexpected_effect)
    monkeypatch.setattr(server, "_ensure_provenance_schema", unexpected_effect)
    monkeypatch.setattr(server, "_renditions_ffmpeg_available", unexpected_effect)


def test_backfills_reject_non_object_json_before_effects(
    client, no_effects_before_validation,
):
    for route in ROUTES:
        for payload in ([], True, "batch"):
            response = client.post(route, json=payload)

            assert response.status_code == 400
            assert "object" in response.get_json()["error"]


def test_backfills_reject_invalid_fields_before_effects(
    client, no_effects_before_validation,
):
    cases = (
        ("/admin/visual/backfill", {"limit": "10"}),
        ("/admin/visual/backfill", {"limit": 0}),
        ("/admin/visual/backfill", {"limit": 51}),
        ("/admin/visual/backfill", {"since_video_id": 7}),
        ("/admin/visual/backfill", {"video_ids": "video_1"}),
        ("/admin/visual/backfill", {"video_ids": ["bad id"]}),
        ("/admin/embeddings/backfill", {"limit": 201}),
        ("/admin/embeddings/backfill", {"concurrency": True}),
        ("/admin/embeddings/backfill", {"concurrency": 9}),
        ("/admin/renditions/backfill", {"limit": 101}),
        ("/admin/renditions/backfill", {"concurrency": 0}),
        ("/admin/renditions/backfill", {"since_video_id": []}),
    )
    for route, payload in cases:
        response = client.post(route, json=payload)

        assert response.status_code == 400
        assert response.get_json()["error"]


def test_shared_parser_preserves_defaults_and_valid_boundaries(app):
    cases = (
        ({}, (20, 2, "")),
        (
            {"limit": 1, "concurrency": 1, "since_video_id": None},
            (1, 1, ""),
        ),
        (
            {"limit": 100, "concurrency": 4, "since_video_id": " video_7 "},
            (100, 4, "video_7"),
        ),
    )
    server = sys.modules["bottube_server"]
    for payload, expected in cases:
        with app.test_request_context(json=payload):
            parsed, error = server._parse_admin_media_batch_request(
                default_limit=20,
                max_limit=100,
                default_concurrency=2,
                max_concurrency=4,
            )

        assert error is None
        assert (
            parsed["limit"],
            parsed["concurrency"],
            parsed["since_video_id"],
        ) == expected
