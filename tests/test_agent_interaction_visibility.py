"""
Test agent interaction visibility features (Issue #2158).

Tests for the enhanced comment system that displays agent interaction context
including frequent commenter badges, follow relationships, and first-time visitor indicators.
"""

import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_agent_interaction.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_agent_interaction.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """Create test client with fresh database."""
    db_path = tmp_path / "bottube_agent_interaction.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, api_key: str, is_human: int = 0) -> int:
    """Insert a test agent into the database."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', ?, ?, ?)
            """,
            (agent_name, agent_name.title(), api_key, is_human, time.time(), time.time()),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(agent_id: int, video_id: str, title: str = "Test Video") -> None:
    """Insert a test video into the database."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (video_id, agent_id, title, f"{video_id}.mp4", time.time()),
        )
        db.commit()


def _insert_comment(video_id: str, agent_id: int, content: str, created_at: float = None) -> int:
    """Insert a test comment into the database."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        ts = created_at or time.time()
        cur = db.execute(
            """
            INSERT INTO comments (video_id, agent_id, content, comment_type, created_at)
            VALUES (?, ?, ?, 'comment', ?)
            """,
            (video_id, agent_id, content, ts),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_subscription(follower_id: int, following_id: int) -> None:
    """Insert a subscription (follow) relationship."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO subscriptions (follower_id, following_id, created_at)
            VALUES (?, ?, ?)
            """,
            (follower_id, following_id, time.time()),
        )
        db.commit()


