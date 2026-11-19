"""Exercise the outcome-report shell script with GitHub needs results."""
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from test_ci_workflow_timeouts import workflow_text


@pytest.mark.parametrize("drift_result, drift_kind, expected_code, message", [
    ("success", "code_failure", 0, "All CI jobs completed successfully."),
    ("failure", "code_failure", 1, "FAILED on a step of your code"),
    ("failure", "step_timeout_or_infra", 1, "timed out or hung on infrastructure"),
    ("failure", "", 1, "failed before any step reported a result"),
    ("cancelled", "", 1, "timed out or cancelled before finishing"),
])
def test_report_includes_deployment_drift(tmp_path, drift_result, drift_kind, expected_code, message):
    report = yaml.safe_load(workflow_text("ci.yml"))["jobs"]["report"]
    step = report["steps"][0]

    def resolve(template):
        # GitHub resolves missing context properties to the empty string.
        template = re.sub(
            r"\$\{\{\s*needs\.([\w-]+)\.result\s*\}\}",
            lambda m: drift_result if m.group(1) == "deployment-drift" else "success",
            template,
        )
        return re.sub(
            r"\$\{\{\s*needs\.([\w-]+)\.outputs\.failure_kind\s*\}\}",
            lambda m: drift_kind if m.group(1) == "deployment-drift" else "code_failure",
            template,
        )

    env = {"GITHUB_STEP_SUMMARY": str(tmp_path / "step_summary.md")}
    for name, template in step["env"].items():
        env[name] = resolve(template)
    completed = subprocess.run(["bash", "-e", "-c", step["run"]],
                               capture_output=True, text=True, timeout=5, env=env)
    assert completed.returncode == expected_code, completed.stdout + completed.stderr
    combined = completed.stdout + Path(env["GITHUB_STEP_SUMMARY"]).read_text(encoding="utf-8")
    assert message in combined
