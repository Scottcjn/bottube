# SPDX-License-Identifier: MIT
"""Regression tests for BoTTube CI workflow timeouts and step-timeout attribution (#16472)."""

from __future__ import annotations

from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"


def _load_workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS_DIR / name).read_text(encoding="utf-8"))


def test_every_workflow_job_and_step_has_explicit_timeout():
    """Every job and step across all BoTTube workflows must define timeout-minutes."""
    workflow_files = sorted(p.name for p in WORKFLOWS_DIR.glob("*.yml"))
    assert workflow_files == [
        "bottube-verify.yml",
        "ci.yml",
        "labeler.yml",
        "python-sdk.yml",
        "rtc-reward.yml",
    ]

    for wf_name in workflow_files:
        wf = _load_workflow(wf_name)
        jobs = wf.get("jobs", {})
        assert jobs, f"{wf_name} has no jobs"
        for job_id, job_cfg in jobs.items():
            assert isinstance(job_cfg.get("timeout-minutes"), int), (
                f"{wf_name}:{job_id} missing job-level timeout-minutes"
            )
            assert 1 <= job_cfg["timeout-minutes"] <= 30
            steps = job_cfg.get("steps", [])
            assert steps, f"{wf_name}:{job_id} has no steps"
            for idx, step in enumerate(steps):
                assert isinstance(step.get("timeout-minutes"), int), (
                    f"{wf_name}:{job_id} step #{idx} ({step.get('name', step.get('uses'))}) "
                    "missing step-level timeout-minutes"
                )


def test_ci_jobs_export_failure_kind_distinguishing_step_timeout_from_code_failure():
    """When a step times out inside a job, GitHub Actions sets needs.<job>.result='failure'
    (not 'cancelled'). Each CI job must export outputs.failure_kind so the report job
    distinguishes step timeouts / infra errors from genuine code failures."""
    ci = _load_workflow("ci.yml")
    jobs = ci["jobs"]

    for job_id in ("lint", "test", "security", "deployment-drift"):
        job = jobs[job_id]
        outputs = job.get("outputs", {})
        assert "failure_kind" in outputs, f"{job_id} must export outputs.failure_kind"
        steps_by_id = {s.get("id"): s for s in job["steps"] if s.get("id")}
        assert "classify" in steps_by_id, f"{job_id} missing classify step"
        classify_run = steps_by_id["classify"]["run"]
        assert "step_timeout_or_infra" in classify_run
        assert "code_failure" in classify_run

    # Upload coverage must not fail the test job when Codecov is unreachable or tokenless on fork PRs
    test_steps = {s.get("id"): s for s in jobs["test"]["steps"] if s.get("id")}
    assert test_steps["codecov"].get("continue-on-error") is True

    # Report job must check both cancelled and step_timeout_or_infra
    report_run = jobs["report"]["steps"][0]["run"]
    assert "step_timeout_or_infra" in report_run
    assert "GITHUB_STEP_SUMMARY" in report_run
