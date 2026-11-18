# SPDX-License-Identifier: MIT
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_verify_video_id_input_has_programmatic_label():
    """Verify the video-id input on /verify has a programmatic label.

    Screen readers announce input fields by their associated label. The
    verify page must keep a screen-reader-only <label for=vrf-vid> bound
    to the input so the field is reachable and identified by assistive
    tech instead of being announced as a bare text box.
    """
    template = (ROOT / "bottube_templates" / "verify.html").read_text(encoding="utf-8")

    # The label now uses the shared base.html ``sr-only`` class; assert the
    # binding and a visually-hidden class rather than one exact spelling.
    label = re.search(r'<label\s+for="vrf-vid"\s+class="([^"]*)"\s*>([^<]+)</label>', template)
    assert label, "missing <label for=\"vrf-vid\">"
    assert "sr-only" in label.group(1)
    assert "video id" in label.group(2).lower()
    assert 'id="vrf-vid"' in template


def test_verify_primary_submit_has_descriptive_accessible_name():
    """Verify the primary submit button has a descriptive accessible name.

    The default button text on /verify should be paired with an explicit
    aria-label that says what the action actually does ("Verify video
    provenance"), so screen reader users hear the action verb instead of
    an ambiguous label like "Submit".
    """
    template = (ROOT / "bottube_templates" / "verify.html").read_text(encoding="utf-8")

    assert 'id="vrf-btn" aria-label="Verify video provenance"' in template
