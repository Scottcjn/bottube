"""API Docs Blueprint (Swagger UI + OpenAPI spec)

Implements bounty issue: https://github.com/Scottcjn/bottube/issues/144

Design goals:
- No heavy dependencies
- Serve a static OpenAPI YAML from repo root
- Swagger UI via CDN

"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Response, current_app, render_template, request


docs_bp = Blueprint("api_docs", __name__)


def _read_openapi_yaml() -> str:
    base_dir = Path(current_app.root_path)

    # repo root == current_app.root_path in this codebase (bottube_server.py lives there)
    candidates = [
        base_dir / "openapi.yaml",
        base_dir / "openapi.yml",
        base_dir / "docs" / "openapi.yaml",
        base_dir / "docs" / "openapi.yml",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p.read_text(encoding="utf-8")

    return "openapi: 3.0.3\ninfo:\n  title: BoTTube API\n  version: 'missing-openapi-yaml'\n"


@docs_bp.get("/api/openapi.yaml")
def openapi_yaml():
    text = _read_openapi_yaml()
    # Some crawlers + tooling expect text/yaml; others accept application/yaml.
    return Response(text, mimetype="text/yaml; charset=utf-8")


@docs_bp.get("/api/docs")
def swagger_ui():
    """Swagger UI (CDN-hosted assets).

    Notes:
    - We intentionally do NOT bundle swagger assets into the repo.
    - Config uses request.url_root so local dev works behind proxies.
    """

    base = request.url_root.rstrip("/")
    prefix = current_app.config.get("APPLICATION_ROOT", "").rstrip("/")
    spec_url = f"{base}{prefix}/api/openapi.yaml"

    html = f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
    <title>BoTTube API Docs</title>
    <link rel=\"stylesheet\" href=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui.css\" />
    <style>
      body {{ margin: 0; background: #0f0f0f; }}
      .topbar {{ display: none; }}
    </style>
  </head>
  <body>
    <div id=\"swagger-ui\"></div>
    <script src=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js\"></script>
    <script>
      window.onload = function() {{
        SwaggerUIBundle({{
          url: {spec_url!r},
          dom_id: '#swagger-ui',
          deepLinking: true,
          displayRequestDuration: true,
          docExpansion: 'list',
          persistAuthorization: true
        }});
      }}
    </script>
  </body>
</html>"""

    return Response(html, mimetype="text/html; charset=utf-8")


@docs_bp.get("/developers")
def developers_landing():
    """Developer landing page (SEO-friendly)."""
    return render_template("developers.html")
