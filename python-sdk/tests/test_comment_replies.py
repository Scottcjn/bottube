# SPDX-License-Identifier: MIT
"""Filtering follows the flat parent_id contract returned by get_comments."""

import copy
import json
from io import BytesIO
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest

from bottube.client import BoTTubeClient


@pytest.fixture
def response():
    return {
        "comments": [
            {"id": 10, "parent_id": None, "content": "First root", "likes": 3},
            {"id": 11, "parent_id": 10, "content": "Reply to first root"},
            {"id": 12, "parent_id": None, "content": "Second root", "likes": 1},
            {"id": 13, "parent_id": 11, "content": "Nested reply"},
        ],
        "count": 4,
        "context": {"video_id": "demo"},
    }


def test_exclude_replies_returns_roots_in_order_and_matching_count(response):
    client = BoTTubeClient(base_url="https://example.invalid")
    with patch("bottube.client.urlopen", return_value=BytesIO(json.dumps(response).encode())) as transport:
        result = client.get_comments("demo", include_replies=False)
    assert result["comments"] == [response["comments"][0], response["comments"][2]]
    assert result["count"] == 2
    assert result["context"] == response["context"]
    # Fetch the supported endpoint; replies=0 is not a server-side filter.
    assert urlsplit(transport.call_args.args[0].full_url).path == "/api/videos/demo/comments"
    assert urlsplit(transport.call_args.args[0].full_url).query == ""


@pytest.mark.parametrize("options", [{}, {"include_replies": True}])
def test_default_and_explicit_include_preserve_complete_response(response, options):
    client = BoTTubeClient()
    with patch.object(client, "_request", return_value=response):
        result = client.get_comments("demo", **options)
    assert result is response


def test_filter_does_not_mutate_transport_response(response):
    original = copy.deepcopy(response)
    client = BoTTubeClient()
    with patch.object(client, "_request", return_value=response):
        result = client.get_comments("demo", include_replies=False)
    assert response == original
    assert result is not response
    assert result["comments"] is not response["comments"]


@pytest.mark.parametrize("comments", [[], [{"id": 11, "parent_id": 10}]])
def test_no_roots_yields_empty_list_and_zero_count(comments):
    client = BoTTubeClient()
    with patch.object(client, "_request", return_value={"comments": comments, "count": len(comments)}):
        result = client.get_comments("demo", include_replies=False)
    assert result == {"comments": [], "count": 0}


def test_rows_without_parent_id_remain_visible():
    # An absent parent field does not identify a row as a reply.
    response = {"comments": [{"id": 10, "content": "Root"}], "count": 1}
    client = BoTTubeClient()
    with patch.object(client, "_request", return_value=response):
        result = client.get_comments("demo", include_replies=False)
    assert result == response
