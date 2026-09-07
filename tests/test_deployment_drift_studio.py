# SPDX-License-Identifier: MIT
"""Keep Studio declarations in both offline deployment-drift inventories."""

from pathlib import Path

import pytest

from deployment_drift import MISSING_IN_CODE, build_report, load_config


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_NAMES = (
    "deployment-drift.json",
    "deployment-drift.issue-1410.example.json",
)
STUDIO_SOURCE = "studio_blueprint.py"
STUDIO_OPERATION = {"method": "POST", "path": "/api/studio/generate"}


@pytest.mark.parametrize("config_name", CONFIG_NAMES)
def test_studio_is_inventoried_without_a_drift_allowance(config_name):
    config = load_config(REPO_ROOT / config_name)

    report = build_report(REPO_ROOT, config)

    assert STUDIO_SOURCE in report["inventory"]["application_sources"]
    assert STUDIO_OPERATION not in report["blocking"]["missing_in_code"]
    assert STUDIO_OPERATION not in report["allowed"]["missing_in_code"]
    assert report["exit_code"] == 0


@pytest.mark.parametrize("config_name", CONFIG_NAMES)
def test_omitting_studio_source_still_reports_missing_code(config_name):
    config = load_config(REPO_ROOT / config_name)
    config["application_sources"] = [
        source for source in config["application_sources"] if source != STUDIO_SOURCE
    ]

    report = build_report(REPO_ROOT, config)

    assert STUDIO_OPERATION in report["blocking"]["missing_in_code"]
    assert STUDIO_OPERATION not in report["allowed"]["missing_in_code"]
    assert report["exit_code"] & MISSING_IN_CODE
