"""Regression coverage for Studio's public JSON request contract."""

import pytest
from flask import Flask

from studio_blueprint import studio_bp


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test", PROPAGATE_EXCEPTIONS=False)
    app.register_blueprint(studio_bp)
    return app.test_client()


@pytest.mark.parametrize(
    "payload",
    [
        ["not", "an", "object"],
        {"type": ["video"], "prompt": "hello"},
        {"type": "video", "prompt": ["hello"]},
        {"type": "video", "prompt": "hello", "tier": ["text_card"]},
        {"type": "i2v", "prompt": "hello", "image": ["not-base64"]},
    ],
)
def test_generate_rejects_malformed_json_types_without_server_error(client, payload):
    response = client.post("/api/studio/generate", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"]


def test_generate_preserves_empty_object_validation(client):
    response = client.post("/api/studio/generate", json={})

    assert response.status_code == 400
    assert response.get_json() == {"error": "prompt required"}
