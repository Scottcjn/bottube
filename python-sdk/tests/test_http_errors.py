# SPDX-License-Identifier: MIT
"""Preserve SDK HTTP errors regardless of the response JSON shape."""

import json
from functools import partial
from io import BytesIO
from urllib.error import HTTPError, URLError
from unittest.mock import patch

import pytest

from bottube import client as sdk
from bottube.client import BoTTubeClient, BoTTubeError


@pytest.fixture(params=["request", "multipart", "streaming"])
def call_api(request, tmp_path):
    client = BoTTubeClient(base_url="https://example.test")
    if request.param == "request":
        return client.get_categories
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video fixture")
    if request.param == "streaming":
        return partial(client._streaming_upload, "/api/upload", str(video),
                       {"title": "Error regression"})
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


@pytest.mark.parametrize(
    "size", [100 * 1024 * 1024, 100 * 1024 * 1024 + 1],
    ids=["buffered", "streaming"],
)
def test_upload_http_error_at_streaming_boundary(size):
    client = sdk.BoTTubeClient(base_url="https://example.invalid")
    detail = {"error": "Rate limit exceeded", "retry_after": 60}

    def reject(request, **kwargs):
        assert request.get_method() == "POST"
        assert request.full_url == "https://example.invalid/api/upload"
        raise HTTPError(request.full_url, 429, "Too Many Requests", {},
                        BytesIO(json.dumps(detail).encode()))

    with patch.object(sdk.os.path, "getsize", return_value=size), \
         patch.object(sdk, "open", side_effect=lambda *a, **k: BytesIO(b"x"), create=True), \
         patch.object(sdk, "urlopen", side_effect=reject):
        with pytest.raises(sdk.BoTTubeError) as caught:
            client.upload("clip.mp4", title="Local fixture")

    assert caught.value.status_code == 429
    assert caught.value.error == detail["error"]
    assert caught.value.detail == detail
    assert isinstance(caught.value.__cause__, HTTPError)


def test_streaming_transport_error_preserves_runtime_error(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video fixture")
    original = URLError("connection refused")
    with patch.object(sdk.os.path, "getsize", return_value=100 * 1024 * 1024 + 1), \
         patch.object(sdk, "urlopen", side_effect=original):
        with pytest.raises(RuntimeError, match="Upload failed: connection refused") as caught:
            BoTTubeClient().upload(str(video), title="Transport error")

    assert caught.value.__cause__ is original
