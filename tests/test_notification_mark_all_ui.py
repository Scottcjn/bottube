"""Runtime regression for notification mark-all response semantics."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "bottube_static" / "base.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
@pytest.mark.parametrize("mark_ok", [False, True])
def test_mark_all_only_clears_unread_state_after_success(mark_ok):
    harness = f"""
const listeners = {{}};
function element(id) {{
  return {{
    id, style: {{display: id === 'notif-badge' ? 'block' : ''}}, textContent: id === 'notif-badge' ? '5' : '',
    innerHTML: 'last-good-list', attributes: {{}},
    setAttribute(name, value) {{ this.attributes[name] = value; }},
    getAttribute(name) {{ return this.attributes[name] || null; }},
    addEventListener(name, fn) {{ listeners[id + ':' + name] = fn; }},
    contains() {{ return true; }}, querySelector() {{ return null; }}
  }};
}}
const elements = {{
  'bell-btn': element('bell-btn'), 'notif-panel': element('notif-panel'),
  'notif-badge': element('notif-badge'), 'notif-list': element('notif-list'),
  'notif-mark-all': element('notif-mark-all')
}};
const wrapper = element('wrapper');
global.window = {{location: {{href: ''}}}};
global.navigator = {{webdriver: false, plugins: [], serviceWorker: null}};
global.screen = {{width: 1, height: 1}};
global.XMLHttpRequest = function() {{ this.open = () => {{}}; this.setRequestHeader = () => {{}}; this.send = () => {{}}; }};
global.setInterval = () => 1;
global.document = {{
  readyState: 'loading',
  getElementById: id => elements[id] || null,
  querySelector: selector => selector === '.notif-wrapper' ? wrapper : null,
  createElement: () => ({{set textContent(value) {{ this.innerHTML = value; }}, innerHTML: ''}}),
  addEventListener: () => {{}}
}};
let markPosts = 0;
global.fetch = async (url, options) => {{
  if (url.endsWith('/api/notifications/unread-count')) return {{ok: true, json: async () => ({{unread: 5}})}};
  if (url.endsWith('/api/notifications/read')) {{
    markPosts += 1;
    return {{ok: {json.dumps(mark_ok)}, status: {200 if mark_ok else 500}, json: async () => ({{ok: true}})}};
  }}
  if (url.endsWith('/api/notifications?per_page=20')) return {{ok: true, json: async () => ({{unread: 0, notifications: []}})}};
  throw new Error('unexpected URL ' + url);
}};
eval({json.dumps(SCRIPT.read_text(encoding='utf-8'))});
setImmediate(() => {{
  const event = {{preventDefault() {{}}}};
  listeners['notif-mark-all:click'](event);
  listeners['notif-mark-all:click'](event);
  setImmediate(() => setImmediate(() => {{
    process.stdout.write(JSON.stringify({{
      display: elements['notif-badge'].style.display,
      text: elements['notif-badge'].textContent,
      disabled: elements['notif-mark-all'].attributes['aria-disabled'],
      markPosts
    }}));
  }}));
}});
"""
    completed = subprocess.run(
        ["node", "-e", harness], check=True, capture_output=True, text=True, timeout=10
    )
    result = json.loads(completed.stdout)
    assert result["markPosts"] == 1
    assert result["disabled"] == "false"
    if mark_ok:
        assert result["display"] == "none"
    else:
        assert result["display"] == "block"
        assert result["text"] == "5"
