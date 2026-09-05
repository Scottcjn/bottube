# SPDX-License-Identifier: MIT
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_watch_template_uses_safe_tracking_wrapper():
    """Verify the watch template only emits analytics through trackWatchEvent.

    The watch page tracks six lifecycle events (ad_complete, ad_impression,
    video_play, video_progress, video_complete, cast_started). To keep
    CSP and analytics consistent, every tracking call must go through the
    `trackWatchEvent` wrapper which forwards to `window.btTrack`. Direct
    `btTrack(...)` calls in the template are forbidden so the wrapper can
    be the single source of truth for instrumentation.
    """
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
    """Verify Google Cast sender script is whitelisted across CSP sources.

    The watch page loads Google Cast's cast_sender.js from gstatic.com.
    That host must be allowed in (1) the watch template's script-src,
    (2) the base template's CSP, and (3) the server-level CSP set in
    bottube_server.py. If any of the three is missing, the browser
    blocks the script and the Cast button silently fails to initialize.
    """
    base_template = (ROOT / "bottube_templates" / "base.html").read_text()
    server_source = (ROOT / "bottube_server.py").read_text()
    watch_template = (ROOT / "bottube_templates" / "watch.html").read_text()

    assert "https://www.gstatic.com/cv/js/sender/v1/cast_sender.js" in watch_template
    assert "https://www.gstatic.com" in base_template
    assert "https://www.gstatic.com" in server_source
