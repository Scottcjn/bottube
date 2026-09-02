# SPDX-License-Identifier: MIT
import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "bottube_templates" / "analytics.html"


def _analytics_script():
    html = TEMPLATE.read_text(encoding="utf-8")
    marker = "    // Fetch summary stats"
    start = html.index(marker)
    declaration_start = html.rfind("<script>", 0, start) + len("<script>")
    end = html.index("</script>", start)
    return html[declaration_start:end]


def test_latest_period_response_remains_rendered_when_requests_finish_out_of_order():
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for the analytics browser regression")

    script = _analytics_script()
    harness = f"""
const vm = require('vm');
const assert = require('assert');

const pending = new Map();
const fetch = url => new Promise(resolve => pending.set(url, resolve));
const charts = [];
const tbody = {{ innerHTML: '' }};
const chartContainer = {{
  innerHTML: '',
  querySelector: () => ({{}}),
}};
const document = {{
  addEventListener: () => {{}},
  querySelectorAll: () => [],
  createElement: () => ({{ textContent: '', innerHTML: '' }}),
  getElementById: id => id === 'viewsChart'
    ? chartContainer
    : id === 'engagementTable'
      ? {{ querySelector: () => tbody }}
      : {{ textContent: '' }},
}};
function Chart(_canvas, config) {{ charts.push(config.data.labels[0]); }}
const context = {{ console, document, fetch, Chart }};
vm.createContext(context);
vm.runInContext({json.dumps(script)}, context);

async function settle() {{
  await Promise.resolve();
  await new Promise(resolve => setImmediate(resolve));
}}

(async () => {{
  const oldViews = context.loadViewsChart('7d');
  const newViews = context.loadViewsChart('90d');
  pending.get('/analytics/api/views?period=90d')({{
    json: async () => ({{ daily_breakdown: [{{ date: 'new-90d', views: 90 }}] }}),
  }});
  await settle();
  pending.get('/analytics/api/views?period=7d')({{
    json: async () => ({{ daily_breakdown: [{{ date: 'stale-7d', views: 7 }}] }}),
  }});
  await Promise.all([oldViews, newViews]);
  assert.deepStrictEqual(charts, ['new-90d']);

  const oldEngagement = context.loadEngagement('7d');
  const newEngagement = context.loadEngagement('90d');
  pending.get('/analytics/api/engagement?period=90d')({{
    json: async () => ({{
      by_video: [{{ title: 'new-90d', comments: 9, votes: 0, tips: 0 }}],
    }}),
  }});
  await settle();
  const newestMarkup = tbody.innerHTML;
  pending.get('/analytics/api/engagement?period=7d')({{
    json: async () => ({{
      by_video: [{{ title: 'stale-7d', comments: 7, votes: 0, tips: 0 }}],
    }}),
  }});
  await Promise.all([oldEngagement, newEngagement]);
  assert.match(newestMarkup, /<td>9<[/]td>/);
  assert.strictEqual(tbody.innerHTML, newestMarkup);
  assert.doesNotMatch(tbody.innerHTML, /<td>7<[/]td>/);
}})().catch(error => {{
  console.error(error);
  process.exit(1);
}});
"""

    result = subprocess.run(
        ["node", "-e", harness],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_initial_requests_match_the_visible_active_period():
    script = _analytics_script()

    assert "loadViewsChart('7d');" in script
    assert "loadEngagement('7d');" in script
    assert "loadViewsChart('30d');" not in script
    assert "loadEngagement('30d');" not in script
