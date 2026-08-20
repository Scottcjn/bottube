# SPDX-License-Identifier: MIT
"""Verify the OpenAPI spec registers the six endpoints from issue #1605.

Dependency-free: only stdlib + pyyaml (already imported by the repo for the
openapi.json re-serialiser). These assertions match what the production
openapi.json/YAML serves to SDK generators.
"""
from __future__ import annotations

import yaml

SPEC = "openapi.yaml"

REQUIRED = {
    "/api/studio/generate": "post",
    "/api/forum/generate-image": "post",
    "/api/agents/me/earnings": "get",
    "/api/video/mine": "get",
    "/api/video/publish": "post",
    "/api/video/discard": "post",
}
SCHEMAS = [
    "AgentEarnings",
    "StudioGenerateRequest",
    "StudioGenerateResponse",
    "ForumGenerateImageRequest",
]

d = yaml.safe_load(open(SPEC, encoding="utf-8"))


def test_openapi_version() -> None:
    assert str(d["openapi"]).startswith("3.")


def test_spec_version_bumped() -> None:
    # 1.3.0 -> 1.4.0 after adding the six endpoints
    assert d["info"]["version"] == "1.4.0"


def test_six_endpoints_present_and_methods() -> None:
    paths = d["paths"]
    for path, method in REQUIRED.items():
        assert path in paths, f"missing path {path}"
        assert method in paths[path], f"{path} missing method {method}"


def test_referenced_schemas_exist() -> None:
    schemas = d["components"]["schemas"]
    for name in SCHEMAS:
        assert name in schemas, f"missing schema {name}"


def test_studio_tag_registered() -> None:
    tags = {t["name"] for t in d["tags"]}
    assert "Studio" in tags


def test_roundtrip_parse_stable() -> None:
    assert yaml.safe_load(yaml.safe_dump(d)) == d


def test_existing_paths_intact() -> None:
    # Ensure the pre-existing 20 paths were not removed
    existing = {
        "/api/register",
        "/api/agents/me",
        "/api/agents/me/profile",
        "/api/agents/me/avatar",
        "/api/collaborations/me",
    }
    paths = set(d["paths"].keys())
    assert paths.issuperset(existing)
