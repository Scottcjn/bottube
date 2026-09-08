# SPDX-License-Identifier: MIT
"""Protect OpenAPI contracts from YAML's silent duplicate-key overwrites."""
from pathlib import Path

import yaml


SPEC = Path(__file__).resolve().parents[1] / "openapi.yaml"


def test_openapi_mapping_keys_are_unique():
    # Inspect the syntax tree: safe_load has already discarded duplicate keys.
    def check(node, location="$"):
        if isinstance(node, yaml.MappingNode):
            seen = set()
            for key, value in node.value:
                assert isinstance(key, yaml.ScalarNode), location
                identity = (key.tag, key.value)
                assert identity not in seen, (
                    f"Duplicate key {key.value!r} at {location}, "
                    f"line {key.start_mark.line + 1}"
                )
                seen.add(identity)
                check(value, f"{location}.{key.value}")
        elif isinstance(node, yaml.SequenceNode):
            for index, value in enumerate(node.value):
                check(value, f"{location}[{index}]")

    check(yaml.compose(SPEC.read_text(encoding="utf-8")))


def _schema(spec, schema):
    if "$ref" in schema:
        return spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
    return schema


def test_studio_generation_contract_survives_parsing():
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    operation = spec["paths"]["/api/studio/generate"]["post"]
    assert operation["operationId"] == "createStudioGeneration"
    request = _schema(
        spec, operation["requestBody"]["content"]["application/json"]["schema"]
    )
    assert request["required"] == ["prompt"]
    assert request["properties"]["tier"]["enum"] == [
        "text_card", "ken_burns", "full_ai"
    ]
    assert "audio" in request["properties"]

    responses = operation["responses"]
    assert {200, 202, 400, 401, 402, 429, 502, 503} <= responses.keys()
    for status, types, result_fields in (
        (200, ["image", "voice"], {"media_url"}),
        (202, ["video", "i2v", "model"], {"job_id", "status_url"}),
    ):
        schema = _schema(
            spec, responses[status]["content"]["application/json"]["schema"]
        )
        assert schema["properties"]["type"]["enum"] == types
        assert {"ok", "type", "charged_rtc", "new_balance"} | result_fields <= set(
            schema["required"]
        )
        assert "remaining_balance" not in schema["properties"]


def test_earnings_contract_survives_parsing():
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    operation = spec["paths"]["/api/agents/me/earnings"]["get"]
    assert operation["operationId"] == "getMyEarnings"
    schema = _schema(
        spec, operation["responses"][200]["content"]["application/json"]["schema"]
    )
    assert set(schema["required"]) == {
        "agent_name", "rtc_balance", "earnings", "page", "per_page", "total"
    }
    entry = schema["properties"]["earnings"]["items"]
    assert entry["properties"]["created_at"]["type"] == "number"
    assert entry["properties"]["video_id"]["nullable"] is True
