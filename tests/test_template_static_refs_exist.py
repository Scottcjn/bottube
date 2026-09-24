# SPDX-License-Identifier: MIT
"""Every literal /static/... path in these templates must exist on disk.

Follow-up to #2308: the activity feed and discover page pointed their image
fallbacks at /static/default-avatar.png and /static/default-thumb.jpg, which
were never committed, so every fallback 404'd in production. Flask serves
/static from bottube_static/ (see STATIC_DIR in bottube_server.py).
"""

from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "bottube_static"
TEMPLATES = ROOT / "bottube_templates"
CHECKED = ("activity_feed.html", "discover.html")

STATIC_REF = re.compile(r"""/static/([^"'`\s()?#]+)""")


def _refs(name: str) -> list[str]:
    return STATIC_REF.findall((TEMPLATES / name).read_text(encoding="utf-8"))


def test_static_dir_matches_flask_config():
    server = (ROOT / "bottube_server.py").read_text(encoding="utf-8")
    assert 'STATIC_DIR = BASE_DIR / "bottube_static"' in server
    assert 'static_url_path="/static"' in server


@pytest.mark.parametrize("name", CHECKED)
def test_template_static_refs_exist(name):
    refs = _refs(name)
    assert refs, f"expected {name} to reference at least one /static asset"
    missing = sorted({r for r in refs if not (STATIC_DIR / r).is_file()})
    assert not missing, f"{name} references missing static files: {missing}"
