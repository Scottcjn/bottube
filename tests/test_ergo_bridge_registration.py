# SPDX-License-Identifier: MIT
"""Regression test for registering the Ergo bridge in the production app."""

from pathlib import Path


def test_bottube_server_registers_ergo_bridge_blueprint():
    source = Path("bottube_server.py").read_text(encoding="utf-8")

    assert "from ergo_bridge_blueprint import ergo_bp, init_ergo_tables" in source
    assert "init_ergo_tables(_ergo_db)" in source
    assert "app.register_blueprint(ergo_bp)" in source
