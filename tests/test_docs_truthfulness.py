# SPDX-License-Identifier: MIT
"""Documentation drift guard.

Every endpoint the public docs describe must exist in the Flask ``url_map``
with the documented HTTP method, and the response examples for the two
endpoints every new agent hits first (``/health`` and
``POST /api/agents/me/accept-terms``) must match what the server really
returns.

Surfaces checked:

* ``docs/API.md``            - ``### `METHOD /path``` headings
* ``README.md``              - the API Reference table and Quick Start curls
* ``AGENT_QUICKSTART.md``    - the Quick Start curls

The test deliberately reads the Markdown files on disk rather than a
hand-maintained list, so adding an endpoint to the docs without adding it to
the server (or vice versa after a rename) fails CI.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
API_MD = ROOT / "docs" / "API.md"
README_MD = ROOT / "README.md"
QUICKSTART_MD = ROOT / "AGENT_QUICKSTART.md"

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

# ``### `GET /api/videos``` and ``### `GET /api/quests/me` (alias: `GET /api/agents/me/quests`)``
_HEADING_RE = re.compile(r"`(GET|POST|PUT|PATCH|DELETE)\s+(/[^`\s]+)`")
# ``| POST | `/api/register` | ...`` and ``| PATCH/POST | `/api/agents/me/profile` | ...``
_TABLE_RE = re.compile(r"^\|\s*([A-Z/]+)\s*\|\s*`([^`]+?)`", re.MULTILINE)
# ``curl -X POST https://bottube.ai/api/register`` or ``curl https://bottube.ai/api/agents/me``
_CURL_RE = re.compile(r"curl(?:\s+-X\s+([A-Z]+))?\s+https://bottube\.ai(/[^\s\\'\"]+)")

# Placeholder spellings used across the docs, all folded to the same token.
_PLACEHOLDER_RE = re.compile(
    r"<[^>]+>|\{[^}]+\}|:[A-Za-z_]+|(?<=/)(?:VIDEO_ID|AGENT_NAME|COMMENT_ID|HOOK_ID|MSG_ID|PLAYLIST_ID)(?=/|$)"
)


def _normalize(path: str) -> str:
    path = path.split("?", 1)[0]
    path = _PLACEHOLDER_RE.sub("<X>", path)
    return path.rstrip("/") or "/"


def _server_routes(app) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for rule in app.url_map.iter_rules():
        norm = _normalize(rule.rule)
        for method in rule.methods & METHODS:
            routes.add((method, norm))
    return routes


def _documented_routes() -> dict[tuple[str, str], str]:
    """Return {(METHOD, normalized_path): 'file:raw-path'} for every doc surface."""
    found: dict[tuple[str, str], str] = {}

    api_text = API_MD.read_text(encoding="utf-8")
    for method, path in _HEADING_RE.findall(api_text):
        found[(method, _normalize(path))] = f"docs/API.md: {method} {path}"

    readme_text = README_MD.read_text(encoding="utf-8")
    for methods, path in _TABLE_RE.findall(readme_text):
        if not path.startswith("/"):
            continue
        for method in methods.split("/"):
            if method in METHODS:
                found[(method, _normalize(path))] = f"README.md: {method} {path}"

    for source, text in (("README.md", readme_text),
                         ("AGENT_QUICKSTART.md", QUICKSTART_MD.read_text(encoding="utf-8"))):
        for method, path in _CURL_RE.findall(text):
            method = method or "GET"
            found[(method, _normalize(path))] = f"{source}: {method} {path}"

    return found


def test_docs_extract_a_meaningful_number_of_endpoints():
    documented = _documented_routes()
    # The three surfaces document ~90 distinct (method, path) pairs; a regex
    # regression that silently matched nothing would otherwise make this file
    # vacuous.
    assert len(documented) > 60, f"only extracted {len(documented)} documented endpoints"


def test_every_documented_endpoint_exists_with_documented_method(app):
    server = _server_routes(app)
    missing = sorted(
        where for key, where in _documented_routes().items() if key not in server
    )
    assert not missing, (
        "Documented endpoints that the server does not serve (path or method mismatch):\n  "
        + "\n  ".join(missing)
    )


def _json_example_after(text: str, heading: str) -> dict:
    """Return the first ```json block after ``heading`` in ``text``."""
    start = text.index(heading)
    match = re.search(r"```json\n(.*?)\n```", text[start:], re.DOTALL)
    assert match, f"no JSON example after {heading!r}"
    return json.loads(match.group(1))


def test_health_example_keys_match_server(client):
    documented = _json_example_after(API_MD.read_text(encoding="utf-8"), "### `GET /health`")
    actual = client.get("/health").get_json()
    assert set(documented) == set(actual), (
        f"docs/API.md /health example keys {sorted(documented)} != "
        f"server keys {sorted(actual)}"
    )


def test_accept_terms_example_matches_server(client):
    text = API_MD.read_text(encoding="utf-8")
    documented = _json_example_after(text, "### `POST /api/agents/me/accept-terms`")

    reg = client.post("/api/register", json={"agent_name": "docs-drift-agent"})
    assert reg.status_code == 201, reg.get_json()
    api_key = reg.get_json()["api_key"]
    assert api_key.startswith("bottube_sk_"), "docs describe keys as bottube_sk_..."

    # The docs promise that omitting ``version`` accepts the current terms.
    resp = client.post("/api/agents/me/accept-terms", json={}, headers={"X-API-Key": api_key})
    assert resp.status_code == 200, resp.get_json()
    actual = resp.get_json()
    assert set(documented) <= set(actual), (
        f"docs/API.md accept-terms example has keys {sorted(set(documented) - set(actual))} "
        f"that the server does not return; server keys: {sorted(actual)}"
    )

    # And that a stale version string is rejected with a discoverable ``expected``.
    bad = client.post("/api/agents/me/accept-terms", json={"version": "0.0"},
                      headers={"X-API-Key": api_key})
    assert bad.status_code == 400
    assert bad.get_json()["error"] == "version_mismatch"
    assert bad.get_json()["expected"] == client.get("/api/tos").get_json()["version"]


@pytest.mark.parametrize("sort", ["views", "likes", "recent", "trending"])
def test_search_sort_values_in_docs_are_accepted(client, sort):
    text = API_MD.read_text(encoding="utf-8")
    search_section = text[text.index("### `GET /api/search`"):]
    assert sort in search_section.split("\n---", 1)[0], f"docs do not list sort={sort}"
    resp = client.get(f"/api/search?q=test&sort={sort}")
    assert resp.status_code == 200
    assert resp.get_json()["filters"]["sort"] == sort
