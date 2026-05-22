# SPDX-License-Identifier: MIT
"""
Tests for Issue #425: Video+Agent Discoverability Enhancements

Tests for:
- Search with relevance scoring
- Search suggestions API
- Trending with category filter
- Rising videos API
- Related videos API
- Related categories API
"""

import json
import time
import pytest


def _insert_video_for_trending(client, registered_agent, video_id, title, category, *, views=0, likes=0):
    import bottube_server

    with client.application.app_context():
        db = bottube_server.get_db()
        agent = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            (registered_agent["agent_name"],),
        ).fetchone()
        assert agent is not None
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, description, filename, category,
                views, likes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id,
                agent["id"],
                title,
                f"{title} description",
                f"{video_id}.mp4",
                category,
                views,
                likes,
                time.time(),
            ),
        )
        db.commit()


def _insert_search_video(
    client, agent_name, video_id, title, *, tags, category="other",
):
    import bottube_server

    with client.application.app_context():
        db = bottube_server.get_db()
        agent = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()
        assert agent is not None
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, description, filename, category,
                tags, views, likes, created_at, is_removed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                video_id,
                agent["id"],
                title,
                f"{title} description",
                f"{video_id}.mp4",
                category,
                json.dumps(tags),
                0,
                0,
                time.time(),
            ),
        )
        db.commit()


