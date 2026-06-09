import sqlite3

import pytest
import werkzeug
from flask import Flask

from gpu_marketplace import gpu_bp, init_gpu_tables


@pytest.fixture()
def client(monkeypatch, tmp_path):
    if not hasattr(werkzeug, "__version__"):
        monkeypatch.setattr(werkzeug, "__version__", "test", raising=False)

    db_path = tmp_path / "bottube_gpu.db"
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(db_path))
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            display_name TEXT,
            api_key TEXT UNIQUE NOT NULL,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            last_active REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE balances (
            miner_id TEXT PRIMARY KEY,
            amount_i64 INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO agents (agent_name, display_name, api_key, last_active)
        VALUES ('gpu_agent', 'GPU Agent', 'bottube_sk_gpu_agent', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO balances (miner_id, amount_i64)
        VALUES ('gpu_agent', 1000000)
        """
    )
    conn.commit()
    conn.close()
    init_gpu_tables(str(db_path))

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(gpu_bp)

    yield app.test_client()


def test_provider_registration_requires_api_key(client):
    resp = client.post("/api/gpu/providers/register", json={"gpu_model": "RTX 3080"})

    assert resp.status_code == 401
    assert resp.get_json() == {"error": "Missing X-API-Key header"}


def test_provider_registration_sets_authenticated_agent(client):
    resp = client.post(
        "/api/gpu/providers/register",
        headers={"X-API-Key": "bottube_sk_gpu_agent"},
        json={"gpu_model": "RTX 3080", "gpu_vram_gb": 10},
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["provider_id"].startswith("gpu_")
    assert data["gpu_model"] == "RTX 3080"
