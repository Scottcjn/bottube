"""Executable regressions for Studio asynchronous job polling."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "studio.html"


def _poll_source():
    template = TEMPLATE.read_text(encoding="utf-8")
    start = template.index("function poll(url)")
    marker = "\n  }\n})();"
    end = template.index(marker, start) + len("\n  }")
    return template[start:end]


def _run_node(payload):
    source = _poll_source()
    harness = f"""
const vm = require('node:vm');
const outcomes = {json.dumps(payload)};
const messages = [];
const busy = [];
let cleared = false;

const sandbox = {{
  resultEl: {{innerHTML: ''}},
  say(message) {{ messages.push(message); }},
  setBusy(value) {{ busy.push(value); }},
  setInterval(callback) {{ sandbox._tick = callback; return 42; }},
  clearInterval(id) {{ if (id !== 42) throw new Error('wrong interval'); cleared = true; }},
  fetch() {{
    const outcome = outcomes.shift();
    if (!outcome) throw new Error('unexpected poll');
    if (outcome.kind === 'network') return Promise.reject(new Error('offline'));
    return Promise.resolve({{
      ok: outcome.ok,
      status: outcome.status,
      json() {{
        if (outcome.kind === 'nonjson') return Promise.reject(new Error('not json'));
        return Promise.resolve(outcome.body);
      }}
    }});
  }}
}};
vm.createContext(sandbox);
vm.runInContext({json.dumps(source)}, sandbox);
sandbox.poll('/jobs/one');

(async () => {{
  const snapshots = [];
  while (outcomes.length) {{
    await sandbox._tick();
    snapshots.push({{
      message: messages[messages.length - 1] || '',
      cleared,
      busy: busy.slice(),
      result: sandbox.resultEl.innerHTML
    }});
  }}
  process.stdout.write(JSON.stringify({{snapshots, messages, busy, cleared}}));
}})().catch(err => {{ console.error(err); process.exit(1); }});
"""
    completed = subprocess.run(
        ["node", "-e", harness],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    return json.loads(completed.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_poll_recovers_then_stops_after_three_new_consecutive_failures():
    result = _run_node(
        [
            {"kind": "nonjson", "ok": False, "status": 503},
            {"kind": "json", "ok": True, "status": 200, "body": {"status": "queued"}},
            {"kind": "network"},
            {"kind": "json", "ok": True, "status": 200, "body": []},
            {"kind": "json", "ok": False, "status": 502, "body": {"error": "gateway"}},
        ]
    )
    snapshots = result["snapshots"]
    assert snapshots[0]["message"] == "Job status temporarily unavailable (HTTP 503; retry 1/3)."
    assert snapshots[0]["cleared"] is False
    assert snapshots[1]["message"] == "Generating… (queued)"
    assert snapshots[2]["message"] == "Job status temporarily unavailable (network error; retry 1/3)."
    assert snapshots[3]["message"] == "Job status temporarily unavailable (invalid response; retry 2/3)."
    assert snapshots[4]["message"] == (
        "Job status is unavailable after 3 attempts. Your generation may still be running; "
        "check your channel before starting another charge."
    )
    assert snapshots[4]["cleared"] is True
    assert snapshots[4]["busy"] == [False]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_poll_finishes_a_valid_completed_video_response():
    result = _run_node(
        [
            {
                "kind": "json",
                "ok": True,
                "status": 200,
                "body": {"status": "completed", "video_id": "vid123"},
            }
        ]
    )
    assert result["cleared"] is True
    assert result["busy"] == [False]
    assert result["messages"] == ["🎬 Done! <a href='/watch/vid123'>Watch your video →</a>"]


def test_studio_status_is_an_atomic_live_region():
    template = TEMPLATE.read_text(encoding="utf-8")
    status_line = next(
        line for line in template.splitlines() if 'id="st-status"' in line
    )
    assert 'role="status"' in status_line
    assert 'aria-live="polite"' in status_line
    assert 'aria-atomic="true"' in status_line
