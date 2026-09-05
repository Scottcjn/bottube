"""Executable accessibility-state regression for the embeddable Sophia widget."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "bottube_static" / "sophia_widget.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_widget_exposes_and_synchronizes_dialog_keyboard_state():
    harness = f"""
const listeners = {{}};
const appended = [];
function element(tag) {{
  const classes = new Set();
  const attributes = {{}};
  const children = [];
  return {{
    tag, id: '', className: '', hidden: false, textContent: '', innerHTML: '', value: '',
    attributes, children, focused: false, scrollTop: 0, scrollHeight: 0,
    classList: {{
      add(name) {{ classes.add(name); }},
      remove(name) {{ classes.delete(name); }},
      contains(name) {{ return classes.has(name); }}
    }},
    setAttribute(name, value) {{ attributes[name] = String(value); }},
    getAttribute(name) {{ return attributes[name] || null; }},
    addEventListener(name, fn) {{ listeners[(this.id || tag) + ':' + name] = fn; }},
    appendChild(child) {{ children.push(child); this.scrollHeight += 1; }},
    focus() {{ this.focused = true; }},
    remove() {{ this.removed = true; }},
    querySelector(selector) {{
      if (selector === '.selya-msgs') return this._msgs;
      if (selector === '.selya-foot input') return this._input;
      if (selector === '.selya-foot button') return this._send;
      if (selector === '.selya-head button') return this._close;
      return null;
    }}
  }};
}}
const scriptTag = {{getAttribute() {{ return null; }}}};
const document = {{
  currentScript: scriptTag,
  head: {{appendChild() {{}}}},
  body: {{appendChild(node) {{ appended.push(node); }}}},
  getElementsByTagName(name) {{ return name === 'script' ? [scriptTag] : []; }},
  createElement(tag) {{
    const node = element(tag);
    if (tag === 'div') {{
      node._msgs = element('msgs');
      node._input = element('input');
      node._send = element('send');
      node._close = element('close');
    }}
    return node;
  }}
}};
global.document = document;
global.window = {{}};
eval({json.dumps(SCRIPT.read_text(encoding='utf-8'))});

const launcher = appended.find(node => node.className === 'selya-btn');
const panel = appended.find(node => node.className === 'selya-panel');
if (!launcher || !panel) throw new Error('widget was not mounted');
const state = {{
  initial: {{
    expanded: launcher.getAttribute('aria-expanded'),
    controls: launcher.getAttribute('aria-controls'),
    hidden: panel.hidden,
    role: panel.getAttribute('role'),
    labelledby: panel.getAttribute('aria-labelledby'),
    hasLog: panel.innerHTML.includes('role="log"') && panel.innerHTML.includes('aria-live="polite"')
  }}
}};
listeners['selya-launcher:click']({{}});
state.open = {{expanded: launcher.getAttribute('aria-expanded'), hidden: panel.hidden, inputFocused: panel._input.focused}};
panel._input.focused = false;
let prevented = false;
listeners['selya-panel:keydown']({{key: 'Escape', preventDefault() {{ prevented = true; }}}});
state.escape = {{expanded: launcher.getAttribute('aria-expanded'), hidden: panel.hidden, launcherFocused: launcher.focused, prevented}};
launcher.focused = false;
listeners['selya-launcher:click']({{}});
listeners['close:click']({{}});
state.closeButton = {{expanded: launcher.getAttribute('aria-expanded'), hidden: panel.hidden, launcherFocused: launcher.focused}};
process.stdout.write(JSON.stringify(state));
"""
    completed = subprocess.run(
        ["node", "-e", harness],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    state = json.loads(completed.stdout)
    assert state["initial"] == {
        "expanded": "false",
        "controls": "selya-panel",
        "hidden": True,
        "role": "dialog",
        "labelledby": "selya-dialog-title",
        "hasLog": True,
    }
    assert state["open"] == {
        "expanded": "true",
        "hidden": False,
        "inputFocused": True,
    }
    assert state["escape"] == {
        "expanded": "false",
        "hidden": True,
        "launcherFocused": True,
        "prevented": True,
    }
    assert state["closeButton"] == {
        "expanded": "false",
        "hidden": True,
        "launcherFocused": True,
    }
