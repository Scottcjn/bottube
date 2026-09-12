# SPDX-License-Identifier: MIT
"""Exercise SDK multipart bodies with the server's form-data parser."""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from werkzeug.formparser import parse_form_data
from werkzeug.test import EnvironBuilder

from bottube.client import BoTTubeClient


@pytest.mark.parametrize("streaming", [False, True], ids=["buffered", "streaming"])
@pytest.mark.parametrize(
    ("filename", "expected_filename"),
    [
        ("clip.mp4", "clip.mp4"),
        ("my clip; take 2.mp4", "my clip; take 2.mp4"),
        ("演示.mp4", "演示.mp4"),
        ('clip"take2.mp4', 'clip"take2.mp4'),
        ("clip\rtake2.mp4", "clip%0Dtake2.mp4"),
        ("clip\ntake2.mp4", "clip%0Atake2.mp4"),
        (
            'clip"\r\nX-Extra: injected\r\n\r\ntake2.mp4',
            'clip"%0D%0AX-Extra: injected%0D%0A%0D%0Atake2.mp4',
        ),
    ],
)
def test_upload_preserves_video_part(tmp_path, streaming, filename, expected_filename):
    video_bytes = b"\x00\x01video\r\npayload\xff"
    video_path = tmp_path / filename
    video_path.write_bytes(video_bytes)
    client = BoTTubeClient(base_url="https://example.test", api_key="test-key")
    captured = {}

    def receive(request, timeout):
        body = request.data
        if streaming:
            assert not isinstance(body, (bytes, bytearray))
            body = b"".join(body)
            assert int(request.get_header("Content-length")) == len(body)
        builder = EnvironBuilder(
            method="POST",
            input_stream=BytesIO(body),
            content_type=request.get_header("Content-type"),
            content_length=len(body),
        )
        try:
            _, form, files = parse_form_data(builder.get_environ())
            captured["form"] = form
            captured["file_keys"] = list(files)
            if "video" in files:
                video = files["video"]
                captured["filename"] = video.filename
                captured["content"] = video.read()
                captured["headers"] = video.headers
                video.close()
        finally:
            builder.close()
        return BytesIO(b'{"video_id":"uploaded"}')

    with patch("bottube.client.urlopen", side_effect=receive):
        if streaming:
            result = client._streaming_upload(
                "/api/upload", str(video_path), {"title": "Test clip"}, chunk_size=3
            )
        else:
            result = client.upload(str(video_path), title="Test clip")

    assert result == {"video_id": "uploaded"}
    assert captured["file_keys"] == ["video"]
    assert captured["filename"] == expected_filename
    assert Path(captured["filename"]).suffix == ".mp4"
    assert captured["content"] == video_bytes
    assert captured["form"].to_dict() == {"title": "Test clip"}
    assert "X-Extra" not in captured["headers"]
