# SPDX-License-Identifier: MIT
import json
from pathlib import Path

import pytest

from deployment_drift import (
    CONFIG_ERROR,
    ConfigError,
    LIVE_UNAVAILABLE,
    MISSING_IN_CODE,
    MISSING_IN_SPEC,
    Operation,
    STALE_ALLOWANCE,
    build_report,
    extract_flask_inventory,
    extract_flask_operations,
    format_json,
    format_text,
    load_config,
    main,
    probe_live,
    request_head,
    validate_live_base_url,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_project(tmp_path, source, operations):
    (tmp_path / "app.py").write_text(source, encoding="utf-8")
    paths = {}
    for method, path in operations:
        paths.setdefault(path, {})[method.lower()] = {"responses": {"200": {"description": "ok"}}}
    (tmp_path / "openapi.yaml").write_text(
        json.dumps({"openapi": "3.0.3", "info": {"title": "test", "version": "1"}, "paths": paths}),
        encoding="utf-8",
    )


def _config(**overrides):
    config = {
        "application_sources": ["app.py"],
        "missing_in_spec_patterns": ["/api/*"],
        "openapi": "openapi.yaml",
    }
    config.update(overrides)
    return config


def test_extracts_flask_decorators_blueprint_prefixes_and_url_rules(tmp_path):
    source = tmp_path / "app.py"
    source.write_text(
        """
from flask import Blueprint, Flask
app = Flask(__name__)
api_bp = Blueprint("api", __name__, url_prefix="/api")

@app.get("/health")
def health(): pass

@api_bp.route("/items/<int:item_id>", methods=["GET", "PATCH"])
def item(item_id): pass

app.add_url_rule("/api/alias/<path:name>", endpoint="alias", view_func=health)
""",
        encoding="utf-8",
    )

    operations = extract_flask_operations([source])

    assert operations == {
        Operation("GET", "/health"),
        Operation("GET", "/api/items/{item_id}"),
        Operation("PATCH", "/api/items/{item_id}"),
        Operation("GET", "/api/alias/{name}"),
    }


def test_extracts_qualified_constructors_aliases_keyword_rules_and_registration_override(tmp_path):
    source = tmp_path / "app.py"
    source.write_text(
        """
import flask as web
from flask import Blueprint as BlueprintFactory

application = web.Flask(__name__)
site = application
routes = BlueprintFactory("api", __name__, url_prefix="/declared")
route_alias = routes
site.register_blueprint(blueprint=route_alias, url_prefix="/mounted")

@route_alias.get(rule="/items/<int:item_id>")
def item(item_id): pass

@site.route(rule="/keyword", methods=["POST"])
def keyword(): pass

site.add_url_rule(rule="/alias", endpoint="alias", view_func=keyword)
""",
        encoding="utf-8",
    )

    inventory = extract_flask_inventory([source])

    assert inventory.declared == {
        Operation("GET", "/mounted/items/{item_id}"),
        Operation("POST", "/keyword"),
        Operation("GET", "/alias"),
    }
    assert Operation("GET", "/declared/items/{item_id}") not in inventory.declared
    assert Operation("HEAD", "/mounted/items/{item_id}") in inventory.implicit
    assert Operation("OPTIONS", "/keyword") in inventory.implicit


def test_unsupported_qualified_route_owner_fails_visibly(tmp_path):
    source = tmp_path / "app.py"
    source.write_text(
        """
@container.app.get("/hidden")
def hidden(): pass
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unsupported route owner 'container.app'"):
        extract_flask_operations([source])


def test_cross_file_blueprint_prefix_override_fails_instead_of_inventing_path(tmp_path):
    app_source = tmp_path / "app.py"
    blueprint_source = tmp_path / "routes.py"
    app_source.write_text(
        """
from flask import Flask
from routes import routes
app = Flask(__name__)
app.register_blueprint(routes, url_prefix="/mounted")
""",
        encoding="utf-8",
    )
    blueprint_source.write_text(
        """
from flask import Blueprint
routes = Blueprint("routes", __name__, url_prefix="/declared")
@routes.get("/items")
def items(): pass
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="cannot resolve url_prefix override for imported blueprint"):
        extract_flask_operations([app_source, blueprint_source])


def test_implicit_head_and_options_satisfy_openapi_without_missing_spec_noise(tmp_path):
    _write_project(
        tmp_path,
        """
from flask import Flask
app = Flask(__name__)
@app.get("/api/resource")
def resource(): pass
""",
        [("GET", "/api/resource"), ("HEAD", "/api/resource"), ("OPTIONS", "/api/resource")],
    )

    report = build_report(tmp_path, _config())

    assert report["status"] == "pass"
    assert report["drift"]["missing_in_code"] == []
    assert report["drift"]["missing_in_spec"] == []
    assert report["inventory"]["application_operations"] == 1
    assert report["inventory"]["application_effective_operations"] == 3


def test_disabling_automatic_options_keeps_openapi_options_missing(tmp_path):
    _write_project(
        tmp_path,
        """
from flask import Flask
app = Flask(__name__)
@app.get("/api/resource", provide_automatic_options=False)
def resource(): pass
""",
        [("GET", "/api/resource"), ("HEAD", "/api/resource"), ("OPTIONS", "/api/resource")],
    )

    report = build_report(tmp_path, _config())

    assert report["drift"]["missing_in_code"] == [
        {"method": "OPTIONS", "path": "/api/resource"}
    ]
    assert report["drift"]["missing_in_spec"] == []


def test_report_separates_missing_in_code_and_missing_in_spec(tmp_path):
    _write_project(
        tmp_path,
        """
from flask import Flask
app = Flask(__name__)

@app.get("/api/present")
def present(): pass

@app.post("/api/undocumented")
def undocumented(): pass
""",
        [("GET", "/api/present"), ("GET", "/api/missing/{item_id}")],
    )

    report = build_report(tmp_path, _config())

    assert report["exit_code"] == MISSING_IN_CODE | MISSING_IN_SPEC
    assert report["drift"]["missing_in_code"] == [
        {"method": "GET", "path": "/api/missing/{item_id}"}
    ]
    assert report["drift"]["missing_in_spec"] == [
        {"method": "POST", "path": "/api/undocumented"}
    ]
    assert report["drift"]["live_unavailable"] == []


def test_known_drift_remains_visible_but_does_not_block(tmp_path):
    _write_project(tmp_path, "from flask import Flask\napp = Flask(__name__)\n", [("GET", "/api/missing")])
    report = build_report(
        tmp_path,
        _config(allowed_drift={"missing_in_code": ["GET /api/missing"]}),
    )

    assert report["status"] == "pass"
    assert report["drift"]["missing_in_code"] == [{"method": "GET", "path": "/api/missing"}]
    assert report["allowed"]["missing_in_code"] == [{"method": "GET", "path": "/api/missing"}]
    assert "[known] GET /api/missing" in format_text(report)


def test_stale_known_drift_allowance_blocks_cleanup(tmp_path):
    _write_project(
        tmp_path,
        """
from flask import Flask
app = Flask(__name__)
@app.get("/api/present")
def present(): pass
""",
        [("GET", "/api/present")],
    )
    report = build_report(
        tmp_path,
        _config(allowed_drift={"missing_in_code": ["GET /api/present"]}),
    )

    assert report["exit_code"] == STALE_ALLOWANCE
    assert report["stale_allowances"] == [{"method": "GET", "path": "/api/present"}]


def test_issue_1410_state_is_live_unavailable_only(tmp_path):
    _write_project(
        tmp_path,
        """
from flask import Flask
app = Flask(__name__)

@app.get("/merged-route")
def merged_route(): pass
""",
        [],
    )
    calls = []

    def missing_live(url, timeout):
        calls.append((url, timeout))
        return 404

    report = build_report(
        tmp_path,
        _config(
            canaries=["GET /merged-route"],
            live_probe_openapi_reads=False,
        ),
        live_enabled=True,
        live_base_url="https://example.test",
        requester=missing_live,
    )

    assert report["drift"]["missing_in_code"] == []
    assert report["drift"]["missing_in_spec"] == []
    assert report["exit_code"] == LIVE_UNAVAILABLE
    assert report["drift"]["live_unavailable"] == [
        {
            "available": False,
            "method": "GET",
            "path": "/merged-route",
            "reason": "http_status:404",
            "request_method": "HEAD",
            "request_path": "/merged-route",
            "status": 404,
        }
    ]
    assert calls == [("https://example.test/merged-route", 5.0)]


def test_live_fixtures_are_encoded_and_missing_fixtures_do_not_request():
    calls = []

    def available(url, timeout):
        calls.append((url, timeout))
        return 401

    results = probe_live(
        [Operation("GET", "/api/videos/{video_id}"), Operation("GET", "/api/agents/{agent_name}")],
        "https://example.test/base",
        {"video_id": "folder value"},
        2.5,
        available,
    )

    assert calls == [("https://example.test/base/api/videos/folder%20value", 2.5)]
    assert results[0]["reason"] == "missing_fixture:agent_name"
    assert results[1]["available"] is True
    assert results[1]["reason"] == "route_present"


def test_request_head_sends_no_credentials_and_does_not_follow_redirects(monkeypatch):
    captured = {}

    class Response:
        status = 302

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Opener:
        def open(self, request, timeout):
            captured["method"] = request.get_method()
            captured["headers"] = {name.lower(): value for name, value in request.header_items()}
            captured["timeout"] = timeout
            return Response()

    monkeypatch.setattr("urllib.request.build_opener", lambda *handlers: Opener())

    assert request_head("https://example.test/account", 3) == 302
    assert captured["method"] == "HEAD"
    assert captured["timeout"] == 3
    assert "authorization" not in captured["headers"]
    assert "cookie" not in captured["headers"]
    assert "x-api-key" not in captured["headers"]


def test_reports_are_deterministic(tmp_path):
    _write_project(
        tmp_path,
        """
from flask import Flask
app = Flask(__name__)
@app.get("/api/z")
def z(): pass
@app.get("/api/a")
def a(): pass
""",
        [("GET", "/api/m")],
    )
    first = build_report(tmp_path, _config())
    second = build_report(tmp_path, _config())

    assert format_json(first) == format_json(second)
    assert format_text(first) == format_text(second)
    assert format_json(first).endswith("\n")


def test_live_base_url_requires_explicit_live_flag(tmp_path, capsys):
    _write_project(tmp_path, "from flask import Flask\napp = Flask(__name__)\n", [])
    (tmp_path / "deployment-drift.json").write_text(json.dumps(_config()), encoding="utf-8")

    exit_code = main(["--repo-root", str(tmp_path), "--live-base-url", "https://example.test"])

    assert exit_code == CONFIG_ERROR
    assert "inert without explicit --live" in capsys.readouterr().err


@pytest.mark.parametrize(
    "base_url",
    [
        "https://[::1",
        "https://example.test:not-a-port",
        "https://example.test:70000",
    ],
)
def test_malformed_live_urls_return_cli_config_error(tmp_path, capsys, base_url):
    _write_project(tmp_path, "from flask import Flask\napp = Flask(__name__)\n", [])
    (tmp_path / "deployment-drift.json").write_text(json.dumps(_config()), encoding="utf-8")

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--live",
            "--live-base-url",
            base_url,
        ]
    )

    assert exit_code == CONFIG_ERROR
    assert "invalid live base URL" in capsys.readouterr().err


