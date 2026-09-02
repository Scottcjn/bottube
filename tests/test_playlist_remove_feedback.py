"""Executable regressions for playlist-removal result handling."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "playlist.html"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_playlist_removal_gates_mutation_and_reports_results():
    template = TEMPLATE.read_text(encoding="utf-8")
    start = template.index("function setPlaylistStatus")
    end = template.index("</script>", start)
    script = template[start:end]
    harness = f"""
const vm = require('node:vm');
const status = {{hidden: true, dataset: {{}}, textContent: ''}};
const item = {{removed: false, remove() {{ this.removed = true; }}}};
const numbers = [{{textContent: '4'}}, {{textContent: '8'}}];
let fetchCount = 0;
let responseOK = true;
let responsePayload = {{ok: true}};
const sandbox = {{
  prefix: '', plId: 'playlist-1',
  confirm() {{ return true; }},
  _csrfHeaders() {{ return {{'Content-Type': 'application/json'}}; }},
  document: {{
    getElementById(id) {{ return id === 'playlistActionStatus' ? status : null; }},
    querySelector() {{ return item; }},
    querySelectorAll() {{ return numbers; }}
  }},
  fetch() {{
    fetchCount += 1;
    return Promise.resolve({{
      ok: responseOK,
      json() {{ return Promise.resolve(responsePayload); }}
    }});
  }}
}};
vm.createContext(sandbox);
vm.runInContext({json.dumps(script)}, sandbox);

(async () => {{
  const failedButton = {{disabled: false}};
  responseOK = false;
  responsePayload = {{error: 'Removal was rejected'}};
  const firstFailure = sandbox.removeItem('video-1', failedButton);
  sandbox.removeItem('video-1', failedButton);
  await firstFailure;
  const failure = {{
    fetchCount, removed: item.removed, disabled: failedButton.disabled,
    message: status.textContent, isError: status.dataset.error
  }};

  const successButton = {{disabled: false}};
  responseOK = true;
  responsePayload = {{ok: true}};
  await sandbox.removeItem('video-1', successButton);
  const success = {{
    fetchCount, removed: item.removed, disabled: successButton.disabled,
    message: status.textContent, isError: status.dataset.error,
    numbers: numbers.map(n => n.textContent)
  }};
  process.stdout.write(JSON.stringify({{failure, success}}));
}})().catch(err => {{ console.error(err); process.exit(1); }});
"""
    completed = subprocess.run(
        ["node", "-e", harness],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    result = json.loads(completed.stdout)
    assert result["failure"] == {
        "fetchCount": 1,
        "removed": False,
        "disabled": False,
        "message": "Removal was rejected",
        "isError": "true",
    }
    assert result["success"] == {
        "fetchCount": 2,
        "removed": True,
        "disabled": False,
        "message": "Video removed from playlist.",
        "isError": "false",
        "numbers": [1, 2],
    }


def test_playlist_status_is_an_atomic_live_region():
    template = TEMPLATE.read_text(encoding="utf-8")
    status_line = next(
        line for line in template.splitlines() if 'id="playlistActionStatus"' in line
    )
    assert 'role="status"' in status_line
    assert 'aria-live="polite"' in status_line
    assert 'aria-atomic="true"' in status_line
