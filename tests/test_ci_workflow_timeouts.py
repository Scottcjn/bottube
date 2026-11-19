# SPDX-License-Identifier: MIT
"""Workflow timeout + attribution audit (rustchain-bounties#16472).

The 15m01s CI failures on bottube#1639/#1640 were GitHub Actions
infrastructure hangs that contributors were told were their fault. These
rules keep that from recurring: every job and step declares an explicit
timeout (so a hang fails fast with "timed out after N minutes" instead of
pretending the code failed), pip installs are network-bounded, and
ci.yml/labeler.yml classify failures as infrastructure vs code before
anyone is blamed.

While the #16472 workflow YAML updates are pending (the contributor's PAT
has no `workflow` scope, so they ship as full copies under
patches/16472-workflows/ and in the PR description), the audit checks those
copies; once the files land in .github/workflows/ it checks the live files.
"""
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
PATCHED = REPO_ROOT / "patches" / "16472-workflows"
ALL_WORKFLOWS = ["ci.yml", "labeler.yml", "rtc-reward.yml", "bottube-verify.yml", "python-sdk.yml"]
PATCHED_FILES = ["ci.yml", "labeler.yml", "rtc-reward.yml"]
# Jobs whose failure kind the ci.yml report job needs to attribute blame.
CI_CODE_JOBS = ["lint", "test", "security", "deployment-drift"]


def workflow_text(name):
    """Effective text for a workflow: live file, or the #16472 pending copy.

    shortcut: while the patch is unapplied the audit checks the proposal in
    patches/16472-workflows/; delete that directory when the YAML lands and
    these tests start enforcing .github/workflows/ directly.
    """
    live = (WORKFLOWS / name).read_text(encoding="utf-8")
    pending = PATCHED / name
    if pending.exists():
        text = pending.read_text(encoding="utf-8")
        if text != live:
            return text
    return live


def _jobs(name):
    return yaml.safe_load(workflow_text(name))["jobs"]


def test_pending_workflow_copies_are_really_pending():
    """Once a copy matches the live workflow, the patch landed: delete it."""
    for name in PATCHED_FILES:
        pending = PATCHED / name
        if pending.exists():
            assert pending.read_text(encoding="utf-8") != (WORKFLOWS / name).read_text(encoding="utf-8"), (
                f"{name}: the #16472 workflow update is applied - delete patches/16472-workflows/{name}"
            )


@pytest.mark.parametrize("name", ALL_WORKFLOWS)
def test_every_job_declares_a_timeout(name):
    for job_id, job in _jobs(name).items():
        limit = job.get("timeout-minutes")
        assert isinstance(limit, int) and 1 <= limit <= 30, (
            f"{name}: job {job_id!r} must declare timeout-minutes 1-30, got {limit!r}"
        )


@pytest.mark.parametrize("name", ALL_WORKFLOWS)
def test_every_step_declares_a_timeout(name):
    for job_id, job in _jobs(name).items():
        job_limit = job["timeout-minutes"]
        for step in job.get("steps", []):
            label = step.get("name") or step.get("uses") or "?"
            limit = step.get("timeout-minutes")
            assert isinstance(limit, int) and 1 <= limit <= job_limit, (
                f"{name}: {job_id}/{label} must declare timeout-minutes 1-{job_limit}, got {limit!r}"
            )


@pytest.mark.parametrize("name", ALL_WORKFLOWS)
def test_pip_installs_are_network_bounded(name):
    for job_id, job in _jobs(name).items():
        for step in job.get("steps", []):
            run = step.get("run") or ""
            if "pip install" in run:
                assert "--timeout" in run, f"{name}: {job_id} pip install must pass --timeout"


@pytest.mark.parametrize("job_id", CI_CODE_JOBS)
def test_ci_job_classifies_its_failure_kind(job_id):
    steps = _jobs("ci.yml")[job_id]["steps"]
    classify = [s for s in steps if s.get("id") == "classify"]
    assert len(classify) == 1, f"{job_id} needs exactly one step with id: classify"
    step = classify[0]
    assert step["if"] == "always()", "classify must run even after a cancellation"
    outcomes = step["env"]["SETUP_OUTCOMES"]
    for ref in ("steps.checkout.outcome", "steps.setup-python.outcome", "steps.install.outcome"):
        assert ref in outcomes, f"{job_id}: classify env must inspect {ref}"
    assert "step_timeout_or_infra" in step["run"] and "code_failure" in step["run"]


@pytest.mark.parametrize("outcomes, expected_kind", [
    ("success/success/success", "code_failure"),  # a code step failed, setup was fine
    ("success/success/cancelled", "step_timeout_or_infra"),  # pip install hung
    ("success/cancelled/cancelled", "step_timeout_or_infra"),  # setup-python hung (install skipped)
    ("cancelled/cancelled/cancelled", "step_timeout_or_infra"),  # checkout hung
])
def test_classify_step_exports_failure_kind(tmp_path, outcomes, expected_kind):
    classify = [s for s in _jobs("ci.yml")["lint"]["steps"] if s.get("id") == "classify"][0]
    out = tmp_path / "github_output"
    completed = subprocess.run(
        ["bash", "-e", "-c", classify["run"]],
        capture_output=True, text=True, timeout=5,
        env={"SETUP_OUTCOMES": outcomes, "GITHUB_OUTPUT": str(out)},
    )
    assert completed.returncode == 0, completed.stderr
    assert out.read_text(encoding="utf-8").strip() == f"failure_kind={expected_kind}"


def test_ci_report_distinguishes_infrastructure_from_code():
    report = _jobs("ci.yml")["report"]["steps"][0]
    env_text = " ".join(str(v) for v in report["env"].values())
    assert env_text.count("outputs.failure_kind") == 4, (
        "report must read failure_kind from all four CI jobs"
    )
    script = report["run"]
    assert "step_timeout_or_infra" in script
    assert "not your code" in script  # infrastructure attribution path
    assert "real failure" in script  # genuine code-failure path
    assert "$GITHUB_STEP_SUMMARY" in script  # contributor sees the breakdown


def test_labeler_explains_its_own_failures():
    steps = _jobs("labeler.yml")["label"]["steps"]
    assert any(s.get("id") == "labeler" for s in steps), "labeler action step needs an id"
    explain = [s for s in steps if s.get("name") == "Explain label failure"]
    assert len(explain) == 1, "label job must annotate timeout vs non-timeout failure"
    assert "timed out" in explain[0]["run"] and "NOT a problem with your PR" in explain[0]["run"]
