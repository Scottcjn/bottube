# SPDX-License-Identifier: MIT
import os
import subprocess
import sys
from pathlib import Path


def test_production_app_registers_translation_routes(tmp_path):
    env = os.environ.copy()
    env["BOTTUBE_BASE_DIR"] = str(tmp_path)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(Path(__file__).resolve().parents[1]), env.get("PYTHONPATH")])
    )
    script = (
        "import bottube_server; "
        "routes={r.rule for r in bottube_server.app.url_map.iter_rules()}; "
        "assert '/translations' in routes; "
        "assert '/api/translations/<video_id>' in routes"
    )

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.fspath(tmp_path),
        env=env,
        check=True,
        timeout=60,
    )
