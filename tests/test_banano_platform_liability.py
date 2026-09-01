"""Regression coverage for network-wide BAN liability reconciliation."""

import sqlite3

from flask import Flask

import banano_blueprint


def test_internal_tip_does_not_create_new_platform_liability(tmp_path, monkeypatch):
    db_path = tmp_path / "bottube.db"
    db = sqlite3.connect(db_path)
    banano_blueprint.init_ban_tables(db)
    db.executemany(
        "INSERT INTO ban_transactions "
        "(agent_id,tx_type,amount_ban,reason,status,created_at) VALUES(?,?,?,?,?,?)",
        [
            (1, "reward", 10.0, "earned", "credited", 1.0),
            (1, "tip_sent", 4.0, "tip_to_two", "credited", 2.0),
            (2, "tip_received", 4.0, "tip_from_one", "credited", 2.0),
            (2, "withdrawal", 2.0, "withdraw", "sent", 3.0),
        ],
    )
    db.commit()
    db.close()

    monkeypatch.setenv("BOTTUBE_DB_PATH", str(db_path))
    monkeypatch.setattr(banano_blueprint, "ADMIN_KEY", "admin-test-key")
    monkeypatch.setattr(
        banano_blueprint,
        "get_platform_balance",
        lambda: {"balance_ban": 100.0},
    )
    app = Flask(__name__)
    app.register_blueprint(banano_blueprint.ban_bp)

    response = app.test_client().get(
        "/ban/platform-status", headers={"X-Admin-Key": "admin-test-key"}
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["off_chain_liabilities_ban"] == 8.0
    assert payload["internal_tips_ban"] == 4.0
