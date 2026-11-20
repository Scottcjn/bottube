# SPDX-License-Identifier: MIT
"""Chapter markers parsed from the video description.

Covers the pure parser (``video_chapters.parse_chapters``), the JSON-LD
``hasPart`` builder, the public ``GET /api/videos/<id>/chapters`` endpoint and
the chapter panel rendered on the watch page.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_chapters import (  # noqa: E402
    MAX_TITLE_LEN,
    chapters_to_jsonld,
    format_timestamp,
    parse_chapters,
    parse_timestamp,
)

DESCRIPTION = """Boot sequence on the S824, narrated by Boris.

0:00 Intro
0:12 The POWER8 boots
1:05 Closing thoughts

Filmed on vintage hardware. #powerpc"""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def test_parse_timestamp_accepts_all_three_shapes():
    assert parse_timestamp("0:00") == 0
    assert parse_timestamp("12:34") == 754
    assert parse_timestamp("1:05:30") == 3930


@pytest.mark.parametrize("bad", ["", "12", "1:60", "1:99:00", "a:bc", "1:2:3:4", None])
def test_parse_timestamp_rejects_malformed(bad):
    assert parse_timestamp(bad) is None


def test_format_timestamp_round_trips():
    assert format_timestamp(0) == "0:00"
    assert format_timestamp(754) == "12:34"
    assert format_timestamp(3930) == "1:05:30"
    assert format_timestamp(None) == "0:00"
    assert format_timestamp(-5) == "0:00"


def test_parse_chapters_basic_list_with_duration():
    chapters = parse_chapters(DESCRIPTION, duration_sec=90)
    assert [c["title"] for c in chapters] == ["Intro", "The POWER8 boots", "Closing thoughts"]
    assert [c["start_sec"] for c in chapters] == [0, 12, 65]
    # each chapter ends where the next begins; the last ends at the duration
    assert [c["end_sec"] for c in chapters] == [12, 65, 90]
    assert [c["label"] for c in chapters] == ["0:00", "0:12", "1:05"]
    assert [c["index"] for c in chapters] == [0, 1, 2]


def test_parse_chapters_unknown_duration_leaves_last_end_open():
    chapters = parse_chapters(DESCRIPTION, duration_sec=None)
    assert chapters[-1]["end_sec"] is None
    assert chapters[0]["end_sec"] == 12


@pytest.mark.parametrize("duration", [0, -1, "not a number"])
def test_parse_chapters_treats_bad_duration_as_unknown(duration):
    chapters = parse_chapters(DESCRIPTION, duration_sec=duration)
    assert len(chapters) == 3
    assert chapters[-1]["end_sec"] is None


def test_parse_chapters_accepts_bullets_brackets_and_separators():
    text = "\n".join([
        "- 0:00 - Intro",
        "* [0:10] Setup",
        "• (0:20): Demo",
        "> 0:30 | Outro",
    ])
    chapters = parse_chapters(text, duration_sec=60)
    assert [c["title"] for c in chapters] == ["Intro", "Setup", "Demo", "Outro"]
    assert [c["start_sec"] for c in chapters] == [0, 10, 20, 30]


def test_parse_chapters_requires_at_least_two_lines():
    # A lone timestamp in prose is not a chapter list.
    assert parse_chapters("Watch the explosion at 0:42, it is great.", 60) == []
    assert parse_chapters("0:00 Whole video", 60) == []


def test_parse_chapters_ignores_inline_timestamps_in_prose():
    text = "See 0:42 for the good part.\n0:00 Intro\n0:30 Middle"
    chapters = parse_chapters(text, duration_sec=60)
    assert [c["title"] for c in chapters] == ["Intro", "Middle"]


def test_parse_chapters_stops_at_first_out_of_order_line():
    text = "0:00 A\n0:20 B\n0:10 C\n0:40 D"
    chapters = parse_chapters(text, duration_sec=60)
    assert [c["title"] for c in chapters] == ["A", "B"]


def test_parse_chapters_duplicate_start_ends_list():
    text = "0:00 A\n0:10 B\n0:10 B again\n0:20 C"
    chapters = parse_chapters(text, duration_sec=60)
    assert [c["title"] for c in chapters] == ["A", "B"]


def test_parse_chapters_drops_chapters_past_duration():
    text = "0:00 A\n0:05 B\n0:30 Beyond the end"
    chapters = parse_chapters(text, duration_sec=8)
    assert [c["title"] for c in chapters] == ["A", "B"]
    assert chapters[-1]["end_sec"] == 8


def test_parse_chapters_does_not_require_zero_start():
    # Lenient on purpose: agents often skip the 0:00 line.
    text = "0:05 First\n0:10 Second"
    chapters = parse_chapters(text, duration_sec=20)
    assert [c["start_sec"] for c in chapters] == [5, 10]


def test_parse_chapters_truncates_long_titles():
    long_title = "x" * (MAX_TITLE_LEN + 40)
    text = f"0:00 {long_title}\n0:10 Short"
    chapters = parse_chapters(text, duration_sec=20)
    assert len(chapters[0]["title"]) == MAX_TITLE_LEN
    assert chapters[0]["title"].endswith("…")


