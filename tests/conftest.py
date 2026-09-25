# SPDX-License-Identifier: MIT
"""
Shared pytest fixtures for BoTTube tests.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

from ci_quarantine import QUARANTINE_ISSUE, QUARANTINED

# Modules that cannot be imported at all: each tests a helper that was never
# merged to main (the test half of a squash-merged PR landed without the code
# half). Tracked in QUARANTINE_ISSUE; delete a line here once its module
# imports again.
collect_ignore = [
    "test_gpu_marketplace_completion_concurrency.py",  # gpu_marketplace._complete_gpu_job_transaction (#2166)
    "test_gpu_marketplace_fail_state.py",  # gpu_marketplace._release_gpu_job_transaction (#2168)
    "test_gpu_marketplace_start_state.py",  # gpu_marketplace._start_gpu_job_transaction (#2170)
]


def pytest_collection_modifyitems(config, items):
    """Mark each quarantined node ID xfail(strict=True); fail on stale entries.

    Strict means a quarantined test that starts passing turns the run red, so
    the list can only shrink. An entry whose module was collected but whose
    node ID no longer exists (renamed/removed test) is a collection error for
    the same reason: the list must not silently rot.
    """
    seen = set()
    collected_files = set()
    for item in items:
        collected_files.add(item.nodeid.split("::", 1)[0])
        reason = QUARANTINED.get(item.nodeid)
        if reason is not None:
            seen.add(item.nodeid)
            item.add_marker(
                pytest.mark.xfail(strict=True, reason=f"quarantined ({QUARANTINE_ISSUE}): {reason}")
            )
    # Only judge staleness when whole modules were collected unfiltered;
    # a run of one node ID, -k/-m, --deselect or --lf legitimately omits
    # other quarantined tests from the same module.
    partial = (
        any("::" in str(arg) for arg in config.args)
        or config.getoption("keyword")
        or config.getoption("markexpr")
        or config.getoption("deselect")
        or config.getoption("lf", False)
    )
    stale = [] if partial else sorted(
        nid for nid in QUARANTINED
        if nid not in seen and nid.split("::", 1)[0] in collected_files
    )
    if stale:
        raise pytest.UsageError(
            "tests/ci_quarantine.py lists node IDs that were not collected "
            "(renamed or removed?); delete them:\n  " + "\n  ".join(stale)
        )


@pytest.fixture
def app():
    """Create a test Flask app with an in-memory database."""
    # We need to set up the environment before importing bottube_server
    server_path = Path(__file__).resolve().parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["BOTTUBE_BASE_DIR"] = tmpdir
        db_path = Path(tmpdir) / "bottube.db"
        video_dir = Path(tmpdir) / "videos"
        thumb_dir = Path(tmpdir) / "thumbnails"
        avatar_dir = Path(tmpdir) / "avatars"
        video_dir.mkdir()
        thumb_dir.mkdir()
        avatar_dir.mkdir()

        # Bootstrap database schema by running the init from the server
        # Ensure fresh import
        for mod_name in list(sys.modules.keys()):
            if "bottube_server" in mod_name:
                del sys.modules[mod_name]
            if "paypal_packages" in mod_name:
                del sys.modules[mod_name]
            if "gpu_marketplace" in mod_name:
                del sys.modules[mod_name]
            if "banano_blueprint" in mod_name:
                del sys.modules[mod_name]
            if "captions_blueprint" in mod_name:
                del sys.modules[mod_name]

        sys.path.insert(0, str(server_path))
        
        # Set DB path before importing
        import bottube_server
        bottube_server.DB_PATH = db_path
        bottube_server.VIDEO_DIR = video_dir
        bottube_server.THUMB_DIR = thumb_dir
        bottube_server.AVATAR_DIR = avatar_dir

        flask_app = bottube_server.app
        flask_app.config["TESTING"] = True
        flask_app.config["DB_PATH"] = str(db_path)
        flask_app.config["SECRET_KEY"] = "test-secret-key"
        # Use the templates from the project
        flask_app.template_folder = str(server_path / "bottube_templates")

        with flask_app.app_context():
            bottube_server.init_db()

        yield flask_app


@pytest.fixture
def client(app):
    """Return a Flask test client."""
    return app.test_client()


@pytest.fixture
def registered_agent(client):
    """Register a test agent and return dict with agent_name and api_key."""
    resp = client.post("/api/register", json={
        "agent_name": "test_discoverability_bot",
        "display_name": "Discoverability Test Bot",
        "bio": "A bot for testing discoverability features",
    })
    data = resp.get_json()
    assert resp.status_code == 201, f"Registration failed: {data}"
    return {"agent_name": data["agent_name"], "api_key": data["api_key"]}
