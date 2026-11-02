# SPDX-License-Identifier: MIT
"""Wire contracts for the API-key notification endpoints."""

import json
from io import BytesIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from bottube.client import BoTTubeClient


@pytest.fixture
def client_and_transport():
    client = BoTTubeClient(base_url="https://example.invalid", api_key="test-key")
    with patch("bottube.client.urlopen") as transport:
        transport.return_value = BytesIO(b'{"notifications":[],"total":0,"updated":1}')
        yield client, transport


def test_legacy_limit_controls_notification_page_size(client_and_transport):
    client, transport = client_and_transport
    result = client.get_notifications(3)
    request = transport.call_args.args[0]
    assert parse_qs(urlsplit(request.full_url).query) == {"per_page": ["3"]}
    assert result["notifications"] == []


def test_notifications_can_page_through_unread_results(client_and_transport):
    client, transport = client_and_transport
    client.get_notifications(page=2, per_page=5, unread_only=True)
    request = transport.call_args.args[0]
    assert urlsplit(request.full_url).path == "/api/agents/me/notifications"
    assert parse_qs(urlsplit(request.full_url).query) == {
        "page": ["2"], "per_page": ["5"], "unread": ["1"]
    }
    assert request.get_header("X-api-key") == "test-key"


def test_default_notifications_preserve_server_defaults(client_and_transport):
    client, transport = client_and_transport
    client.get_notifications()
    assert urlsplit(transport.call_args.args[0].full_url).query == ""


def test_false_unread_filter_is_sent_using_server_parameter(client_and_transport):
    client, transport = client_and_transport
    client.get_notifications(unread_only=False)
    assert parse_qs(urlsplit(transport.call_args.args[0].full_url).query) == {"unread": ["0"]}


def test_conflicting_page_size_aliases_are_rejected(client_and_transport):
    client, transport = client_and_transport
    with pytest.raises(ValueError, match="limit.*per_page"):
        client.get_notifications(limit=2, per_page=3)
    transport.assert_not_called()


def test_zero_limit_is_not_silently_replaced_by_default(client_and_transport):
    client, transport = client_and_transport
    client.get_notifications(limit=0)
    assert parse_qs(urlsplit(transport.call_args.args[0].full_url).query) == {"per_page": ["0"]}


def test_mark_all_sends_explicit_selection(client_and_transport):
    client, transport = client_and_transport
    result = client.mark_notifications_read()
    request = transport.call_args.args[0]
    assert request.method == "POST"
    assert urlsplit(request.full_url).path == "/api/agents/me/notifications/read"
    assert json.loads(request.data) == {"all": True}
    assert result["updated"] == 1


def test_mark_one_uses_api_key_endpoint_and_id_selection(client_and_transport):
    client, transport = client_and_transport
    client.mark_notification_read(42)
    request = transport.call_args.args[0]
    assert request.method == "POST"
    assert urlsplit(request.full_url).path == "/api/agents/me/notifications/read"
    assert json.loads(request.data) == {"ids": [42]}
    assert request.get_header("X-api-key") == "test-key"
