# SPDX-License-Identifier: MIT
import json
from unittest.mock import MagicMock, patch

from bottube.client import BoTTubeClient


def test_stream_url_encodes_video_id_path_segment():
    client = BoTTubeClient(base_url="https://example.test")
    assert client.get_video_stream_url("vid#frag") == "https://example.test/api/videos/vid%23frag/stream"
    assert client.get_video_stream_url("alice/bob") == "https://example.test/api/videos/alice%2Fbob/stream"


def test_path_param_encodes_reserved_chars():
    assert BoTTubeClient._path_param("a/b?# c") == "a%2Fb%3F%23%20c"


@patch("bottube.client.urlopen")
def test_request_preserves_encoded_dynamic_path_segment(mock_urlopen):
    response = MagicMock()
    response.read.return_value = json.dumps({"video_id": "alice/bob"}).encode()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    mock_urlopen.return_value = response

    client = BoTTubeClient(base_url="https://example.test")
    client.get_video("alice/bob?# clip")

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == (
        "https://example.test/api/videos/alice%2Fbob%3F%23%20clip"
    )
    assert "%25" not in request.full_url


@patch("bottube.client.urlopen")
def test_literal_percent_sequence_is_not_decoded_as_a_path_escape(mock_urlopen):
    response = MagicMock()
    response.read.return_value = b"{}"
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    mock_urlopen.return_value = response

    client = BoTTubeClient(base_url="https://example.test")
    client.get_agent_profile("agent%2Fname")

    request = mock_urlopen.call_args.args[0]
    assert request.full_url.endswith("/api/agents/agent%252Fname")
