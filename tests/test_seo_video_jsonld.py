"""Regression tests for video JSON-LD metadata normalization."""

from datetime import datetime

from seo_routes import build_video_jsonld


def test_invalid_numeric_metadata_uses_safe_schema_defaults():
    """One malformed legacy field must not break the entire watch page."""
    result = build_video_jsonld(
        {
            "video_id": "legacy-video",
            "title": "Legacy video",
            "duration_sec": "unknown",
            "width": "HD",
            "height": None,
            "created_at": "not-a-timestamp",
            "views": "many",
            "comment_count": "none",
        },
        agent_name="legacy-agent",
        display_name="Legacy Agent",
        is_human=False,
    )

    assert result["duration"] == "PT8S"
    assert result["width"] == 720
    assert result["height"] == 720
    assert result["interactionStatistic"][0]["userInteractionCount"] == 0
    assert result["interactionStatistic"][1]["userInteractionCount"] == 0
    datetime.fromisoformat(result["uploadDate"])


def test_non_finite_numeric_metadata_uses_safe_schema_defaults():
    """NaN and infinity are not valid JSON-LD numeric values or timestamps."""
    result = build_video_jsonld(
        {
            "video_id": "non-finite-video",
            "duration_sec": "nan",
            "width": "inf",
            "height": "-inf",
            "created_at": "nan",
            "views": "inf",
            "comment_count": "nan",
        },
        agent_name="agent",
        display_name="Agent",
        is_human=False,
    )

    assert result["duration"] == "PT8S"
    assert result["width"] == 720
    assert result["height"] == 720
    assert [
        counter["userInteractionCount"]
        for counter in result["interactionStatistic"]
    ] == [0, 0]
    datetime.fromisoformat(result["uploadDate"])
