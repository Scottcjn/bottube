"""Executable regression for Discover tab selection and keyboard behavior."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "discover.html"


def test_tabs_and_panels_have_complete_relationships():
    html = TEMPLATE.read_text(encoding="utf-8")
    for name, panel in (
        ("trending", "trendingSection"),
        ("foryou", "foryouSection"),
        ("agents", "agentsSection"),
        ("categories", "categoriesGrid"),
        ("tags", "tagsCloud"),
    ):
        assert f'id="discover-tab-{name}"' in html
        assert f'aria-controls="{panel}"' in html
        assert f'id="{panel}" role="tabpanel" aria-labelledby="discover-tab-{name}"' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_click_and_keyboard_paths_keep_exactly_one_selected_tab():
    html = TEMPLATE.read_text(encoding="utf-8")
    script = html.split("{% block extra_js %}", 1)[1].split("<script>", 1)[1].split("</script>", 1)[0]
    harness = f"""
const calls = [];
function classList() {{
  const values = new Set();
  return {{toggle(name, on) {{ on ? values.add(name) : values.delete(name); }}, contains: name => values.has(name)}};
}}
const specs = [
  ['trending', 'trendingSection'], ['foryou', 'foryouSection'], ['agents', 'agentsSection'],
  ['categories', 'categoriesGrid'], ['tags', 'tagsCloud']
];
const tabs = specs.map(([filter, panel]) => ({{
  dataset: {{filter, panel}}, attributes: {{}}, classList: classList(), focused: false,
  setAttribute(name, value) {{ this.attributes[name] = value; }},
  addEventListener() {{}}, focus() {{ this.focused = true; }}
}}));
const panels = Object.fromEntries(specs.map(([, panel]) => [panel, {{style: {{display: ''}}}}]));
const searchInput = {{addEventListener() {{}}, value: ''}};
global.document = {{
  addEventListener() {{}},
  querySelectorAll: selector => selector === '.filter-tab' ? tabs : [],
  getElementById: id => id === 'searchInput' ? searchInput : panels[id]
}};
eval({json.dumps(script)});
loadTrending = () => calls.push('trending');
loadForYou = () => calls.push('foryou');
loadAgents = () => calls.push('agents');
showCategories = () => {{ panels.categoriesGrid.style.display = 'block'; calls.push('categories'); }};
showTags = () => {{ panels.tagsCloud.style.display = 'flex'; calls.push('tags'); }};
activateDiscoverTab(tabs[1]);
handleDiscoverTabKeydown({{key: 'End', preventDefault() {{ calls.push('prevented'); }}}}, tabs[1]);
process.stdout.write(JSON.stringify({{
  selected: tabs.map(tab => tab.attributes['aria-selected']),
  tabstops: tabs.map(tab => tab.attributes.tabindex),
  displays: Object.fromEntries(Object.entries(panels).map(([id, panel]) => [id, panel.style.display])),
  focused: tabs.map(tab => tab.focused), calls
}}));
"""
    completed = subprocess.run(
        ["node", "-e", harness], check=True, capture_output=True, text=True, timeout=10
    )
    result = json.loads(completed.stdout)
    assert result["selected"] == ["false", "false", "false", "false", "true"]
    assert result["tabstops"] == ["-1", "-1", "-1", "-1", "0"]
    assert result["displays"]["tagsCloud"] == "flex"
    assert all(value == "none" for key, value in result["displays"].items() if key != "tagsCloud")
    assert result["focused"] == [False, False, False, False, True]
    assert result["calls"] == ["foryou", "prevented", "tags"]
