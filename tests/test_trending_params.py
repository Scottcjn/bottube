"""Tests for /api/trending limit/days/since query param validation."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
from bottube_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _mock_db():
    """Return a mock db connection that yields empty results."""
    mock = MagicMock()
    mock.execute.return_value.fetchall.return_value = []
    return mock


# --- limit param validation ---

def test_limit_default(client):
    with patch("bottube_server.get_db", return_value=_mock_db()):
        rv = client.get("/api/trending")
        assert rv.status_code == 200


def test_limit_valid(client):
    with patch("bottube_server.get_db", return_value=_mock_db()):
        rv = client.get("/api/trending?limit=5")
        assert rv.status_code == 200


def test_limit_zero_rejected(client):
    rv = client.get("/api/trending?limit=0")
    assert rv.status_code == 400


def test_limit_negative_rejected(client):
    rv = client.get("/api/trending?limit=-1")
    assert rv.status_code == 400


def test_limit_non_integer_rejected(client):
    rv = client.get("/api/trending?limit=abc")
    assert rv.status_code == 400


def test_limit_exceeds_max_rejected(client):
    rv = client.get("/api/trending?limit=201")
    assert rv.status_code == 400


def test_limit_at_max(client):
    with patch("bottube_server.get_db", return_value=_mock_db()):
        rv = client.get("/api/trending?limit=200")
        assert rv.status_code == 200


# --- days param validation ---

def test_days_valid(client):
    with patch("bottube_server.get_db", return_value=_mock_db()):
        rv = client.get("/api/trending?days=7")
        assert rv.status_code == 200


def test_days_zero_rejected(client):
    rv = client.get("/api/trending?days=0")
    assert rv.status_code == 400


def test_days_negative_rejected(client):
    rv = client.get("/api/trending?days=-5")
    assert rv.status_code == 400


def test_days_non_integer_rejected(client):
    rv = client.get("/api/trending?days=foo")
    assert rv.status_code == 400


def test_days_exceeds_max_rejected(client):
    rv = client.get("/api/trending?days=91")
    assert rv.status_code == 400


def test_days_at_max(client):
    with patch("bottube_server.get_db", return_value=_mock_db()):
        rv = client.get("/api/trending?days=90")
        assert rv.status_code == 200


# --- since param validation ---

def test_since_valid(client):
    with patch("bottube_server.get_db", return_value=_mock_db()):
        rv = client.get("/api/trending?since=1000000")
        assert rv.status_code == 200


def test_since_negative_rejected(client):
    rv = client.get("/api/trending?since=-1")
    assert rv.status_code == 400


def test_since_non_integer_rejected(client):
    rv = client.get("/api/trending?since=bar")
    assert rv.status_code == 400


# --- combined params ---

def test_all_valid_params(client):
    with patch("bottube_server.get_db", return_value=_mock_db()):
        rv = client.get("/api/trending?limit=10&days=3&since=1700000000")
        assert rv.status_code == 200


def test_first_invalid_param_short_circuits(client):
    rv = client.get("/api/trending?limit=-1&days=-5&since=-1")
    assert rv.status_code == 400
