"""Executable regressions for Beacon Atlas partial data-source failures."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "beacon_atlas.html"


def _loader_script() -> str:
    script = TEMPLATE.read_text(encoding="utf-8").rsplit("<script>", 1)[1].split("</script>", 1)[0]
    return script.split("(async function()", 1)[0]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
@pytest.mark.parametrize(
    ("responses", "expected"),
    [
        (
            {
                "/api/beacon/directory": {"ok": True, "status": 200, "payload": {"beacons": [{"agent_name": "atlas"}]}},
                "/api/agents?limit=100&sort=popular": {"ok": False, "status": 503, "payload": None},
            },
            {"outcome": "resolved", "beacons": 1, "agents": 0, "calls": 2, "json_calls": 1},
        ),
        (
            {
                "/api/beacon/directory": {"ok": False, "status": 502, "payload": None},
                "/api/agents?limit=100&sort=popular": {"ok": True, "status": 200, "payload": {"agents": []}},
            },
            {"outcome": "rejected", "calls": 2, "json_calls": 1},
        ),
        (
            {
                "/api/beacon/directory": {"ok": True, "status": 200, "payload": {"beacons": [{"agent_name": "atlas"}]}},
                "/api/agents?limit=100&sort=popular": {"ok": True, "status": 200, "payload": {"agents": [{"agent_name": "one"}]}},
                "/api/agents?limit=100&page=2&sort=popular": {"ok": True, "status": 200, "payload": {"agents": [{"agent_name": "two"}]}},
                "/api/agents?limit=100&page=3&sort=popular": {"ok": False, "status": 500, "payload": None},
            },
            {"outcome": "resolved", "beacons": 1, "agents": 2, "calls": 4, "json_calls": 3},
        ),
    ],
)
def test_required_and_optional_atlas_sources_have_distinct_failure_semantics(responses, expected):
    harness = f"""
const configured = {json.dumps(responses)};
let calls = 0;
let jsonCalls = 0;
global.fetch = async url => {{
  calls += 1;
  const item = configured[url];
  if (!item) throw new Error('unexpected URL ' + url);
  return {{
    ok: item.ok,
    status: item.status,
    json: async () => {{ jsonCalls += 1; return item.payload; }}
  }};
}};
eval({json.dumps(_loader_script())});
_atlasLoadDirectoryData().then(data => {{
  process.stdout.write(JSON.stringify({{
    outcome: 'resolved', beacons: data.beacons.length, agents: data.agents.length,
    calls, json_calls: jsonCalls
  }}));
}}).catch(() => {{
  process.stdout.write(JSON.stringify({{outcome: 'rejected', calls, json_calls: jsonCalls}}));
}});
"""
    completed = subprocess.run(
        ["node", "-e", harness], check=True, capture_output=True, text=True, timeout=10
    )
    assert json.loads(completed.stdout) == expected
