"""Static and executable regressions for wallet operation feedback."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_every_wallet_result_container_is_an_atomic_live_status():
    template = Path("bottube_templates/settings_wallet.html").read_text(
        encoding="utf-8"
    )
    for element_id in (
        "linked-wallet-result",
        "local-wallet-status",
        "local-wallet-result",
    ):
        line = next(
            line for line in template.splitlines() if f'id="{element_id}"' in line
        )
        assert 'role="status"' in line
        assert 'aria-live="polite"' in line
        assert 'aria-atomic="true"' in line


def test_shared_writer_updates_each_wallet_status_path():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the JavaScript runtime regression")

    result = subprocess.run(
        [node, str(Path(__file__).parent / "wallet_status_live_region.test.cjs")],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
