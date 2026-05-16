# SPDX-License-Identifier: MIT
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validate_recommendation import ValidationResult, generate_report


def test_validation_result_defaults_to_passing_empty_state():
    result = ValidationResult("Smoke")

    assert result.to_dict() == {
        "name": "Smoke",
        "passed": True,
        "errors": [],
        "warnings": [],
        "metrics": {},
    }


def test_validation_result_records_errors_warnings_and_metrics():
    result = ValidationResult("Recommendation Drift")

    result.add_warning("score spread is narrow")
    result.add_metric("recommendation_time_ms", 12.34567)
    result.add_error("missing video_id")

    assert result.passed is False
    assert result.to_dict()["warnings"] == ["score spread is narrow"]
    assert result.to_dict()["errors"] == ["missing video_id"]
    assert result.to_dict()["metrics"] == {"recommendation_time_ms": 12.34567}


def test_generate_report_formats_pass_fail_metrics_and_messages():
    passing = ValidationResult("Freshness")
    passing.add_metric("fresh_score", 1.0)

    failing = ValidationResult("Diversity")
    failing.add_warning("category skew detected")
    failing.add_error("agent penalty did not apply")

    report = generate_report([passing, failing])

    assert "SUMMARY: 1/2 tests passed" in report
    assert "[PASS] Freshness" in report
    assert "- fresh_score: 1.0000" in report
    assert "[FAIL] Diversity" in report
    assert "- category skew detected" in report
    assert "- agent penalty did not apply" in report
    assert "VALIDATION FAILED - 1 test(s) failed" in report


def test_generate_report_declares_success_when_all_results_pass():
    result = ValidationResult("Performance")
    result.add_metric("videos_processed", 100)

    report = generate_report([result])

    assert "SUMMARY: 1/1 tests passed" in report
    assert "- videos_processed: 100" in report
    assert "VALIDATION PASSED - All tests successful" in report
