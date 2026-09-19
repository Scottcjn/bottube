# SPDX-License-Identifier: MIT
"""Footer stats API tests.

Task: #2138 - Fix BoTTube footer stats showing '--' by wiring real backend values
"""
from __future__ import annotations
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

ROOT: Path = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_footer_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_footer_bootstrap.db")

_orig_sqlite_connect: Any = sqlite3.connect


def _bootstrap_sqlite_connect(path: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
    """Redirect database path for testing."""
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages

_orig_init_store_db: Any = paypal_packages.init_store_db


def _test_init_store_db(db_path: str | None = None) -> None:
    """Initialize test database."""
    bootstrap_path: str = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    Path(bootstrap_path).unlink(missing_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[Any, None, None]:
    """Create test client with isolated database."""
    db_path: Path = tmp_path / "bottube_footer.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server._footer_counters_cache["ts"] = 0.0
    bottube_server._footer_counters_cache["data"] = None
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, api_key: str, *, is_human: bool = False) -> int:
    """Helper to insert an agent for testing."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', ?, ?, ?)
            """,
            (agent_name, agent_name.title(), api_key, 1 if is_human else 0, 1.0, 1.0),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(agent_id: int, title: str = "Test Video") -> int:
    """Helper to insert a video for testing."""
    import uuid
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        video_id = str(uuid.uuid4())
        cur = db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, description, filename, thumbnail, duration_sec, views, likes, created_at)
            VALUES (?, ?, ?, '', '', '', 8, 0, 0, ?)
            """,
            (video_id, agent_id, title, 1.0),
        )
        db.commit()
        return int(cur.lastrowid)


class TestFooterCounters:
    """Tests for /api/footer-counters endpoint."""

    def test_footer_counters_returns_valid_json(self, client: Any) -> None:
        """Test that footer-counters returns valid JSON structure."""
        resp: Any = client.get("/api/footer-counters")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")
        
        data: Dict = resp.get_json()
        assert "stats" in data
        assert "bottube" in data
        assert "clawrtc" in data
        assert "grazer" in data

    def test_footer_counters_stats_structure(self, client: Any) -> None:
        """Test that stats section has expected fields."""
        resp: Any = client.get("/api/footer-counters")
        assert resp.status_code == 200
        
        data: Dict = resp.get_json()
        stats: Dict = data.get("stats", {})
        
        assert "videos" in stats
        assert "agents" in stats
        assert "humans" in stats
        assert isinstance(stats["videos"], int)
        assert isinstance(stats["agents"], int)
        assert isinstance(stats["humans"], int)

    def test_footer_counters_bottube_downloads(self, client: Any) -> None:
        """Test that BoTTube downloads have fallback values."""
        resp: Any = client.get("/api/footer-counters")
        assert resp.status_code == 200
        
        data: Dict = resp.get_json()
        bottube: Dict = data.get("bottube", {})
        downloads: Dict = bottube.get("downloads", {})
        
        # Should have fallback values, not zeros
        assert "clawhub" in downloads
        assert "npm" in downloads
        assert "pypi" in downloads
        # Fallback defaults ensure non-zero values
        assert downloads["clawhub"] > 0
        assert downloads["npm"] > 0
        assert downloads["pypi"] > 0

    def test_footer_counters_clawrtc_downloads(self, client: Any) -> None:
        """Test that ClawRTC downloads have fallback values."""
        resp: Any = client.get("/api/footer-counters")
        assert resp.status_code == 200
        
        data: Dict = resp.get_json()
        clawrtc: Dict = data.get("clawrtc", {})
        downloads: Dict = clawrtc.get("downloads", {})
        
        assert "clawhub" in downloads
        assert "npm" in downloads
        assert "pypi" in downloads
        assert downloads["clawhub"] > 0
        assert downloads["npm"] > 0
        assert downloads["pypi"] > 0

    def test_footer_counters_grazer_downloads(self, client: Any) -> None:
        """Test that Grazer downloads have fallback values."""
        resp: Any = client.get("/api/footer-counters")
        assert resp.status_code == 200
        
        data: Dict = resp.get_json()
        grazer: Dict = data.get("grazer", {})
        downloads: Dict = grazer.get("downloads", {})
        
        assert "clawhub" in downloads
        assert "npm" in downloads
        assert "pypi" in downloads
        assert downloads["clawhub"] > 0
        assert downloads["npm"] > 0
        assert downloads["pypi"] > 0

    def test_footer_counters_github_stats(self, client: Any) -> None:
        """Test that GitHub stats are present."""
        resp: Any = client.get("/api/footer-counters")
        assert resp.status_code == 200
        
        data: Dict = resp.get_json()
        
        # BoTTube GitHub stats
        bottube_github: Dict = data.get("bottube", {}).get("github", {})
        assert "stars" in bottube_github
        assert "forks" in bottube_github
        assert "clones" in bottube_github
        
        # ClawRTC GitHub stats
        clawrtc_github: Dict = data.get("clawrtc", {}).get("github", {})
        assert "stars" in clawrtc_github
        assert "forks" in clawrtc_github

    def test_footer_counters_with_real_data(self, client: Any) -> None:
        """Test footer counters with actual database data."""
        # Insert test data
        agent_id = _insert_agent("TestAgent", "test-key-123")
        human_id = _insert_agent("TestHuman", "test-key-456", is_human=True)
        _insert_video(agent_id, "AI Generated Video")
        _insert_video(agent_id, "Another AI Video")
        
        resp: Any = client.get("/api/footer-counters")
        assert resp.status_code == 200
        
        data: Dict = resp.get_json()
        stats: Dict = data.get("stats", {})
        
        # Should reflect actual database counts
        assert stats["videos"] >= 2
        assert stats["agents"] >= 1
        assert stats["humans"] >= 1

    def test_footer_counters_caching(self, client: Any) -> None:
        """Test that footer counters are cached."""
        # First request
        resp1: Any = client.get("/api/footer-counters")
        assert resp1.status_code == 200
        data1: Dict = resp1.get_json()
        
        # Second request should use cache (within 60s TTL)
        resp2: Any = client.get("/api/footer-counters")
        assert resp2.status_code == 200
        data2: Dict = resp2.get_json()
        
        # Cache should return same timestamp
        assert data1.get("ts") == data2.get("ts")

    def test_read_download_cache_returns_defaults(self) -> None:
        """Test that _read_download_cache returns defaults when file is missing."""
        # Ensure no cache file exists in test environment
        cache = bottube_server._read_download_cache()
        
        # Should return defaults, not empty dict
        assert isinstance(cache, dict)
        assert len(cache) > 0
        # Check some expected default keys
        assert "clawhub" in cache or cache.get("clawhub", 0) > 0

    def test_download_cache_defaults_constant(self) -> None:
        """Test that download cache defaults are properly defined."""
        defaults = bottube_server._DOWNLOAD_CACHE_DEFAULTS
        
        assert isinstance(defaults, dict)
        assert "clawhub" in defaults
        assert "npm" in defaults
        assert "pypi" in defaults
        assert defaults["clawhub"] > 0
        assert defaults["npm"] > 0
        assert defaults["pypi"] > 0


class TestIndividualDownloadEndpoints:
    """Tests for individual download counter endpoints."""

    def test_clawhub_downloads_endpoint(self, client: Any) -> None:
        """Test /api/clawhub-downloads returns valid response."""
        resp: Any = client.get("/api/clawhub-downloads")
        assert resp.status_code == 200
        data: Dict = resp.get_json()
        assert "downloads" in data
        assert isinstance(data["downloads"], int)

    def test_npm_downloads_endpoint(self, client: Any) -> None:
        """Test /api/npm-downloads returns valid response."""
        resp: Any = client.get("/api/npm-downloads")
        assert resp.status_code == 200
        data: Dict = resp.get_json()
        assert "downloads" in data
        assert isinstance(data["downloads"], int)

    def test_pypi_downloads_endpoint(self, client: Any) -> None:
        """Test /api/pypi-downloads returns valid response."""
        resp: Any = client.get("/api/pypi-downloads")
        assert resp.status_code == 200
        data: Dict = resp.get_json()
        assert "downloads" in data
        assert isinstance(data["downloads"], int)


class TestPlatformStatsVisibility:
    """Tests for /api/stats public vs non-public visibility denominators (#1883)."""

    def test_api_stats_public_denominators(self, client: Any) -> None:
        """Verify banned agents, removed videos, and non-public metrics are excluded."""
        with bottube_server.app.app_context():
            db = bottube_server.get_db()
            # 1 visible bot agent
            bot_cur = db.execute(
                "INSERT INTO agents (agent_name, display_name, api_key, is_human, is_banned, created_at, last_active) VALUES ('goodbot', 'Good Bot', 'k1', 0, 0, 1.0, 1.0)"
            )
            good_bot_id = int(bot_cur.lastrowid)

            # 1 visible human agent
            human_cur = db.execute(
                "INSERT INTO agents (agent_name, display_name, api_key, is_human, is_banned, created_at, last_active) VALUES ('goodhuman', 'Good Human', 'k2', 1, 0, 1.0, 1.0)"
            )
            good_human_id = int(human_cur.lastrowid)

            # 1 banned agent
            banned_cur = db.execute(
                "INSERT INTO agents (agent_name, display_name, api_key, is_human, is_banned, created_at, last_active) VALUES ('bannedguy', 'Banned Guy', 'k3', 0, 1, 1.0, 1.0)"
            )
            banned_id = int(banned_cur.lastrowid)

            # Videos:
            # - Visible bot video: 10 views, 2 likes
            db.execute(
                "INSERT INTO videos (video_id, agent_id, title, filename, thumbnail, duration_sec, views, likes, is_removed, created_at) VALUES ('v1', ?, 'Bot V1', 'f1.mp4', 't1.jpg', 60, 10, 2, 0, 1.0)",
                (good_bot_id,),
            )
            # - Removed video from visible bot: 100 views, 20 likes
            db.execute(
                "INSERT INTO videos (video_id, agent_id, title, filename, thumbnail, duration_sec, views, likes, is_removed, created_at) VALUES ('v2', ?, 'Bot V2 Removed', 'f2.mp4', 't2.jpg', 60, 100, 20, 1, 1.0)",
                (good_bot_id,),
            )
            # - Visible human video: 5 views, 1 like
            db.execute(
                "INSERT INTO videos (video_id, agent_id, title, filename, thumbnail, duration_sec, views, likes, is_removed, created_at) VALUES ('v3', ?, 'Human V1', 'f3.mp4', 't3.jpg', 60, 5, 1, 0, 1.0)",
                (good_human_id,),
            )
            # - Video from banned agent: 200 views, 30 likes
            db.execute(
                "INSERT INTO videos (video_id, agent_id, title, filename, thumbnail, duration_sec, views, likes, is_removed, created_at) VALUES ('v4', ?, 'Banned V1', 'f4.mp4', 't4.jpg', 60, 200, 30, 0, 1.0)",
                (banned_id,),
            )

            # Comments:
            # - Valid comment on visible video
            db.execute(
                "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES ('v1', ?, 'Nice', 1.0)",
                (good_human_id,),
            )
            # - Valid comment on another visible video
            db.execute(
                "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES ('v3', ?, 'Cool', 1.0)",
                (good_bot_id,),
            )
            # - Comment from banned agent (must be excluded)
            db.execute(
                "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES ('v1', ?, 'Spam', 1.0)",
                (banned_id,),
            )
            # - Comment on removed video (must be excluded)
            db.execute(
                "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES ('v2', ?, 'Removed vid comment', 1.0)",
                (good_human_id,),
            )
            # - Comment on banned video (must be excluded)
            db.execute(
                "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES ('v4', ?, 'Banned vid comment', 1.0)",
                (good_human_id,),
            )
            db.commit()

        resp = client.get("/api/stats")
        assert resp.status_code == 200
        stats = resp.get_json()

        assert stats["videos"] == 2
        assert stats["agents"] == 1
        assert stats["humans"] == 1
        assert stats["total_views"] == 15
        assert stats["total_likes"] == 3
        assert stats["total_comments"] == 2

        # top_agents should exclude banned agents and removed videos
        agent_names = [a["agent_name"] for a in stats["top_agents"]]
        assert "bannedguy" not in agent_names
        good_bot_stat = next(a for a in stats["top_agents"] if a["agent_name"] == "goodbot")
        assert good_bot_stat["video_count"] == 1
        assert good_bot_stat["total_views"] == 10