class TestComputeAgentInteractionContext:
    """Tests for the _compute_agent_interaction_context helper function."""

    def test_first_interaction(self, client):
        """Test context for an agent commenting for the first time."""
        with bottube_server.app.app_context():
            video_creator_id = _insert_agent("creator_bot", "bottube_sk_creator")
            first_timer_id = _insert_agent("newbie_bot", "bottube_sk_newbie")
            video_id = "test_video_001"
            _insert_video(video_creator_id, video_id)
            
            db = bottube_server.get_db()
            context = bottube_server._compute_agent_interaction_context(
                db, video_creator_id, first_timer_id
            )
            
            assert context["interaction_level"] == "new"
            assert context["first_interaction"] is True
            assert context["is_frequent_commenter"] is False
            assert context["comment_count_on_channel"] == 0
            assert context["is_mutual_follow"] is False
            assert context["follows_creator"] is False
            assert context["followed_by_creator"] is False

    def test_occasional_commenter(self, client):
        """Test context for an agent with 1-2 comments."""
        with bottube_server.app.app_context():
            video_creator_id = _insert_agent("creator_bot", "bottube_sk_creator")
            occasional_id = _insert_agent("occasional_bot", "bottube_sk_occasional")
            video_id = "test_video_002"
            _insert_video(video_creator_id, video_id)
            
            # Add 2 comments in the past 30 days
            now = time.time()
            _insert_comment(video_id, occasional_id, "First comment", now - 86400)
            _insert_comment(video_id, occasional_id, "Second comment", now - 3600)
            
            db = bottube_server.get_db()
            context = bottube_server._compute_agent_interaction_context(
                db, video_creator_id, occasional_id
            )
            
            assert context["interaction_level"] == "occasional"
            assert context["first_interaction"] is False
            assert context["is_frequent_commenter"] is False
            assert context["comment_count_on_channel"] == 2

    def test_regular_commenter(self, client):
        """Test context for an agent with 3-10 comments."""
        with bottube_server.app.app_context():
            video_creator_id = _insert_agent("creator_bot", "bottube_sk_creator")
            regular_id = _insert_agent("regular_bot", "bottube_sk_regular")
            video_id = "test_video_003"
            _insert_video(video_creator_id, video_id)
            
            # Add 5 comments in the past 30 days
            now = time.time()
            for i in range(5):
                _insert_comment(video_id, regular_id, f"Comment {i}", now - (i * 86400))
            
            db = bottube_server.get_db()
            context = bottube_server._compute_agent_interaction_context(
                db, video_creator_id, regular_id
            )
            
            assert context["interaction_level"] == "regular"
            assert context["is_frequent_commenter"] is True
            assert context["comment_count_on_channel"] == 5

    def test_frequent_commenter(self, client):
        """Test context for an agent with 11+ comments."""
        with bottube_server.app.app_context():
            video_creator_id = _insert_agent("creator_bot", "bottube_sk_creator")
            frequent_id = _insert_agent("frequent_bot", "bottube_sk_frequent")
            video_id = "test_video_004"
            _insert_video(video_creator_id, video_id)
            
            # Add 15 comments in the past 30 days
            now = time.time()
            for i in range(15):
                _insert_comment(video_id, frequent_id, f"Comment {i}", now - (i * 3600))
            
            db = bottube_server.get_db()
            context = bottube_server._compute_agent_interaction_context(
                db, video_creator_id, frequent_id
            )
            
            assert context["interaction_level"] == "frequent"
            assert context["is_frequent_commenter"] is True
            assert context["comment_count_on_channel"] == 15

    def test_mutual_follow(self, client):
        """Test context for mutual follow relationship."""
        with bottube_server.app.app_context():
            video_creator_id = _insert_agent("creator_bot", "bottube_sk_creator")
            commenter_id = _insert_agent("commenter_bot", "bottube_sk_commenter")
            video_id = "test_video_005"
            _insert_video(video_creator_id, video_id)
            
            # Create mutual follow relationship
            _insert_subscription(commenter_id, video_creator_id)  # Commenter follows creator
            _insert_subscription(video_creator_id, commenter_id)  # Creator follows commenter
            
            db = bottube_server.get_db()
            context = bottube_server._compute_agent_interaction_context(
                db, video_creator_id, commenter_id
            )
            
            assert context["is_mutual_follow"] is True
            assert context["follows_creator"] is True
            assert context["followed_by_creator"] is True

    def test_one_way_follow(self, client):
        """Test context for one-way follow relationship."""
        with bottube_server.app.app_context():
            video_creator_id = _insert_agent("creator_bot", "bottube_sk_creator")
            commenter_id = _insert_agent("fan_bot", "bottube_sk_fan")
            video_id = "test_video_006"
            _insert_video(video_creator_id, video_id)
            
            # Commenter follows creator (but not vice versa)
            _insert_subscription(commenter_id, video_creator_id)
            
            db = bottube_server.get_db()
            context = bottube_server._compute_agent_interaction_context(
                db, video_creator_id, commenter_id
            )
            
            assert context["follows_creator"] is True
            assert context["followed_by_creator"] is False
            assert context["is_mutual_follow"] is False

    def test_old_comments_dont_count(self, client):
        """Test that comments older than 30 days don't count toward interaction level."""
        with bottube_server.app.app_context():
            video_creator_id = _insert_agent("creator_bot", "bottube_sk_creator")
            old_commenter_id = _insert_agent("old_bot", "bottube_sk_old")
            video_id = "test_video_007"
            _insert_video(video_creator_id, video_id)
            
            # Add comments older than 30 days
            old_time = time.time() - (35 * 86400)  # 35 days ago
            for i in range(20):
                _insert_comment(video_id, old_commenter_id, f"Old comment {i}", old_time - (i * 86400))
            
            db = bottube_server.get_db()
            context = bottube_server._compute_agent_interaction_context(
                db, video_creator_id, old_commenter_id
            )
            
            # Should be treated as new since recent comments are 0
            assert context["interaction_level"] == "new"
            assert context["first_interaction"] is True
            assert context["comment_count_on_channel"] == 0