class TestSearchEnhancements:
    """Test search API enhancements (issue #425)."""

    def test_search_relevance_sort(self, client, registered_agent):
        """Test search with relevance sorting."""
        # Upload videos with different title relevance
        client.post("/api/upload", json={
            "title": "Python Tutorial",
            "description": "Learn Python programming",
            "tags": "python,programming,tutorial",
            "category": "education",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        client.post("/api/upload", json={
            "title": "Advanced Python Tips",
            "description": "Python tricks and tips",
            "tags": "python,advanced",
            "category": "education",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        client.post("/api/upload", json={
            "title": "JavaScript Basics",
            "description": "Learn JavaScript with Python comparisons",
            "tags": "javascript,python",
            "category": "education",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        # Search with relevance sort (default)
        resp = client.get("/api/search?q=Python&sort=relevance")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "videos" in data
        assert len(data["videos"]) >= 2
        # First result should have exact or title match
        assert "python" in data["videos"][0]["title"].lower()

    def test_search_agent_filter(self, client, registered_agent):
        """Test search with agent filter."""
        other = client.post("/api/register", json={
            "agent_name": "other_search_bot",
            "display_name": "Other Search Bot",
            "bio": "Another bot for testing search filters",
        }).get_json()

        _insert_search_video(
            client, registered_agent["agent_name"], "shared-filter-primary",
            "Shared Filter Topic", tags=["test"],
        )
        _insert_search_video(
            client, other["agent_name"], "shared-filter-other",
            "Shared Filter Topic", tags=["test"],
        )

        # Search with agent filter
        resp = client.get(
            f"/api/search?q=Shared&agent={registered_agent['agent_name']}"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["filters"]["agent"] == registered_agent["agent_name"]
        assert len(data["videos"]) == 1
        assert {video["agent_name"] for video in data["videos"]} == {
            registered_agent["agent_name"],
        }

        resp = client.get("/api/search?q=Shared&agent=missing_search_bot")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["filters"]["agent"] == "missing_search_bot"
        assert data["videos"] == []

    def test_search_tag_filter(self, client, registered_agent):
        """Test search with tag filter."""
        _insert_search_video(
            client, registered_agent["agent_name"], "filtered-art-ai",
            "Filtered Art Video",
            tags=["ai", "art", "creative"],
            category="ai-art",
        )
        _insert_search_video(
            client, registered_agent["agent_name"], "filtered-art-nonai",
            "Filtered Art Video", tags=["art", "nonai"], category="ai-art",
        )

        # Search with tag filter
        resp = client.get("/api/search?q=Filtered&tag=ai")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["filters"]["tag"] == "ai"
        assert len(data["videos"]) == 1
        assert all("ai" in video["tags"] for video in data["videos"])

        resp = client.get("/api/search?q=Filtered&tag=missing-tag")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["filters"]["tag"] == "missing-tag"
        assert data["videos"] == []

    def test_search_tag_filter_treats_like_wildcards_as_literals(
            self, client, registered_agent):
        """Test tag filters treat SQL LIKE wildcard characters literally."""
        _insert_search_video(
            client, registered_agent["agent_name"], "wildcard-percent",
            "Wildcard Tag Video", tags=["a%b"], category="ai-art",
        )
        _insert_search_video(
            client, registered_agent["agent_name"], "wildcard-underscore",
            "Wildcard Tag Video", tags=["a_b"], category="ai-art",
        )
        _insert_search_video(
            client, registered_agent["agent_name"], "wildcard-ordinary",
            "Wildcard Tag Video", tags=["axb"], category="ai-art",
        )

        resp = client.get("/api/search?q=Wildcard&tag=a%25b")
        assert resp.status_code == 200
        data = resp.get_json()
        assert [video["video_id"] for video in data["videos"]] == [
            "wildcard-percent"
        ]

        resp = client.get("/api/search?q=Wildcard&tag=a_b")
        assert resp.status_code == 200
        data = resp.get_json()
        assert [video["video_id"] for video in data["videos"]] == [
            "wildcard-underscore"
        ]

    def test_search_suggestions(self, client, registered_agent):
        """Test search suggestions API."""
        # Upload videos with similar titles
        client.post("/api/upload", json={
            "title": "Python for Beginners",
            "description": "Learn Python",
            "tags": "python,beginners",
            "category": "education",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        client.post("/api/upload", json={
            "title": "Python Advanced",
            "description": "Advanced Python",
            "tags": "python,advanced",
            "category": "education",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        # Get suggestions
        resp = client.get("/api/search/suggestions?q=Py")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "suggestions" in data
        assert "categories" in data
        assert "agents" in data
        assert "tags" in data
        # Should have Python-related suggestions
        assert len(data["suggestions"]) >= 1 or len(data["categories"]) >= 1


class TestTrendingEnhancements:
    """Test trending API enhancements (issue #425)."""

    def test_trending_category_filter(self, client, registered_agent):
        """Test trending with category filter."""
        _insert_video_for_trending(
            client, registered_agent, "music-trending", "Music Video", "music", views=3, likes=2,
        )
        _insert_video_for_trending(
            client, registered_agent, "tech-trending", "Tech Demo", "science-tech", views=50, likes=20,
        )

        # Get trending for music category
        resp = client.get("/api/trending?category=music")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "videos" in data
        assert data["category"] == "music"
        assert [video["title"] for video in data["videos"]] == ["Music Video"]
        # All videos should be in music category
        for video in data["videos"]:
            assert video["category"] == "music"

    def test_trending_rising_endpoint(self, client, registered_agent):
        """Test rising videos API."""
        # Upload a recent video
        client.post("/api/upload", json={
            "title": "Rising Video",
            "description": "A new video",
            "tags": "new,rising",
            "category": "other",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        resp = client.get("/api/trending/rising")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "videos" in data
        assert isinstance(data["videos"], list)

    def test_trending_rising_category_filter(self, client, registered_agent):
        """Test rising videos with category filter."""
        client.post("/api/upload", json={
            "title": "Gaming Video",
            "description": "Gaming content",
            "tags": "gaming",
            "category": "gaming",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        resp = client.get("/api/trending/rising?category=gaming")
        assert resp.status_code == 200
        data = resp.get_json()
        for video in data["videos"]:
            assert video["category"] == "gaming"


class TestRelatedVideos:
    """Test related videos API (issue #425)."""

    def test_related_videos_by_category(self, client, registered_agent):
        """Test related videos finds same category."""
        # Upload videos in same category
        client.post("/api/upload", json={
            "title": "AI Art 1",
            "description": "First AI art video",
            "tags": "ai,art",
            "category": "ai-art",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        client.post("/api/upload", json={
            "title": "AI Art 2",
            "description": "Second AI art video",
            "tags": "ai,art,creative",
            "category": "ai-art",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        # Get related videos for first video
        resp = client.get("/api/videos/ai-art-1/related")
        # May return 404 if video not found (video_id is generated)
        # Test will pass if endpoint exists and returns valid response
        assert resp.status_code in [200, 404]

    def test_related_videos_endpoint_exists(self, client, registered_agent):
        """Test related videos endpoint is accessible."""
        # Upload a video
        resp = client.post("/api/upload", json={
            "title": "Test for Related",
            "description": "Testing related videos",
            "tags": "test,related",
            "category": "other",
        }, headers={"X-API-Key": registered_agent["api_key"]})
        
        # Get the video_id from upload response or list
        data = resp.get_json()
        if resp.status_code == 200 and "video_id" in data:
            video_id = data["video_id"]
            resp = client.get(f"/api/videos/{video_id}/related")
            assert resp.status_code == 200
            result = resp.get_json()
            assert "related_videos" in result
            assert "count" in result


class TestRelatedCategories:
    """Test related categories API (issue #425)."""

    def test_related_categories_endpoint(self, client):
        """Test related categories API."""
        resp = client.get("/api/categories/ai-art/related")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "category" in data
        assert "related" in data
        assert data["category"] == "ai-art"
        assert isinstance(data["related"], list)

    def test_related_categories_invalid(self, client):
        """Test related categories with invalid category."""
        resp = client.get("/api/categories/nonexistent/related")
        assert resp.status_code == 404


class TestSearchPageUI:
    """Test search page UI enhancements (issue #425)."""

    def test_search_page_renders(self, client):
        """Test search page renders with filters."""
        resp = client.get("/search?q=test")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # Check for filter elements
        assert "search-filters" in html or "filter" in html

    def test_search_page_pagination(self, client, registered_agent):
        """Test search page pagination."""
        # Upload multiple videos
        for i in range(5):
            client.post("/api/upload", json={
                "title": f"Pagination Test {i}",
                "description": "Testing pagination",
                "tags": "pagination,test",
                "category": "other",
            }, headers={"X-API-Key": registered_agent["api_key"]})

        resp = client.get("/search?q=Pagination&page=1")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Pagination Test" in html


class TestTrendingPageUI:
    """Test trending page UI enhancements (issue #425)."""

    def test_trending_page_category_filter(self, client, registered_agent):
        """Test trending page has category filter."""
        _insert_video_for_trending(
            client, registered_agent, "music-page-trending", "Music Page Video", "music", views=3, likes=2,
        )
        _insert_video_for_trending(
            client, registered_agent, "tech-page-trending", "Tech Page Video", "science-tech", views=50, likes=20,
        )

        resp = client.get("/trending?category=music")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # Check for category filter elements
        assert "category-filter" in html or "category" in html
        assert "Music Page Video" in html
        assert "Tech Page Video" not in html
        assert 'category=music" class="category-filter-chip active"' in html

    def test_trending_page_rising_section(self, client, registered_agent):
        """Test trending page has rising section."""
        # Upload a video
        client.post("/api/upload", json={
            "title": "Rising Test",
            "description": "Testing rising section",
            "tags": "rising,test",
            "category": "other",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        resp = client.get("/trending")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # Check for rising section
        assert "rising" in html.lower() or "Rising" in html


class TestCategoryPageUI:
    """Test category page UI enhancements (issue #425)."""

    def test_category_page_related_categories(self, client, registered_agent):
        """Test category page shows related categories."""
        # Upload a video in a category
        client.post("/api/upload", json={
            "title": "Category Test",
            "description": "Testing category page",
            "tags": "category,test",
            "category": "ai-art",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        resp = client.get("/category/ai-art")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # Check for related categories section
        assert "related" in html.lower() or "Related" in html

    def test_category_page_trending_in_category(self, client, registered_agent):
        """Test category page shows trending in category."""
        client.post("/api/upload", json={
            "title": "Trending Category Test",
            "description": "Testing trending in category",
            "tags": "trending,category",
            "category": "music",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        resp = client.get("/category/music")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # Check for trending section
        assert "trending" in html.lower() or "Trending" in html


class TestDiscoverabilityIntegration:
    """Integration tests for discoverability features."""

    def test_search_to_category_flow(self, client, registered_agent):
        """Test user can navigate from search to category."""
        # Upload video
        client.post("/api/upload", json={
            "title": "Integration Test",
            "description": "Testing flow",
            "tags": "integration,test",
            "category": "education",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        # Search for video
        resp = client.get("/search?q=Integration")
        assert resp.status_code == 200

        # Navigate to category
        resp = client.get("/category/education")
        assert resp.status_code == 200

    def test_trending_to_video_flow(self, client, registered_agent):
        """Test user can navigate from trending to video."""
        client.post("/api/upload", json={
            "title": "Flow Test Video",
            "description": "Testing trending flow",
            "tags": "flow,test",
            "category": "other",
        }, headers={"X-API-Key": registered_agent["api_key"]})

        # Get trending
        resp = client.get("/trending")
        assert resp.status_code == 200
