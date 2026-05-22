import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_watch_template_uses_safe_tracking_wrapper():
    template = (ROOT / "bottube_templates" / "watch.html").read_text()

    assert "function trackWatchEvent(name, data)" in template
    assert "window.btTrack(name, data)" in template
    assert re.search(r"(?<!window\.)\bbtTrack\s*\(", template) is None

    for event_name in [
        "ad_complete",
        "ad_impression",
        "video_play",
        "video_progress",
        "video_complete",
        "cast_started",
    ]:
        assert f"trackWatchEvent('{event_name}'" in template


def test_google_cast_script_is_allowed_by_csp_definitions():
    base_template = (ROOT / "bottube_templates" / "base.html").read_text()
    server_source = (ROOT / "bottube_server.py").read_text()
    watch_template = (ROOT / "bottube_templates" / "watch.html").read_text()

    assert "https://www.gstatic.com/cv/js/sender/v1/cast_sender.js" in watch_template
    assert "https://www.gstatic.com" in base_template
    assert "https://www.gstatic.com" in server_source
