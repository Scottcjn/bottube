# SPDX-License-Identifier: MIT
import sqlite3
import time

import pytest
from flask import Flask, g

import usdc_blueprint


@pytest.fixture
def usdc_client(tmp_path):
    db_path = tmp_path / "bottube.db"
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(usdc_blueprint.usdc_bp)

    @app.before_request
    def before_request():
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row

    @app.teardown_request
    def teardown_request(_exc):
        db = getattr(g, "db", None)
        if db is not None:
            db.close()

    with sqlite3.connect(db_path) as db:
        db.execute(
            "CREATE TABLE agents (name TEXT PRIMARY KEY, api_key TEXT UNIQUE NOT NULL)"
        )
        usdc_blueprint.init_usdc_tables(db)
        now = time.time()
        db.executemany(
            "INSERT INTO agents (name, api_key) VALUES (?, ?)",
            [("alice", "key-alice"), ("bob", "key-bob")],
        )
        db.execute(
            """
            INSERT INTO usdc_balances
            (agent_name, balance_usdc, total_deposited, total_spent, total_earned, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("alice", 10.0, 10.0, 0.0, 0.0, now),
        )
        db.commit()

    client = app.test_client()
    client.db_path = db_path
    client.auth_headers = {"X-API-Key": "key-alice"}
    return client


def _table_count(db_path, table):
    with sqlite3.connect(db_path) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _balance(db_path, agent_name):
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT balance_usdc, total_spent FROM usdc_balances WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()
    return row


@pytest.mark.parametrize("amount", ["abc", "NaN", "Infinity", True])
def test_usdc_tip_rejects_malformed_amounts_without_writes(usdc_client, amount):
    before_tips = _table_count(usdc_client.db_path, "usdc_tips")
    before_alice = _balance(usdc_client.db_path, "alice")

    response = usdc_client.post(
        "/api/usdc/tip",
        json={"to_agent": "bob", "amount_usdc": amount},
        headers=usdc_client.auth_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "amount_usdc must be a finite number"
    assert _table_count(usdc_client.db_path, "usdc_tips") == before_tips
    assert _balance(usdc_client.db_path, "alice") == before_alice


@pytest.mark.parametrize("amount", ["abc", "NaN", "Infinity", True])
def test_usdc_payout_rejects_malformed_amounts_without_writes(usdc_client, amount):
    before_payouts = _table_count(usdc_client.db_path, "usdc_payouts")
    before_alice = _balance(usdc_client.db_path, "alice")

    response = usdc_client.post(
        "/api/usdc/payout",
        json={"to_address": "0x" + "a" * 40, "amount_usdc": amount},
        headers=usdc_client.auth_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "amount_usdc must be a finite number"
    assert _table_count(usdc_client.db_path, "usdc_payouts") == before_payouts
    assert _balance(usdc_client.db_path, "alice") == before_alice


def test_usdc_tip_rejects_non_object_json_body(usdc_client):
    before_tips = _table_count(usdc_client.db_path, "usdc_tips")

    response = usdc_client.post(
        "/api/usdc/tip",
        json=["not", "an", "object"],
        headers=usdc_client.auth_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "JSON object required"
    assert _table_count(usdc_client.db_path, "usdc_tips") == before_tips


def test_usdc_deposit_rejects_non_object_json_before_verification(
    usdc_client,
    monkeypatch,
):
    monkeypatch.setattr(
        usdc_blueprint,
        "verify_usdc_transfer_onchain",
        lambda _tx_hash: pytest.fail("verification should not run"),
    )

    response = usdc_client.post(
        "/api/usdc/deposit",
        json="not-object",
        headers=usdc_client.auth_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "JSON object required"
    assert _table_count(usdc_client.db_path, "usdc_deposits") == 0


def test_usdc_deposit_rejects_non_string_tx_hash_before_verification(
    usdc_client,
    monkeypatch,
):
    monkeypatch.setattr(
        usdc_blueprint,
        "verify_usdc_transfer_onchain",
        lambda _tx_hash: pytest.fail("verification should not run"),
    )

    response = usdc_client.post(
        "/api/usdc/deposit",
        json={"tx_hash": ["0xabc"]},
        headers=usdc_client.auth_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["error"].startswith("tx_hash required")
    assert _table_count(usdc_client.db_path, "usdc_deposits") == 0


def test_usdc_premium_rejects_non_object_json_without_writes(usdc_client):
    before_premium = _table_count(usdc_client.db_path, "usdc_premium")
    before_alice = _balance(usdc_client.db_path, "alice")

    response = usdc_client.post(
        "/api/usdc/premium",
        json="not-object",
        headers=usdc_client.auth_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "JSON object required"
    assert _table_count(usdc_client.db_path, "usdc_premium") == before_premium
    assert _balance(usdc_client.db_path, "alice") == before_alice


def test_usdc_premium_rejects_non_string_tier_without_writes(usdc_client):
    before_premium = _table_count(usdc_client.db_path, "usdc_premium")
    before_alice = _balance(usdc_client.db_path, "alice")

    response = usdc_client.post(
        "/api/usdc/premium",
        json={"tier": ["basic"]},
        headers=usdc_client.auth_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "tier must be a string"
    assert _table_count(usdc_client.db_path, "usdc_premium") == before_premium
    assert _balance(usdc_client.db_path, "alice") == before_alice


def test_usdc_verify_payment_rejects_non_object_json_before_verification(
    usdc_client,
    monkeypatch,
):
    monkeypatch.setattr(
        usdc_blueprint,
        "verify_usdc_transfer_onchain",
        lambda _tx_hash: pytest.fail("verification should not run"),
    )

    response = usdc_client.post("/api/usdc/verify-payment", json=["bad"])

    assert response.status_code == 400
    assert response.get_json()["error"] == "JSON object required"


def test_usdc_verify_payment_rejects_non_string_tx_hash_before_verification(
    usdc_client,
    monkeypatch,
):
    monkeypatch.setattr(
        usdc_blueprint,
        "verify_usdc_transfer_onchain",
        lambda _tx_hash: pytest.fail("verification should not run"),
    )

    response = usdc_client.post(
        "/api/usdc/verify-payment",
        json={"tx_hash": ["0xabc"]},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "tx_hash required"


def test_valid_usdc_tip_still_debits_sender_and_credits_creator(usdc_client):
    response = usdc_client.post(
        "/api/usdc/tip",
        json={"to_agent": "bob", "amount_usdc": "2.00"},
        headers=usdc_client.auth_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["tip"]["creator_receives"] == 1.7
    assert body["tip"]["platform_fee"] == 0.3

    alice = _balance(usdc_client.db_path, "alice")
    bob = _balance(usdc_client.db_path, "bob")
    assert alice == (8.0, 2.0)
    assert bob == (1.7, 0.0)
    assert _table_count(usdc_client.db_path, "usdc_tips") == 1


def test_valid_usdc_payout_still_creates_pending_request(usdc_client):
    response = usdc_client.post(
        "/api/usdc/payout",
        json={"to_address": "0x" + "b" * 40, "amount_usdc": "1.25"},
        headers=usdc_client.auth_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["payout"]["status"] == "pending"
    assert body["payout"]["amount_usdc"] == 1.25
    assert _balance(usdc_client.db_path, "alice") == (8.75, 1.25)
    assert _table_count(usdc_client.db_path, "usdc_payouts") == 1
