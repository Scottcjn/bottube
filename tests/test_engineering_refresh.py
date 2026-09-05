"""Regression coverage for engineering-dashboard refresh correctness."""

from pathlib import Path
import json
import shutil
import subprocess

import pytest


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "engineering.html"


def _script() -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    return html.rsplit("<script>", 1)[1].split("</script>", 1)[0]


def test_refresh_feedback_is_an_accessible_status():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="eng-tick" role="status" aria-live="polite" aria-atomic="true"' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
@pytest.mark.parametrize(
    ("response", "expected_status", "expected_generated", "expected_node"),
    [
        (
            {"ok": False, "status": 503, "payload": None},
            "refresh failed; retrying in 30s",
            "last-good-time",
            "last-good-node",
        ),
        (
            {"ok": True, "status": 200, "payload": {"nodes": []}},
            "refresh failed; retrying in 30s",
            "last-good-time",
            "last-good-node",
        ),
        (
            {
                "ok": True,
                "status": 200,
                "payload": {
                    "generated_at": "new-time",
                    "nodes": [
                        {"id": "node-1", "location": "Virginia", "status": "ok", "rtt_ms": 12.6}
                    ],
                },
            },
            "updated; refreshing in 30s",
            "new-time",
            "node-1",
        ),
    ],
)
def test_refresh_rejects_bad_responses_before_replacing_last_good_data(
    response, expected_status, expected_generated, expected_node
):
    harness = f"""
const elements = {{
  'eng-tick': {{ textContent: 'initial' }},
  'eng-generated': {{ textContent: 'last-good-time' }},
  'eng-nodes': {{ innerHTML: 'last-good-node' }}
}};
global.document = {{ getElementById: id => elements[id] }};
global.setInterval = () => 1;
const configured = {json.dumps(response)};
global.fetch = async () => ({{
  ok: configured.ok,
  status: configured.status,
  json: async () => configured.payload
}});
eval({json.dumps(_script())});
_engRefresh().then(() => setImmediate(() => {{
  process.stdout.write(JSON.stringify(elements));
}}));
"""
    completed = subprocess.run(
        ["node", "-e", harness], check=True, capture_output=True, text=True, timeout=10
    )
    elements = json.loads(completed.stdout)
    assert elements["eng-tick"]["textContent"] == expected_status
    assert elements["eng-generated"]["textContent"] == expected_generated
    assert expected_node in elements["eng-nodes"]["innerHTML"]