def test_parse_chapters_handles_empty_and_none():
    assert parse_chapters(None, 10) == []
    assert parse_chapters("", 10) == []
    assert parse_chapters("just prose\nno chapters here", 10) == []


def test_parse_chapters_windows_line_endings():
    text = "0:00 A\r\n0:10 B\r\n"
    assert [c["title"] for c in parse_chapters(text, 20)] == ["A", "B"]


# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------

def test_chapters_to_jsonld_builds_clip_parts_with_seek_urls():
    chapters = parse_chapters(DESCRIPTION, duration_sec=90)
    parts = chapters_to_jsonld("abc123", chapters)
    assert len(parts) == 3
    assert parts[0] == {
        "@type": "Clip",
        "name": "Intro",
        "startOffset": 0,
        "endOffset": 12,
        "url": "https://bottube.ai/watch/abc123?t=0",
    }
    assert parts[-1]["endOffset"] == 90
    assert parts[-1]["url"].endswith("?t=65")


def test_chapters_to_jsonld_omits_open_ended_clip():
    # endOffset is required by schema.org, so an unknown end is left out.
    chapters = parse_chapters(DESCRIPTION, duration_sec=None)
    parts = chapters_to_jsonld("abc123", chapters)
    assert [p["name"] for p in parts] == ["Intro", "The POWER8 boots"]


# ---------------------------------------------------------------------------
# HTTP + watch page (uses the shared ``app``/``client`` fixtures in conftest)
# ---------------------------------------------------------------------------

def _insert_video(app, video_id, *, description, duration_sec=90, banned=False, removed=False):
    import bottube_server  # fresh module installed by the ``app`` fixture

    with app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """INSERT INTO agents
                   (agent_name, display_name, api_key, password_hash, bio,
                    avatar_url, created_at, last_active, is_banned)
               VALUES (?, ?, ?, '', '', '', 1.0, 1.0, ?)""",
            (f"chapters-{video_id}", "Chapters Agent", f"key-{video_id}", 1 if banned else 0),
        )
        agent_id = int(cur.lastrowid)
        db.execute(
            """INSERT INTO videos
                   (video_id, agent_id, title, filename, description, duration_sec,
                    created_at, is_removed)
               VALUES (?, ?, ?, ?, ?, ?, 1.0, ?)""",
            (video_id, agent_id, "Chapters Test", f"{video_id}.mp4",
             description, duration_sec, 1 if removed else 0),
        )
        db.commit()


def test_chapters_endpoint_returns_parsed_chapters(app, client):
    _insert_video(app, "chapVid01", description=DESCRIPTION, duration_sec=90)
    resp = client.get("/api/videos/chapVid01/chapters")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["video_id"] == "chapVid01"
    assert data["source"] == "description"
    assert data["count"] == 3
    assert [c["title"] for c in data["chapters"]] == ["Intro", "The POWER8 boots", "Closing thoughts"]
    assert data["chapters"][1]["url"] == "https://bottube.ai/watch/chapVid01?t=12"
    assert data["chapters"][-1]["end_sec"] == 90
    assert "max-age" in resp.headers.get("Cache-Control", "")


def test_chapters_endpoint_empty_list_when_no_chapters(app, client):
    _insert_video(app, "chapVid02", description="Just a plain description.")
    resp = client.get("/api/videos/chapVid02/chapters")
    assert resp.status_code == 200
    assert resp.get_json() == {
        "video_id": "chapVid02",
        "source": "description",
        "count": 0,
        "chapters": [],
    }


def test_chapters_endpoint_404_for_unknown_removed_or_banned(app, client):
    assert client.get("/api/videos/doesNotExist/chapters").status_code == 404

    _insert_video(app, "chapVid03", description=DESCRIPTION, removed=True)
    assert client.get("/api/videos/chapVid03/chapters").status_code == 404

    _insert_video(app, "chapVid04", description=DESCRIPTION, banned=True)
    assert client.get("/api/videos/chapVid04/chapters").status_code == 404


def test_watch_page_renders_chapter_panel_and_jsonld(app, client):
    _insert_video(app, "chapVid05", description=DESCRIPTION, duration_sec=90)
    resp = client.get("/watch/chapVid05")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'id="chapters-panel"' in html
    assert "Chapters (3)" in html
    assert 'data-chapter-start="12"' in html
    assert 'aria-label="Jump to 0:12, The POWER8 boots"' in html
    # Key-moments JSON-LD lives inside the VideoObject block
    assert '"hasPart":' in html
    assert '"startOffset": 12' in html
    assert '"endOffset": 65' in html
    assert "https://bottube.ai/watch/chapVid05?t=65" in html


def test_watch_page_omits_panel_without_chapters(app, client):
    _insert_video(app, "chapVid06", description="No chapters, just words.")
    resp = client.get("/watch/chapVid06")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="chapters-panel"' not in html
    assert '"hasPart":' not in html


def test_watch_page_escapes_chapter_titles(app, client):
    hostile = '0:00 <script>alert(1)</script>\n0:10 "quoted" & <b>bold</b>'
    _insert_video(app, "chapVid07", description=hostile, duration_sec=30)
    resp = client.get("/watch/chapVid07")
    html = resp.get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    # JSON-LD uses tojson, which escapes < > & so the script tag cannot close
    assert "\\u003cscript\\u003e" in html
