import datetime as dt
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytest
from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import feed_blueprint


def test_escape_xml_handles_none_and_all_special_characters():
    assert feed_blueprint.escape_xml(None) == ""
    assert (
        feed_blueprint.escape_xml("Rock & <Roll> \"Mix\" 'Tape'")
        == "Rock &amp; &lt;Roll&gt; &quot;Mix&quot; &apos;Tape&apos;"
    )


def test_timestamp_helpers_normalize_epoch_and_iso_values():
    expected = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

    assert parsedate_to_datetime(feed_blueprint._to_rfc2822(0)) == expected
    assert parsedate_to_datetime(feed_blueprint._to_rfc2822("0")) == expected
    assert parsedate_to_datetime(
        feed_blueprint._to_rfc2822("1970-01-01T00:00:00Z")
    ) == expected

    assert feed_blueprint._to_iso8601(0) == "1970-01-01T00:00:00+00:00"
    assert feed_blueprint._to_iso8601("0") == "1970-01-01T00:00:00+00:00"
    assert (
        feed_blueprint._to_iso8601("1970-01-01T00:00:00")
        == "1970-01-01T00:00:00+00:00"
    )


def test_normalize_videos_filters_non_dict_entries_from_supported_shapes():
    video_a = {"id": "a"}
    video_b = {"id": "b"}

    assert feed_blueprint._normalize_videos([video_a, "skip", video_b]) == [
        video_a,
        video_b,
    ]
    assert feed_blueprint._normalize_videos({"videos": [video_a, None]}) == [video_a]
    assert feed_blueprint._normalize_videos({"items": ["skip", video_b]}) == [video_b]
    assert feed_blueprint._normalize_videos({"data": [video_a, video_b]}) == [
        video_a,
        video_b,
    ]
    assert feed_blueprint._normalize_videos({"videos": "not-a-list"}) == []


def test_vid_fields_applies_defaults_and_derived_urls():
    fields = feed_blueprint._vid_fields({"id": "vid123"})

    assert fields == {
        "id": "vid123",
        "title": "Untitled Video",
        "desc": "",
        "author": "AI Agent",
        "category": "General",
        "thumb": "https://bottube.ai/api/videos/vid123/thumbnail",
        "stream": "https://bottube.ai/api/videos/vid123/stream",
        "watch": "https://bottube.ai/watch/vid123",
        "created_at": None,
    }


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/feed/rss", 20),
        ("/feed/rss?limit=5", 5),
        ("/feed/rss?limit=0", 1),
        ("/feed/rss?limit=-30", 1),
        ("/feed/rss?limit=250", 100),
        ("/feed/rss?limit=invalid", 20),
    ],
)
def test_parse_limit_defaults_and_clamps_values(path, expected):
    app = Flask(__name__)
    with app.test_request_context(path):
        assert feed_blueprint._parse_limit() == expected


def test_fetch_videos_builds_filtered_request_and_normalizes_response(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            calls.append(("raise_for_status",))

        def json(self):
            return {"items": [{"id": "one"}, "skip", {"id": "two"}]}

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return FakeResponse()

    monkeypatch.setenv("BOTTUBE_API_BASE", "https://api.example.test/")
    monkeypatch.setattr(feed_blueprint.requests, "get", fake_get)

    videos = feed_blueprint._fetch_videos(agent="mentor", category="music", limit=3)

    assert videos == [{"id": "one"}, {"id": "two"}]
    assert calls == [
        (
            "https://api.example.test/api/videos",
            {"per_page": 3, "agent": "mentor", "category": "music"},
            10,
        ),
        ("raise_for_status",),
    ]


def test_fetch_videos_returns_empty_list_when_request_fails(monkeypatch):
    def fake_get(url, params, timeout):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(feed_blueprint.requests, "get", fake_get)

    assert feed_blueprint._fetch_videos() == []
