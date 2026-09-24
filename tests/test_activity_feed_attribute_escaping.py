# SPDX-License-Identifier: MIT
"""Regression for stored attribute injection in the activity feed (bounty #71).

The card builders interpolate user-controlled values (video titles, avatar
URLs, thumbnails) into quoted HTML attributes. The old escapeHtml used the
textContent/innerHTML trick, which does not escape quotes, so a title could
close the attribute and add an event handler.
"""

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


TEMPLATES = Path(__file__).resolve().parents[1] / "bottube_templates"
FEED = TEMPLATES / "activity_feed.html"
DISCOVER = TEMPLATES / "discover.html"

# Anything inside a double-quoted attribute value that interpolates a
# template-literal expression.
ATTR_INTERPOLATION = re.compile(r'[\w-]+="[^"]*\$\{([^}]*)\}[^"]*"')
SAFE_WRAPPERS = ("escapeHtml(", "escapeAttribute(", "encodeURIComponent(")


def _script(path: Path) -> str:
    html = path.read_text(encoding="utf-8")
    return html.split("{% block extra_js %}", 1)[1].split("<script>", 1)[1].split("</script>", 1)[0]


def _card_builders(source: str) -> str:
    start = source.index("function createUploadItem(")
    end = source.index("function escapeHtml(")
    return source[start:end]


def test_every_feed_attribute_interpolation_is_escaped():
    builders = _card_builders(_script(FEED))
    found = ATTR_INTERPOLATION.findall(builders)
    assert found, "expected attribute interpolations in the card builders"
    for expr in found:
        assert expr.strip().startswith(SAFE_WRAPPERS), f"raw attribute interpolation: ${{{expr}}}"


def test_feed_escape_html_is_a_string_escaper_not_textcontent():
    script = _script(FEED)
    body = script.split("function escapeHtml(", 1)[1].split("\n    }", 1)[0]
    assert "textContent" not in body
    assert "&quot;" in body and "&#39;" in body


def test_discover_video_card_attributes_are_escaped():
    script = _script(DISCOVER)
    card = script.split("function createVideoCard(", 1)[1].split("function searchByTag(", 1)[0]
    for expr in ATTR_INTERPOLATION.findall(card):
        assert expr.strip().startswith(SAFE_WRAPPERS), f"raw attribute interpolation: ${{{expr}}}"


HOSTILE_TITLE = 'x" data-injected="1'


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_feed_cards_render_hostile_values_inertly():
    script = _script(FEED)
    harness = f"""
global.document = {{ addEventListener() {{}} }};
eval({json.dumps(script)});
const title = {json.dumps(HOSTILE_TITLE)};
const agent = {{display_name: title, avatar: 'javascript:alert(1)'}};
const out = {{
  upload: createActivityItem({{type: 'upload', agent, formatted_time: title,
    content: {{video_id: 'v1', title, thumbnail: 'a" b.jpg'}}}}),
  comment: createActivityItem({{type: 'comment', agent: {{display_name: 'a', avatar: '//evil.example/a.png'}},
    formatted_time: 't', content: {{text: title, video_title: title, is_reply: false}}}}),
  vote: createActivityItem({{type: 'vote', agent: {{display_name: 'a', avatar: 'https://cdn.example/a.png'}},
    formatted_time: 't', content: {{action: title, video_title: title}}}}),
  tip: createActivityItem({{type: 'tip', from_agent: {{display_name: 'a', avatar: '/avatars/a.png'}},
    to_agent: {{display_name: title}}, formatted_time: 't', content: {{amount: 0, message: title}}}}),
  urls: [safeUrl('javascript:alert(1)', 'F'), safeUrl(' JAVASCRIPT:alert(1)', 'F'),
         safeUrl('data:image/svg+xml,x', 'F'), safeUrl('//evil.example', 'F'),
         safeUrl('/\\\\evil.example', 'F'), safeUrl('/avatars/a.png', 'F'),
         safeUrl('https://cdn.example/a.png', 'F'), safeUrl('', 'F'), safeUrl(null, 'F')],
  esc: escapeHtml('&<>"\\''),
}};
console.log(JSON.stringify(out));
"""
    result = subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True, timeout=30)
    out = json.loads(result.stdout)

    assert out["esc"] == "&amp;&lt;&gt;&quot;&#39;"
    assert out["urls"] == [
        "F", "F", "F", "F", "F",
        "/avatars/a.png", "https://cdn.example/a.png", "F", "F",
    ]

    for kind in ("upload", "comment", "vote", "tip"):
        html = out[kind]
        assert 'data-injected="' not in html, kind
        assert "javascript:" not in html, kind

    assert 'alt="Video thumbnail: x&quot; data-injected=&quot;1"' in out["upload"]
    assert 'src="/static/icon-192.png"' in out["upload"]
    assert 'src="/thumbnails/a%22%20b.jpg"' in out["upload"]
    assert 'src="/static/icon-192.png"' in out["comment"]
    assert 'src="https://cdn.example/a.png"' in out["vote"]
    assert 'src="/avatars/a.png"' in out["tip"]
    assert '<span class="tip-amount">0 RTC</span>' in out["tip"]
