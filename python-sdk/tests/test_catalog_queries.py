# SPDX-License-Identifier: MIT
"""Search and trending options must reach parameters the server consumes."""

from io import BytesIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from bottube.client import BoTTubeClient


@pytest.fixture
def client_and_transport():
    client = BoTTubeClient(base_url="https://example.invalid")
    with patch("bottube.client.urlopen") as transport:
        transport.return_value = BytesIO(b'{"videos":[],"total":0}')
        yield client, transport


def query(transport):
    return parse_qs(urlsplit(transport.call_args.args[0].full_url).query)


def test_search_legacy_limit_uses_server_page_size(client_and_transport):
    client, transport = client_and_transport
    result = client.search("cats & dogs / café", 3)
    assert query(transport) == {"q": ["cats & dogs / café"], "per_page": ["3"]}
    assert result == {"videos": [], "total": 0}


def test_search_can_request_later_result_pages(client_and_transport):
    client, transport = client_and_transport
    client.search("robots", page=2, per_page=4)
    assert query(transport) == {"q": ["robots"], "page": ["2"], "per_page": ["4"]}


def test_search_default_leaves_pagination_to_server(client_and_transport):
    client, transport = client_and_transport
    client.search("robots")
    assert query(transport) == {"q": ["robots"]}


def test_search_rejects_ambiguous_page_sizes(client_and_transport):
    client, transport = client_and_transport
    with pytest.raises(ValueError, match="limit.*per_page"):
        client.search("robots", limit=3, per_page=4)
    transport.assert_not_called()


def test_zero_search_limit_reaches_server_validation(client_and_transport):
    client, transport = client_and_transport
    client.search("robots", limit=0)
    assert query(transport) == {"q": ["robots"], "per_page": ["0"]}


@pytest.mark.parametrize("timeframe,days", [("day", "1"), ("week", "7"), ("month", "30")])
def test_trending_timeframes_translate_to_days(client_and_transport, timeframe, days):
    client, transport = client_and_transport
    client.get_trending(10, timeframe)
    assert query(transport) == {"limit": ["10"], "days": [days]}


def test_trending_accepts_day_window_and_category(client_and_transport):
    client, transport = client_and_transport
    client.get_trending(days=14, category="science-tech")
    assert query(transport) == {"days": ["14"], "category": ["science-tech"]}


def test_trending_since_zero_is_preserved(client_and_transport):
    client, transport = client_and_transport
    client.get_trending(since=0)
    assert query(transport) == {"since": ["0"]}


@pytest.mark.parametrize("options", [
    {"days": 2, "since": 123},
    {"timeframe": "week", "days": 2},
    {"timeframe": "week", "since": 123},
])
def test_trending_rejects_conflicting_windows(client_and_transport, options):
    client, transport = client_and_transport
    with pytest.raises(ValueError, match="one of timeframe, days, or since"):
        client.get_trending(**options)
    transport.assert_not_called()


def test_unknown_timeframe_is_not_silently_ignored(client_and_transport):
    client, transport = client_and_transport
    with pytest.raises(ValueError, match="day.*week.*month"):
        client.get_trending(timeframe="forever")
    transport.assert_not_called()


def test_default_trending_preserves_server_defaults(client_and_transport):
    client, transport = client_and_transport
    client.get_trending()
    assert query(transport) == {}
