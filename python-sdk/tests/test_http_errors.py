# SPDX-License-Identifier: MIT
"""Preserve SDK HTTP errors regardless of the response JSON shape."""

import json
from functools import partial
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import patch

import pytest

from bottube.client import BoTTubeClient, BoTTubeError


@pytest.fixture(params=["request", "multipart"])
def call_api(request, tmp_path):
    client = BoTTubeClient(base_url="https://example.test")
    if request.param == "request":
        return client.get_categories
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video fixture")
    return partial(client.upload, str(video), title="Error regression")


@pytest.mark.parametrize(
    "detail", [[], ["upstream unavailable"], None, "unavailable", 0, 502, True, False]
)
def test_non_object_json_http_error_preserves_status_and_detail(call_api, detail):
    original = HTTPError(
        "https://example.test/api", 502, "Bad Gateway", {},
        BytesIO(json.dumps(detail).encode()),
    )
    with patch("bottube.client.urlopen", side_effect=original):
        with pytest.raises(BoTTubeError) as caught:
            call_api()

    error = caught.value
    assert error.status_code == 502
    assert error.error == str(original)
    assert error.detail == detail
    assert type(error.detail) is type(detail)
    assert error.__cause__ is original


@pytest.mark.parametrize("detail", [{"error": "Invalid request", "field": "title"}, {}])
def test_object_http_error_keeps_existing_message_and_detail(call_api, detail):
    original = HTTPError(
        "https://example.test/api", 400, "Bad Request", {},
        BytesIO(json.dumps(detail).encode()),
    )
    with patch("bottube.client.urlopen", side_effect=original):
        with pytest.raises(BoTTubeError) as caught:
            call_api()

    assert caught.value.status_code == 400
    assert caught.value.error == detail.get("error", str(original))
    assert caught.value.detail == detail
    assert caught.value.__cause__ is original


@pytest.mark.parametrize("body", [b"", b"<html>Bad Gateway</html>", b"\xff"])
def test_non_json_http_error_keeps_existing_fallback(call_api, body):
    original = HTTPError(
        "https://example.test/api", 502, "Bad Gateway", {}, BytesIO(body)
    )
    with patch("bottube.client.urlopen", side_effect=original):
        with pytest.raises(BoTTubeError) as caught:
            call_api()

    assert caught.value.status_code == 502
    assert caught.value.error == str(original)
    assert caught.value.detail == {"error": str(original)}
    assert caught.value.__cause__ is original


def test_successful_json_response_is_unchanged(call_api):
    with patch("bottube.client.urlopen", return_value=BytesIO(b'{"ok": true}')):
        assert call_api() == {"ok": True}


def test_malformed_successful_response_still_raises_decode_error(call_api):
    with patch("bottube.client.urlopen", return_value=BytesIO(b"not JSON")):
        with pytest.raises(json.JSONDecodeError):
            call_api()
