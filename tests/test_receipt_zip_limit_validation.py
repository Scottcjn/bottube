"""Regression coverage for receipt-batch limit validation (issue #2007)."""

import importlib

def test_receipt_zip_limit_contract(client, monkeypatch):
    server = importlib.import_module("bottube_server")
    rate_limit_calls = []

    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("invalid pagination reached receipt side effects")

    def stop_at_receipt_rate_limit(key, *_args):
        rate_limit_calls.append(key)
        return not key.startswith("receipts_zip:")

    monkeypatch.setattr(server, "_rate_limit", stop_at_receipt_rate_limit)
    monkeypatch.setattr(server, "_provenance_ensure_v2_columns", unexpected_call)
    monkeypatch.setattr(server, "_build_receipt_for_video", unexpected_call)

    invalid_cases = [
        ("abc", "integer"),
        ("0", ">= 1"),
        ("-5", ">= 1"),
        ("501", "<= 500"),
        (str(2**80), "<= 500"),
    ]
    for raw_limit, message in invalid_cases:
        response = client.get(
            "/api/agents/example/receipts.zip",
            query_string={"limit": raw_limit},
        )
        assert response.status_code == 400
        assert message in response.get_json()["error"]
    assert not any(key.startswith("receipts_zip:") for key in rate_limit_calls)

    for query in ({}, {"limit": "1"}, {"limit": "500"}):
        response = client.get("/api/agents/example/receipts.zip", query_string=query)
        assert response.status_code == 429
        assert response.get_json() == {"ok": False, "error": "rate limited"}
    receipt_calls = [
        key for key in rate_limit_calls if key.startswith("receipts_zip:")
    ]
    assert len(receipt_calls) == 3
