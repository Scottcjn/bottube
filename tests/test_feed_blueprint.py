# SPDX-License-Identifier: MIT
import datetime as dt
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytest
import werkzeug
from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "test"

import feed_blueprint


def test_escape_xml_handles_none_and_all_special_characters():
    """`escape_xml` must null-safe and cover all five XML-reserved characters.

    RSS/Atom output breaks (or becomes injectable) if any one of
    `& < > " '` is left unescaped in title/description text pulled from
    user-controlled video metadata; `None` is included because upstream
    fields are frequently optional.
    """
    assert feed_blueprint.escape_xml(None) == ""
    assert (
        feed_blueprint.escape_xml("Rock & <Roll> \"Mix\" 'Tape'")
        == "Rock &amp; &lt;Roll&gt; &quot;Mix&quot; &apos;Tape&apos;"
    )


def test_timestamp_helpers_normalize_epoch_and_iso_values():
    """RFC 2822 (RSS) and ISO 8601 (Atom) timestamp helpers must agree on the same instant.

    Feeds carry `created_at` in a mix of forms depending on the source
    (numeric epoch, epoch-as-string, or an ISO string with/without a `Z`);
    all three must resolve to the identical UTC instant so RSS and Atom
    readers don't disagree about when a video was published.
    """
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
    """`_normalize_videos` must accept any of the API's response shapes and drop junk entries.

    The upstream videos API has returned results under a bare list,
    `videos`, `items`, or `data` at different times; this locks in support
    for all four AND proves a non-dict entry (a stray string, `None`, or a
    non-list value under the key) is dropped instead of crashing the
    template renderer downstream.
    """
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
    """A video with only an `id` must still render a complete, non-broken feed entry.

    Real entries can be missing title/description/author/category; this
    proves `_vid_fields` fills every field the RSS/Atom templates expect
    with a sane default and derives the thumbnail/stream/watch URLs from
    just the id, rather than leaving template placeholders empty or
    raising a `KeyError`.
    """
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
        ("/feed/rss?limit=1", 1),
        ("/feed/rss?limit=100", 100),
    ],
)
def test_parse_limit_defaults_and_accepts_valid_values(path, expected):
    """No `limit` must default to 20, and any value within [1, 100] must pass through unchanged."""
    app = Flask(__name__)
    with app.test_request_context(path):
        assert feed_blueprint._parse_limit() == expected


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("/feed/rss?limit=0", "limit must be a positive integer"),
        ("/feed/rss?limit=-30", "limit must be a positive integer"),
        ("/feed/rss?limit=101", "limit must be less than or equal to 100"),
        ("/feed/rss?limit=invalid", "limit must be an integer"),
        ("/feed/rss?limit=1.5", "limit must be an integer"),
        ("/feed/rss?limit=", "limit must be an integer"),
    ],
)
def test_parse_limit_rejects_invalid_values(path, message):
    """Zero, negative, over-100, non-integer, and empty `limit` must each raise with a matching, specific message.

    Pinning the exact error text (not just that *a* `ValueError` is
    raised) catches a regression where the check still rejects the value
    but the message stops matching the reason -- e.g. an over-100 value
    reported as "must be an integer" would be confusing and technically
    wrong.
    """
    app = Flask(__name__)
    with app.test_request_context(path), pytest.raises(ValueError, match=message):
        feed_blueprint._parse_limit()


@pytest.mark.parametrize(
    "path",
    [
        "/feed/rss?limit=invalid",
        "/feed/atom?limit=0",
        "/feed/rss/agent-name?limit=-1",
        "/feed/atom/agent-name?limit=101",
    ],
)
def test_feed_routes_reject_invalid_limit_without_fetching_videos(monkeypatch, path):
    """All four feed routes must validate `limit` before ever calling `_fetch_videos`.

    Monkeypatches `_fetch_videos` to raise if it's called at all, so a
    route that validates too late (e.g. after already hitting the
    upstream API) fails loudly here instead of just wasting a request on
    input that was going to be rejected anyway.
    """
    app = Flask(__name__)
    app.register_blueprint(feed_blueprint.feed_bp)

    def fail_fetch_videos(*args, **kwargs):
        """Fail the test if reached, proving invalid-limit routes never call it."""
        raise AssertionError("_fetch_videos should not run for invalid limits")

    monkeypatch.setattr(feed_blueprint, "_fetch_videos", fail_fetch_videos)

    response = app.test_client().get(path)

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_fetch_videos_builds_filtered_request_and_normalizes_response(monkeypatch):
    """`_fetch_videos` must call the upstream API with the right params, check the response, and normalize it.

    Records every call `_fetch_videos` makes (including whether it checked
    the response status) via `calls`, and returns a response shaped like
    real upstream output (including a junk `"skip"` entry) to prove the
    request is built correctly end to end, not just that it returns
    *something*.
    """
    calls = []

    class FakeResponse:
        """A stand-in for `requests.Response` that records status checks and returns canned JSON."""

        def raise_for_status(self):
            """Record that the caller checked for an HTTP error, without actually raising one."""
            calls.append(("raise_for_status",))

        def json(self):
            """Return upstream-shaped JSON including one deliberately invalid entry."""
            return {"items": [{"id": "one"}, "skip", {"id": "two"}]}

    def fake_get(url, params, timeout):
        """Stand in for `requests.get`, recording the exact call args instead of hitting the network."""
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
    """A network failure while fetching videos must degrade to an empty feed, not a 500.

    Feed readers hitting `/feed/rss` during an upstream outage should get
    a valid (if empty) feed rather than an error page, so this locks in
    that `_fetch_videos` swallows the exception instead of letting it
    propagate.
    """
    def fake_get(url, params, timeout):
        """Simulate the upstream API being unreachable."""
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(feed_blueprint.requests, "get", fake_get)

    assert feed_blueprint._fetch_videos() == []


def test_feed_routes_escape_url_attributes_and_cdata(monkeypatch):
    """RSS and Atom output must stay valid, well-formed XML even with hostile field content.

    Feeds a title containing a literal `]]>` (which would prematurely
    close a CDATA section) and a thumbnail URL with `&`/`<` characters,
    then parses the actual response with `ElementTree` -- if escaping is
    wrong anywhere, this fails on the XML parse itself rather than on a
    weaker string-contains check.
    """
    app = Flask(__name__)
    app.register_blueprint(feed_blueprint.feed_bp)

    def fake_fetch_videos(agent=None, category=None, limit=20):
        """Return one video with adversarial title/description/URL content instead of hitting the network."""
        return [
            {
                "video_id": "feedxml01",
                "title": "Feed XML",
                "description": "before ]]> after",
                "agent_name": "creator",
                "category": "music",
                "thumbnail_url": "https://cdn.example.test/thumb.jpg?x=1&y=<bad>",
                "created_at": 0,
            }
        ]

    monkeypatch.setattr(feed_blueprint, "_fetch_videos", fake_fetch_videos)

    client = app.test_client()
    for path in ("/feed/rss", "/feed/atom"):
        response = client.get(path)
        assert response.status_code == 200
        ET.fromstring(response.get_data(as_text=True))
