"""Executable regressions for channel/watch subscribe result handling."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHANNEL = ROOT / "bottube_templates" / "channel.html"
WATCH = ROOT / "bottube_templates" / "watch.html"


def _function_source(path, name, next_name=None):
    template = path.read_text(encoding="utf-8")
    start = template.index(f"function {name}()")
    if next_name:
        end = template.index(f"function {next_name}()", start)
    else:
        end = template.index("</script>", start)
    return template[start:end]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
@pytest.mark.parametrize(
    ("path", "function_name", "next_name", "button_id", "status_id", "count_id"),
    [
        (CHANNEL, "toggleSubscribe", None, "subscribe-btn", "subscribe-status", "sub-count"),
        (WATCH, "toggleWatchSubscribe", "postComment", "watch-sub-btn", "watch-sub-status", "watch-sub-count"),
    ],
)
def test_subscribe_handlers_preserve_state_and_report_every_outcome(
    path, function_name, next_name, button_id, status_id, count_id
):
    source = _function_source(path, function_name, next_name)
    harness = f"""
const vm = require('node:vm');
const source = {json.dumps(source)};

async function run(mode) {{
  const attrs = {{}};
  const elements = {{
    {json.dumps(button_id)}: {{
      disabled: false, textContent: 'Subscribe', className: 'not-following',
      setAttribute(name, value) {{ attrs[name] = value; }}
    }},
    {json.dumps(status_id)}: {{textContent: '', style: {{color: ''}}}},
    {json.dumps(count_id)}: {{textContent: '10'}}
  }};
  const sandbox = {{
    document: {{getElementById(id) {{ return elements[id] || null; }}}},
    window: {{location: {{href: ''}}}},
    prefix: '', agentName: 'creator', uploaderAgent: 'creator',
    _csrfHeaders() {{ return {{'Content-Type': 'application/json'}}; }},
    fetch() {{
      if (mode === 'network') return Promise.reject(new Error('offline'));
      if (mode === 'nonjson') return Promise.resolve({{
        ok: false, status: 502, json() {{ return Promise.reject(new Error('not json')); }}
      }});
      if (mode === 'api') return Promise.resolve({{
        ok: false, status: 409, json() {{ return Promise.resolve({{ok: false, error: 'Already changed'}}); }}
      }});
      return Promise.resolve({{
        ok: true, status: 200,
        json() {{ return Promise.resolve({{ok: true, following: true, subscriber_count: 11}}); }}
      }});
    }}
  }};
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  await sandbox[{json.dumps(function_name)}]();
  const button = elements[{json.dumps(button_id)}];
  return {{
    text: button.textContent, className: button.className, disabled: button.disabled,
    count: elements[{json.dumps(count_id)}].textContent,
    status: elements[{json.dumps(status_id)}].textContent,
    pressed: attrs['aria-pressed'], label: attrs['aria-label']
  }};
}}

(async () => {{
  const success = await run('success');
  const api = await run('api');
  const nonjson = await run('nonjson');
  const network = await run('network');
  process.stdout.write(JSON.stringify({{success, api, nonjson, network}}));
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
    result = json.loads(completed.stdout)

    assert result["success"] == {
        "text": "Following",
        "className": "subscribe-btn following" if path == CHANNEL else "watch-sub-btn following",
        "disabled": False,
        "count": 11,
        "status": "Subscription confirmed.",
        "pressed": "true",
        "label": "Unfollow this channel",
    }
    for outcome in ("api", "nonjson", "network"):
        assert result[outcome]["text"] == "Subscribe"
        assert result[outcome]["className"] == "not-following"
        assert result[outcome]["disabled"] is False
        assert result[outcome]["count"] == "10"
        assert "pressed" not in result[outcome]
        assert "label" not in result[outcome]
    assert result["api"]["status"] == "Already changed"
    assert result["nonjson"]["status"] == "Subscription failed (502)."
    assert result["network"]["status"] == "Subscription failed. Check your connection and try again."


def test_subscribe_results_are_atomic_live_statuses():
    for path, status_id in ((CHANNEL, "subscribe-status"), (WATCH, "watch-sub-status")):
        template = path.read_text(encoding="utf-8")
        status_line = next(
            line for line in template.splitlines() if f'id="{status_id}"' in line
        )
        assert 'role="status"' in status_line
        assert 'aria-live="polite"' in status_line
        assert 'aria-atomic="true"' in status_line
