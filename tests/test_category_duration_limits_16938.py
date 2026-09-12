import pytest
import bottube_server


def test_education_and_science_tech_allow_7_minute_explainers():
    """Verify education and science-tech categories allow up to 420s (7 min)."""
    edu_limits = bottube_server.get_category_limits("education")
    assert edu_limits["max_duration"] >= 420, "education category must admit up to 420 seconds (7 minutes)"
    assert edu_limits["max_file_mb"] >= 25, "education category file size must be at least 25 MB"

    st_limits = bottube_server.get_category_limits("science-tech")
    assert st_limits["max_duration"] >= 420, "science-tech category must admit up to 420 seconds (7 minutes)"
    assert st_limits["max_file_mb"] >= 25, "science-tech category file size must be at least 25 MB"

    sci_limits = bottube_server.get_category_limits("science")
    assert sci_limits["max_duration"] >= 420, "science category must admit up to 420 seconds (7 minutes)"
    assert sci_limits["max_file_mb"] >= 25, "science category file size must be at least 25 MB"


def test_bounty_12787_duration_range_admitted():
    """Verify 3-7 minute technical explainers (180s to 420s) are fully admitted.

    Bounty #12787 requires a 3-7 minute technical explainer on BoTTube.
    Previously, education and science-tech were capped at 120s, causing
    any compliant 180s+ submission to be rejected with HTTP 400.
    """
    edu_limits = bottube_server.get_category_limits("education")
    max_dur = edu_limits["max_duration"]

    # Minimum bounty duration: 3 min (180s)
    min_bounty_dur = 180
    assert min_bounty_dur <= max_dur, f"3-minute ({min_bounty_dur}s) explainer must not exceed max {max_dur}s"

    # Maximum bounty duration: 7 min (420s)
    max_bounty_dur = 420
    assert max_bounty_dur <= max_dur, f"7-minute ({max_bounty_dur}s) explainer must not exceed max {max_dur}s"

    # Beyond maximum (> 420s) is properly bounded
    over_dur = 421
    assert over_dur > max_dur, f"Duration exceeding 420s should trigger limit enforcement"


def test_get_category_limits_respects_custom_env_overrides(monkeypatch):
    """Verify operators can override category duration and size via environment variables."""
    monkeypatch.setenv("BOTTUBE_MAX_DURATION_EDUCATION", "600")
    monkeypatch.setenv("BOTTUBE_MAX_FILE_MB_EDUCATION", "50")

    limits = bottube_server.get_category_limits("education")
    assert limits["max_duration"] == 600
    assert limits["max_file_mb"] == 50


def test_get_category_limits_science_tech_env_override(monkeypatch):
    """Verify hyphenated category name translates cleanly to uppercase env var."""
    monkeypatch.setenv("BOTTUBE_MAX_DURATION_SCIENCE_TECH", "500")
    monkeypatch.setenv("BOTTUBE_MAX_FILE_MB_SCIENCE_TECH", "35")

    limits = bottube_server.get_category_limits("science-tech")
    assert limits["max_duration"] == 500
    assert limits["max_file_mb"] == 35


def test_api_categories_exposes_duration_and_size_limits(client):
    """Verify GET /api/categories endpoint returns max_duration and max_file_mb metadata."""
    resp = client.get("/api/categories")
    assert resp.status_code == 200

    data = resp.get_json()
    assert "categories" in data
    cats_by_id = {c["id"]: c for c in data["categories"]}

    assert "education" in cats_by_id
    edu = cats_by_id["education"]
    assert "max_duration" in edu
    assert edu["max_duration"] >= 420
    assert "max_file_mb" in edu
    assert edu["max_file_mb"] >= 25

    assert "science-tech" in cats_by_id
    st = cats_by_id["science-tech"]
    assert "max_duration" in st
    assert st["max_duration"] >= 420
    assert "max_file_mb" in st
    assert st["max_file_mb"] >= 25
