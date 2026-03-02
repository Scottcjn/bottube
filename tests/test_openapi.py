# SPDX-License-Identifier: MIT

from bottube.openapi import build_openapi_spec


def test_openapi_minimal():
    spec = build_openapi_spec(version="test")
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "BoTTube API"
    assert spec["info"]["version"] == "test"
    assert "/api/upload" in spec["paths"]
    assert "ApiKeyAuth" in spec["components"]["securitySchemes"]
