# SPDX-License-Identifier: MIT
"""Regression: social_orchestrate sends X-API-Key only over verified TLS.

It used to pass verify=False on every request (and silence urllib3's
warning), so anyone on the path could harvest the bots' API keys. The
module is a top-level script that posts on import, so check its AST
instead of importing it.
"""

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "social_orchestrate.py"


def test_no_request_disables_tls_verification():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    request_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "requests"
    ]
    assert request_calls, "expected requests.* calls in social_orchestrate.py"
    for call in request_calls:
        for kw in call.keywords:
            assert not (kw.arg == "verify" and isinstance(kw.value, ast.Constant)
                        and kw.value.value is False), f"verify=False at line {call.lineno}"
    assert "disable_warnings" not in SOURCE.read_text(encoding="utf-8")