@pytest.mark.parametrize("base_url", ["https://[::1", "https://host.test:bad", "https://host.test:99999"])
def test_malformed_live_urls_raise_config_error(base_url):
    with pytest.raises(ConfigError, match="invalid live base URL"):
        validate_live_base_url(base_url)


@pytest.mark.parametrize(
    "fixture",
    ["", "   ", ".", "..", "folder/value", "folder\\value", "%2e%2e", "%2Fadmin", "%252e%252e"],
)
def test_fixture_values_must_be_safe_single_segments(fixture):
    with pytest.raises(ConfigError, match="fixture value"):
        probe_live(
            [Operation("GET", "/api/videos/{video_id}")],
            "https://example.test",
            {"video_id": fixture},
            1,
            lambda url, timeout: pytest.fail("unsafe fixture attempted a request"),
        )


def test_canaries_reject_mutating_methods(tmp_path):
    _write_project(tmp_path, "from flask import Flask\napp = Flask(__name__)\n", [])

    with pytest.raises(ValueError, match="safe GET or HEAD"):
        build_report(tmp_path, _config(canaries=["POST /api/mutate"]))


@pytest.mark.parametrize("timeout", [0, -1, True, "not-a-number", float("inf"), float("-inf"), float("nan")])
def test_timeout_must_be_a_positive_number(tmp_path, timeout):
    _write_project(tmp_path, "from flask import Flask\napp = Flask(__name__)\n", [])

    with pytest.raises(ValueError, match="timeout must be a positive number"):
        build_report(tmp_path, _config(timeout=timeout))


