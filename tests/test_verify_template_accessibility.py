# SPDX-License-Identifier: MIT
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_verify_video_id_input_has_programmatic_label():
    template = (ROOT / "bottube_templates" / "verify.html").read_text(encoding="utf-8")

    assert '<label for="vrf-vid" class="vrf-sr-only">Video ID</label>' in template
    assert 'id="vrf-vid"' in template


def test_verify_primary_submit_has_descriptive_accessible_name():
    template = (ROOT / "bottube_templates" / "verify.html").read_text(encoding="utf-8")

    assert 'id="vrf-btn" aria-label="Verify video provenance"' in template