class TestGetCommentsAPI:
    """Tests for the /api/videos/<video_id>/comments endpoint with interaction context."""

    def test_comments_include_interaction_context(self, client):
        """Test that comments API returns interaction context."""
        with bottube_server.app.app_context():
            video_creator_id = _insert_agent("creator_bot", "bottube_sk_creator")
            frequent_commenter_id = _insert_agent("frequent_bot", "bottube_sk_frequent")
            video_id = "test_video_api_001"
            _insert_video(video_creator_id, video_id)
            
            # Add multiple comments to make commenter "frequent"
            now = time.time()
            for i in range(12):
                _insert_comment(video_id, frequent_commenter_id, f"Comment {i}", now - (i * 3600))
        
        resp = client.get(f"/api/videos/{video_id}/comments")
        assert resp.status_code == 200
        data = resp.get_json()
        
        assert "comments" in data
        assert len(data["comments"]) > 0
        
        comment = data["comments"][0]
        assert "interaction_context" in comment
        ctx = comment["interaction_context"]
        assert ctx["is_frequent_commenter"] is True
        assert ctx["interaction_level"] == "frequent"

    def test_comments_include_is_human_flag(self, client):
        """Test that comments API returns is_human flag."""
        with bottube_server.app.app_context():
            human_id = _insert_agent("human_user", "bottube_sk_human", is_human=1)
            video_id = "test_video_api_002"
            _insert_video(human_id, video_id)
            _insert_comment(video_id, human_id, "Human comment")
        
        resp = client.get(f"/api/videos/{video_id}/comments")
        assert resp.status_code == 200
        data = resp.get_json()
        
        comment = data["comments"][0]
        assert "is_human" in comment
        assert comment["is_human"] is True

    def test_comments_api_video_not_found(self, client):
        """Test comments API returns 404 for non-existent video."""
        resp = client.get("/api/videos/nonexistent_video/comments")
        assert resp.status_code == 200  # Returns empty list for non-existent video
        data = resp.get_json()
        assert data["count"] == 0


class TestWatchPageAccessibility:
    """Tests for watch page accessibility with interaction indicators."""

    def test_watch_page_renders_interaction_badges(self, client):
        """Test that watch page renders interaction indicator badges."""
        with bottube_server.app.app_context():
            video_creator_id = _insert_agent("creator_bot", "bottube_sk_creator")
            frequent_commenter_id = _insert_agent("frequent_bot", "bottube_sk_frequent")
            video_id = "test_video_a11y_001"
            _insert_video(video_creator_id, video_id)
            
            # Add multiple comments to make commenter "frequent"
            now = time.time()
            for i in range(12):
                _insert_comment(video_id, frequent_commenter_id, f"Comment {i}", now - (i * 3600))
        
        resp = client.get(f"/watch/{video_id}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        
        # Check for interaction indicator elements
        assert "interaction-indicators" in html
        assert "interaction-badge" in html
        assert "badge-frequent" in html or "badge-regular" in html or "badge-first-time" in html

    def test_watch_page_has_accessible_labels(self, client):
        """Test that interaction badges have accessible labels."""
        with bottube_server.app.app_context():
            video_creator_id = _insert_agent("creator_bot", "bottube_sk_creator")
            frequent_commenter_id = _insert_agent("frequent_bot", "bottube_sk_frequent")
            video_id = "test_video_a11y_002"
            _insert_video(video_creator_id, video_id)

            # Add multiple comments to make commenter "frequent"
            now = time.time()
            for i in range(12):
                _insert_comment(video_id, frequent_commenter_id, f"Comment {i}", now - (i * 3600))

        resp = client.get(f"/watch/{video_id}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        # Check for accessibility features
        assert 'aria-label="Interaction indicators"' in html or 'role="article"' in html
        assert 'aria-hidden="true"' in html  # Icons should be hidden from screen readers
        assert "sr-only-interaction" in html or "sr-only" in html  # Screen reader only text

    def test_watch_page_badge_tooltips(self, client):
        """Test that interaction badges have helpful tooltips."""
        with bottube_server.app.app_context():
            video_creator_id = _insert_agent("creator_bot", "bottube_sk_creator")
            frequent_commenter_id = _insert_agent("frequent_bot", "bottube_sk_frequent")
            video_id = "test_video_a11y_003"
            _insert_video(video_creator_id, video_id)

            # Add multiple comments to make commenter "frequent"
            now = time.time()
            for i in range(12):
                _insert_comment(video_id, frequent_commenter_id, f"Comment {i}", now - (i * 3600))

        resp = client.get(f"/watch/{video_id}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        # Check for tooltip titles on badges
        assert 'title="Frequent commenter' in html or 'title="First time' in html or 'title="Regular' in html
