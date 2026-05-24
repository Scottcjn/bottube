# SPDX-License-Identifier: MIT

from flask import Flask

from chat_handlers import chat_bp


def create_app(tmp_path):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["DATABASE"] = str(tmp_path / "chat.sqlite3")
    app.register_blueprint(chat_bp)
    return app


def set_moderator(client):
    with client.session_transaction() as session:
        session["is_mod"] = True
        session["username"] = "mod"


def test_send_message_rejects_non_object_json(tmp_path):
    client = create_app(tmp_path).test_client()

    response = client.post("/api/chat/demo/send", json="not-object")

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}


def test_send_message_rejects_non_string_message(tmp_path):
    client = create_app(tmp_path).test_client()

    response = client.post("/api/chat/demo/send", json={"message": ["hello"]})

    assert response.status_code == 400
    assert response.get_json() == {"error": "message must be a string"}


def test_send_message_rejects_invalid_tip_amount(tmp_path):
    client = create_app(tmp_path).test_client()

    response = client.post(
        "/api/chat/demo/send",
        json={"message": "hello", "tip_amount": "many"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "tip_amount must be a number"}


def test_send_message_rejects_boolean_numeric_fields(tmp_path):
    client = create_app(tmp_path).test_client()

    response = client.post(
        "/api/chat/demo/send",
        json={"message": "hello", "is_super": True},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "is_super must be an integer"}

    response = client.post(
        "/api/chat/demo/send",
        json={"message": "hello", "tip_amount": False},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "tip_amount must be a number"}


def test_ban_user_rejects_non_object_json(tmp_path):
    client = create_app(tmp_path).test_client()
    set_moderator(client)

    response = client.post("/api/chat/demo/ban", json=["not-object"])

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}


def test_ban_user_rejects_missing_user_id(tmp_path):
    client = create_app(tmp_path).test_client()
    set_moderator(client)

    response = client.post("/api/chat/demo/ban", json={"reason": "spam"})

    assert response.status_code == 400
    assert response.get_json() == {"error": "user_id is required"}


def test_ban_user_rejects_invalid_duration(tmp_path):
    client = create_app(tmp_path).test_client()
    set_moderator(client)

    response = client.post(
        "/api/chat/demo/ban",
        json={"user_id": "alice", "duration": "forever"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "duration must be a number"}


def test_chat_settings_rejects_non_object_json(tmp_path):
    client = create_app(tmp_path).test_client()
    set_moderator(client)

    response = client.post("/api/chat/demo/settings", json="not-object")

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}


def test_chat_settings_rejects_invalid_numeric_fields(tmp_path):
    client = create_app(tmp_path).test_client()
    set_moderator(client)

    response = client.post("/api/chat/demo/settings", json={"slow_mode": "fast"})

    assert response.status_code == 400
    assert response.get_json() == {"error": "slow_mode must be an integer"}


def test_chat_settings_rejects_boolean_numeric_fields(tmp_path):
    client = create_app(tmp_path).test_client()
    set_moderator(client)

    response = client.post("/api/chat/demo/settings", json={"slow_mode": True})

    assert response.status_code == 400
    assert response.get_json() == {"error": "slow_mode must be an integer"}


def test_chat_settings_rejects_non_string_premiere_at(tmp_path):
    client = create_app(tmp_path).test_client()
    set_moderator(client)

    response = client.post("/api/chat/demo/settings", json={"premiere_at": ["soon"]})

    assert response.status_code == 400
    assert response.get_json() == {"error": "premiere_at must be a string"}
