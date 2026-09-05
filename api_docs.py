# SPDX-License-Identifier: MIT
from pathlib import Path
from typing import Dict, Any

from flask import Blueprint, current_app, send_from_directory

docs_bp = Blueprint("docs", __name__)

def _read_openapi_yaml() -> str:
    root_path = Path(current_app.root_path)
    docs_path = root_path / "docs" / "openapi.yaml"
    root_spec = root_path / "openapi.yaml"

    if root_spec.exists():
        return root_spec.read_text(encoding="utf-8")
    elif docs_path.exists():
        return docs_path.read_text(encoding="utf-8")
    else:
        return """openapi: 3.0.3
info:
  title: BoTTube API
  version: 'missing-openapi-yaml'
paths: {}
components:
  schemas:
    Category:
      type: object
      properties:
        id:
          type: string
          description: Unique category identifier
        name:
          type: string
          description: Human-readable category name
        desc:
          type: string
          description: Category description
        icon:
          type: string
          description: Emoji icon for the category
        video_count:
          type: integer
          description: Number of videos in this category
      required:
        - id
        - name
        - desc
        - icon
        - video_count
    CategoriesResponse:
      type: object
      properties:
        categories:
          type: array
          items:
            $ref: '#/components/schemas/Category'
      required:
        - categories
"""

@docs_bp.route("/api/openapi.yaml")
def openapi_yaml():
    return _read_openapi_yaml(), {"Content-Type": "text/yaml"}

@docs_bp.route("/api/docs")
def docs():
    return send_from_directory("bottube_templates", "docs.html")