def test_repository_configs_are_valid_offline():
    policy = build_report(REPO_ROOT, load_config(REPO_ROOT / "deployment-drift.json"))
    canary = build_report(REPO_ROOT, load_config(REPO_ROOT / "deployment-drift.issue-1410.example.json"))

    assert policy["status"] == "pass"
    assert policy["inventory"]["openapi_operations"] == 24
    assert policy["inventory"]["application_operations"] == 347
    assert len(policy["drift"]["missing_in_code"]) == 19
    assert canary["status"] == "pass"
    assert canary["inventory"]["canary_operations"] == 14


def test_issue_1410_config_reports_exact_live_only_failure_state():
    config = load_config(REPO_ROOT / "deployment-drift.issue-1410.example.json")
    requested = []

    def production_404(url, timeout):
        requested.append((url, timeout))
        return 404

    report = build_report(
        REPO_ROOT,
        config,
        live_enabled=True,
        live_base_url="https://example.test",
        requester=production_404,
    )

    assert report["exit_code"] == LIVE_UNAVAILABLE
    assert report["blocking"]["missing_in_code"] == []
    assert report["blocking"]["missing_in_spec"] == []
    assert len(report["blocking"]["live_unavailable"]) == 14
    assert len(requested) == 14
    assert {url for url, _ in requested} == {
        "https://example.test/account",
        "https://example.test/account/settings",
        "https://example.test/agents/me",
        "https://example.test/channels",
        "https://example.test/creator",
        "https://example.test/creators",
        "https://example.test/help",
        "https://example.test/home",
        "https://example.test/live",
        "https://example.test/premium/plans",
        "https://example.test/premium/upgrade",
        "https://example.test/settings/profile",
        "https://example.test/tags",
        "https://example.test/watch",
    }
