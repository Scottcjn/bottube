# SPDX-License-Identifier: MIT
from pathlib import Path

from flask import Flask

from api_docs import _read_openapi_yaml, docs_bp


ADVERTISED_LIVE_OPERATIONS = {
    ("/api/studio/generate", "post"),
    ("/api/forum/generate-image", "post"),
    ("/api/agents/me/earnings", "get"),
    ("/api/video/mine", "get"),
    ("/api/video/publish", "post"),
    ("/api/video/discard", "post"),
}


def _make_app(root_path: Path) -> Flask:
    app = Flask(__name__, root_path=str(root_path))
    app.config.update(TESTING=True)
    app.register_blueprint(docs_bp)
    return app


def _documented_operations(spec_text: str) -> set[tuple[str, str]]:
    operations = set()
    current_path = None
    methods = {"get", "post", "put", "patch", "delete", "head", "options"}

    for line in spec_text.splitlines():
        if line.startswith("  /") and line.endswith(":"):
            current_path = line.strip()[:-1]
            continue
        if current_path and line.startswith("    ") and not line.startswith("      "):
            key = line.strip()[:-1] if line.strip().endswith(":") else ""
            if key in methods:
                operations.add((current_path, key))

    return operations


def test_openapi_yaml_documents_endpoints_advertised_by_api_explorer():
    repo_root = Path(__file__).resolve().parents[1]
    app = _make_app(repo_root)

    response = app.test_client().get("/api/openapi.yaml")

    assert response.status_code == 200
    documented = _documented_operations(response.get_data(as_text=True))
    assert ADVERTISED_LIVE_OPERATIONS <= documented


def test_read_openapi_yaml_prefers_root_spec(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "openapi.yaml").write_text("openapi: root\n", encoding="utf-8")
    (tmp_path / "docs" / "openapi.yaml").write_text("openapi: docs\n", encoding="utf-8")
    app = _make_app(tmp_path)

    with app.app_context():
        assert _read_openapi_yaml() == "openapi: root\n"


def test_read_openapi_yaml_uses_docs_yml_when_root_specs_are_missing(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "openapi.yml").write_text("openapi: docs-yml\n", encoding="utf-8")
    app = _make_app(tmp_path)

    with app.app_context():
        assert _read_openapi_yaml() == "openapi: docs-yml\n"


def test_openapi_yaml_route_returns_fallback_spec_when_file_is_missing(tmp_path):
    app = _make_app(tmp_path)
    response = app.test_client().get("/api/openapi.yaml")

    assert response.status_code == 200
    assert response.mimetype == "text/yaml"
    assert response.get_data(as_text=True) == (
        "openapi: 3.0.3\n"
        "info:\n"
        "  title: BoTTube API\n"
        "  version: 'missing-openapi-yaml'\n"
    )


def test_swagger_ui_uses_application_root_for_spec_url(tmp_path):
    app = _make_app(tmp_path)
    app.config["APPLICATION_ROOT"] = "/mounted"

    response = app.test_client().get("/api/docs", base_url="https://example.test/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert "SwaggerUIBundle" in html
    assert "https://example.test/mounted/api/openapi.yaml" in html
