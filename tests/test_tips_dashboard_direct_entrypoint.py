"""Regression for issue #2242: direct execution must register /tips/dashboard."""
from pathlib import Path


def test_tips_dashboard_is_defined_before_direct_app_run():
    """Route decorators after app.run() are unreachable for `python bottube_server.py`."""
    source = (Path(__file__).resolve().parents[1] / "bottube_server.py").read_text(
        encoding="utf-8"
    )
    route = source.index('@app.route("/tips/dashboard")')
    direct_entrypoint = source.index('if __name__ == "__main__":')
    assert route < direct_entrypoint
