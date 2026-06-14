# SPDX-License-Identifier: MIT
"""Regression tests for /xrpc/feed.firehose limit validation."""

import pytest


@pytest.fixture(autouse=True)
def ensure_firehose_tables(app):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS video_provenance (
                video_id TEXT PRIMARY KEY,
                canonical_sha256 TEXT,
                uploader_sig TEXT,
                anchor_chain TEXT,
                anchor_tx_hash TEXT,
                anchor_block_height INTEGER,
                anchor_manifest_hash TEXT
            )
            """
        )
        db.commit()


@pytest.mark.parametrize("limit", ["abc", "0", "201"])
def test_firehose_rejects_invalid_limit(client, limit):
    response = client.get(f"/xrpc/feed.firehose?limit={limit}")

    assert response.status_code == 400
    assert "limit" in response.get_json()["error"]


@pytest.mark.parametrize("limit", [None, "1", "200"])
def test_firehose_accepts_default_and_boundary_limits(client, limit):
    path = "/xrpc/feed.firehose"
    if limit is not None:
        path += f"?limit={limit}"

    response = client.get(path)

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert isinstance(data["events"], list)
