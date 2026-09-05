"""Executable regressions for anchor-detail chain response handling."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "anchor_detail.html"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_anchor_verdict_requires_http_success_and_complete_root():
    template = TEMPLATE.read_text(encoding="utf-8")
    start = template.index("(function () {")
    end = template.index("</script>", start)
    script = template[start:end].replace("{{ batch.manifest_hash }}", "root-abc")
    harness = f"""
const vm = require('node:vm');
const source = {json.dumps(script)};

async function run(httpOK, httpStatus, payload) {{
  const ids = ['chain-status', 'chain-rows', 'chain-r4-raw', 'chain-r4-merkle',
    'chain-match', 'chain-confs', 'chain-incl', 'chain-value', 'chain-tree'];
  const elements = Object.fromEntries(ids.map(id => [id, {{textContent: '', style: {{display: id === 'chain-rows' ? 'none' : ''}}}}]));
  const sandbox = {{
    document: {{getElementById(id) {{ return elements[id]; }}}},
    fetch() {{
      return Promise.resolve({{
        ok: httpOK, status: httpStatus,
        json() {{ return Promise.resolve(payload); }}
      }});
    }}
  }};
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  return {{
    status: elements['chain-status'].textContent,
    rows: elements['chain-rows'].style.display,
    confirmations: elements['chain-confs'].textContent,
    value: elements['chain-value'].textContent,
    tree: elements['chain-tree'].textContent
  }};
}}

(async () => {{
  const incomplete = await run(true, 200, {{ok: true}});
  const failed = await run(false, 503, {{ok: true, r4_merkle_root: 'root-abc'}});
  const complete = await run(true, 200, {{
    ok: true,
    r4_merkle_root: 'root-abc',
    num_confirmations: 7,
    anchor_value_nanoerg: 1250000000
  }});
  process.stdout.write(JSON.stringify({{incomplete, failed, complete}}));
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
    assert result["incomplete"] == {
        "status": "chain response incomplete",
        "rows": "none",
        "confirmations": "",
        "value": "",
        "tree": "",
    }
    assert result["failed"]["status"] == "chain request failed (503)"
    assert result["failed"]["rows"] == "none"
    assert result["complete"] == {
        "status": "✓ root matches bottube's claim",
        "rows": "block",
        "confirmations": 7,
        "value": "1.250000 ERG",
        "tree": "—",
    }


def test_chain_verdict_is_an_atomic_live_status():
    template = TEMPLATE.read_text(encoding="utf-8")
    status_line = next(
        line for line in template.splitlines() if 'id="chain-status"' in line
    )
    assert 'role="status"' in status_line
    assert 'aria-live="polite"' in status_line
    assert 'aria-atomic="true"' in status_line
