"""
Tests for Creator Collaboration Features (Issue #427)

Tests cover:
- Creating collaborations (duets/co-uploads/remixes)
- Managing collaboration invitations
- Joining/leaving collaborations
- Adding videos to collaborations
- Collaborative playlists
"""

import json
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Import server module components needed for testing
import bottube_server as server


class TestCollaborationFeatures:
    """Test suite for creator collaboration features."""

    @pytest.fixture
    def db_path(self, tmp_path):
        """Create a temporary database for testing."""
        db_file = tmp_path / "test_bottube.db"
        # Set DB_PATH early
        server.DB_PATH = db_file
        return db_file

    @pytest.fixture
    def app(self, db_path):
        """Create test Flask app with test database."""
        app = server.app
        app.config["TESTING"] = True
        app.config["SERVER_NAME"] = "localhost"
        app.config["APPLICATION_ROOT"] = "/"

        # Initialize database with the schema
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(server.SCHEMA)

        # Run migrations
        server.init_db()
        conn.commit()
        conn.close()

        yield app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()

    @pytest.fixture
    def test_agents(self, app, db_path):
        """Create test agents for collaboration testing."""
        agents = []
        for i in range(4):
            agent_name = f"test_agent_{i}"
            api_key = f"test_api_key_{i}_{int(time.time())}"

            # Create agent directly in DB using the same path as the app
            db = sqlite3.connect(str(db_path))
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute(
                """INSERT INTO agents (agent_name, display_name, api_key, bio, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (agent_name, f"Test Agent {i}", api_key, f"Test bio for agent {i}", time.time())
            )
            db.commit()
            agent_id = db.execute(
                "SELECT id FROM agents WHERE agent_name = ?", (agent_name,)
            ).fetchone()["id"]
            db.close()

            agents.append({
                "agent_name": agent_name,
                "agent_id": agent_id,
                "api_key": api_key,
            })

        return agents

    def _make_request(self, client, method, path, data=None, api_key=None):
        """Helper to make API requests with proper headers."""
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key
        if data is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(data) if isinstance(data, dict) else data

        method_map = {
            "GET": client.get,
            "POST": client.post,
            "PATCH": client.patch,
            "DELETE": client.delete,
            "PUT": client.put,
        }

        return method_map[method](path, data=data, headers=headers)

    # =========================================================================
    # Collaboration Creation Tests
    # =========================================================================

    @patch.object(server, 'DB_PATH', new_callable=lambda: None)
    def test_create_collaboration_basic(self, mock_db_path, client, test_agents, db_path):
        """Test creating a basic collaboration."""
        # Set the actual DB path
        mock_db_path.__class__ = type(db_path)
        server.DB_PATH = db_path
        
        owner = test_agents[0]

        response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Duet", "type": "duet"},
            api_key=owner["api_key"]
        )

        assert response.status_code == 201
        data = json.loads(response.data)
        assert data["ok"] is True
        assert data["title"] == "Test Duet"
        assert data["type"] == "duet"
        assert "collaboration_id" in data

    def test_create_collaboration_with_participants(self, client, test_agents):
        """Test creating a collaboration with initial participants."""
        owner = test_agents[0]
        
        response = self._make_request(
            client, "POST", "/api/collaborations",
            data={
                "title": "Group Collaboration",
                "type": "co-upload",
                "participants": [
                    {"agent_name": test_agents[1]["agent_name"]},
                    {"agent_name": test_agents[2]["agent_name"]},
                ]
            },
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data["ok"] is True
        
        # Verify collaboration was created with participants
        collab_id = data["collaboration_id"]
        get_response = self._make_request(
            client, "GET", f"/api/collaborations/{collab_id}",
            api_key=owner["api_key"]
        )
        assert get_response.status_code == 200
        collab_data = json.loads(get_response.data)
        assert collab_data["participant_count"] >= 1  # Owner + pending invites

    def test_create_collaboration_missing_title(self, client, test_agents):
        """Test that creating collaboration without title fails."""
        owner = test_agents[0]
        
        response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"type": "duet"},
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data

    def test_create_collaboration_invalid_type(self, client, test_agents):
        """Test that invalid collaboration type defaults to 'duet'."""
        owner = test_agents[0]
        
        response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test", "type": "invalid_type"},
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data["type"] == "duet"  # Should default

    # =========================================================================
    # Collaboration Retrieval Tests
    # =========================================================================

    def test_get_collaboration(self, client, test_agents):
        """Test retrieving collaboration details."""
        owner = test_agents[0]
        
        # Create collaboration
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab", "description": "A test collaboration"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        # Get collaboration
        response = self._make_request(
            client, "GET", f"/api/collaborations/{collab_id}",
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["collaboration_id"] == collab_id
        assert data["title"] == "Test Collab"
        assert data["description"] == "A test collaboration"
        assert "owner" in data
        assert "participants" in data

    def test_get_collaboration_not_found(self, client, test_agents):
        """Test retrieving non-existent collaboration."""
        owner = test_agents[0]
        
        response = self._make_request(
            client, "GET", "/api/collaborations/nonexistent123",
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 404

    # =========================================================================
    # Collaboration Update Tests
    # =========================================================================

    def test_update_collaboration(self, client, test_agents):
        """Test updating collaboration details."""
        owner = test_agents[0]
        
        # Create collaboration
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Original Title"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        # Update collaboration
        response = self._make_request(
            client, "PATCH", f"/api/collaborations/{collab_id}",
            data={"title": "Updated Title", "description": "New description"},
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ok"] is True
        
        # Verify update
        get_response = self._make_request(
            client, "GET", f"/api/collaborations/{collab_id}",
            api_key=owner["api_key"]
        )
        get_data = json.loads(get_response.data)
        assert get_data["title"] == "Updated Title"
        assert get_data["description"] == "New description"

    def test_update_collaboration_unauthorized(self, client, test_agents):
        """Test that non-owner cannot update collaboration."""
        owner = test_agents[0]
        other = test_agents[1]
        
        # Create collaboration
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        # Try to update as non-owner
        response = self._make_request(
            client, "PATCH", f"/api/collaborations/{collab_id}",
            data={"title": "Hacked Title"},
            api_key=other["api_key"]
        )
        
        assert response.status_code == 404  # Returns 404 for security

    # =========================================================================
    # Collaboration Invitation Tests
    # =========================================================================

    def test_invite_to_collaboration(self, client, test_agents):
        """Test inviting an agent to a collaboration."""
        owner = test_agents[0]
        invitee = test_agents[1]
        
        # Create collaboration
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        # Invite agent
        response = self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/invite",
            data={"agent_name": invitee["agent_name"], "message": "Join us!"},
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ok"] is True
        assert "invite_id" in data

    def test_invite_self_to_collaboration(self, client, test_agents):
        """Test that inviting yourself fails."""
        owner = test_agents[0]
        
        # Create collaboration
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        # Try to invite self
        response = self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/invite",
            data={"agent_name": owner["agent_name"]},
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 400

    def test_respond_to_collab_invite_accept(self, client, test_agents):
        """Test accepting a collaboration invitation."""
        owner = test_agents[0]
        invitee = test_agents[1]
        
        # Create collaboration and invite
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        invite_response = self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/invite",
            data={"agent_name": invitee["agent_name"]},
            api_key=owner["api_key"]
        )
        invite_id = json.loads(invite_response.data)["invite_id"]
        
        # Accept invite
        response = self._make_request(
            client, "POST", f"/api/collaborations/invites/{invite_id}",
            data={"action": "accept"},
            api_key=invitee["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ok"] is True
        assert data["action"] == "accept"
        
        # Verify participant status
        get_response = self._make_request(
            client, "GET", f"/api/collaborations/{collab_id}",
            api_key=owner["api_key"]
        )
        get_data = json.loads(get_response.data)
        participant = next(
            (p for p in get_data["participants"] if p["agent_name"] == invitee["agent_name"]),
            None
        )
        assert participant is not None
        assert participant["status"] == "accepted"

    def test_respond_to_collab_invite_decline(self, client, test_agents):
        """Test declining a collaboration invitation."""
        owner = test_agents[0]
        invitee = test_agents[1]
        
        # Create collaboration and invite
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        invite_response = self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/invite",
            data={"agent_name": invitee["agent_name"]},
            api_key=owner["api_key"]
        )
        invite_id = json.loads(invite_response.data)["invite_id"]
        
        # Decline invite
        response = self._make_request(
            client, "POST", f"/api/collaborations/invites/{invite_id}",
            data={"action": "decline"},
            api_key=invitee["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["action"] == "decline"

    def test_get_my_collab_invites(self, client, test_agents):
        """Test retrieving pending collaboration invites."""
        owner = test_agents[0]
        invitee = test_agents[1]
        
        # Create collaboration and invite
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/invite",
            data={"agent_name": invitee["agent_name"]},
            api_key=owner["api_key"]
        )
        
        # Get invites
        response = self._make_request(
            client, "GET", "/api/collaborations/invites",
            api_key=invitee["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data["invites"]) == 1
        assert data["invites"][0]["collab_title"] == "Test Collab"

    # =========================================================================
    # Collaboration Participant Management Tests
    # =========================================================================

    def test_remove_collab_participant(self, client, test_agents):
        """Test removing a participant from collaboration."""
        owner = test_agents[0]
        participant = test_agents[1]
        
        # Create collaboration with participant
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={
                "title": "Test Collab",
                "participants": [{"agent_name": participant["agent_name"]}]
            },
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        # Accept invite
        invites_response = self._make_request(
            client, "GET", "/api/collaborations/invites",
            api_key=participant["api_key"]
        )
        invites = json.loads(invites_response.data)["invites"]
        if invites:
            self._make_request(
                client, "POST", f"/api/collaborations/invites/{invites[0]['invite_id']}",
                data={"action": "accept"},
                api_key=participant["api_key"]
            )
        
        # Remove participant
        response = self._make_request(
            client, "DELETE",
            f"/api/collaborations/{collab_id}/participants/{participant['agent_name']}",
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ok"] is True

    def test_leave_collaboration(self, client, test_agents):
        """Test leaving a collaboration."""
        owner = test_agents[0]
        participant = test_agents[1]
        
        # Create collaboration with participant
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={
                "title": "Test Collab",
                "participants": [{"agent_name": participant["agent_name"]}]
            },
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        # Accept invite
        invites_response = self._make_request(
            client, "GET", "/api/collaborations/invites",
            api_key=participant["api_key"]
        )
        invites = json.loads(invites_response.data)["invites"]
        if invites:
            self._make_request(
                client, "POST", f"/api/collaborations/invites/{invites[0]['invite_id']}",
                data={"action": "accept"},
                api_key=participant["api_key"]
            )
        
        # Leave collaboration
        response = self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/leave",
            api_key=participant["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ok"] is True

    def test_owner_cannot_leave_collaboration(self, client, test_agents):
        """Test that owner cannot leave their own collaboration."""
        owner = test_agents[0]
        
        # Create collaboration
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        # Try to leave
        response = self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/leave",
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 400

    # =========================================================================
    # Collaboration Video Tests
    # =========================================================================

    def test_add_video_to_collaboration(self, client, test_agents):
        """Test adding a video to a collaboration."""
        owner = test_agents[0]
        
        # Create collaboration
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        # Create a test video
        db = sqlite3.connect(str(server.DB_PATH))
        video_id = f"test_video_{int(time.time())}"
        db.execute(
            """INSERT INTO videos 
               (video_id, agent_id, title, filename, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (video_id, owner["agent_id"], "Test Video", "test.mp4", time.time())
        )
        db.commit()
        db.close()
        
        # Add video to collaboration
        response = self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/videos",
            data={"video_id": video_id},
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ok"] is True

    def test_add_video_not_yours(self, client, test_agents):
        """Test that you cannot add another agent's video."""
        owner = test_agents[0]
        other = test_agents[1]
        
        # Create collaboration
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        # Create video for other agent
        db = sqlite3.connect(str(server.DB_PATH))
        video_id = f"test_video_{int(time.time())}"
        db.execute(
            """INSERT INTO videos 
               (video_id, agent_id, title, filename, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (video_id, other["agent_id"], "Other Video", "test.mp4", time.time())
        )
        db.commit()
        db.close()
        
        # Try to add other's video
        response = self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/videos",
            data={"video_id": video_id},
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 404

    # =========================================================================
    # My Collaborations Tests
    # =========================================================================

    def test_get_my_collaborations(self, client, test_agents):
        """Test retrieving current agent's collaborations."""
        owner = test_agents[0]
        
        # Create collaboration
        self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "My Collab"},
            api_key=owner["api_key"]
        )
        
        # Get my collaborations
        response = self._make_request(
            client, "GET", "/api/collaborations/me",
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data["collaborations"]) >= 1
        titles = [c["title"] for c in data["collaborations"]]
        assert "My Collab" in titles

    # =========================================================================
    # Collaboration Notifications Tests
    # =========================================================================

    def test_get_collab_notifications(self, client, test_agents):
        """Test retrieving collaboration notifications."""
        owner = test_agents[0]
        invitee = test_agents[1]
        
        # Create collaboration and invite (triggers notification)
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/invite",
            data={"agent_name": invitee["agent_name"]},
            api_key=owner["api_key"]
        )
        
        # Get notifications
        response = self._make_request(
            client, "GET", "/api/collaborations/notifications",
            api_key=invitee["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data["notifications"]) >= 1

    def test_mark_collab_notifications_read(self, client, test_agents):
        """Test marking collaboration notifications as read."""
        owner = test_agents[0]
        invitee = test_agents[1]
        
        # Create collaboration and invite
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/invite",
            data={"agent_name": invitee["agent_name"]},
            api_key=owner["api_key"]
        )
        
        # Mark as read
        response = self._make_request(
            client, "POST", "/api/collaborations/notifications/mark-read",
            api_key=invitee["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ok"] is True

    # =========================================================================
    # Collaborative Playlists Tests
    # =========================================================================

    def test_add_playlist_collaborator(self, client, test_agents):
        """Test adding a collaborator to a playlist."""
        owner = test_agents[0]
        collaborator = test_agents[1]
        
        # Create playlist
        create_response = self._make_request(
            client, "POST", "/api/playlists",
            data={"title": "Test Playlist"},
            api_key=owner["api_key"]
        )
        playlist_id = json.loads(create_response.data)["playlist_id"]
        
        # Add collaborator
        response = self._make_request(
            client, "POST", f"/api/playlists/{playlist_id}/collaborators",
            data={"agent_name": collaborator["agent_name"], "role": "editor"},
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ok"] is True

    def test_get_playlist_collaborators(self, client, test_agents):
        """Test retrieving playlist collaborators."""
        owner = test_agents[0]
        collaborator = test_agents[1]
        
        # Create playlist and add collaborator
        create_response = self._make_request(
            client, "POST", "/api/playlists",
            data={"title": "Test Playlist"},
            api_key=owner["api_key"]
        )
        playlist_id = json.loads(create_response.data)["playlist_id"]
        
        self._make_request(
            client, "POST", f"/api/playlists/{playlist_id}/collaborators",
            data={"agent_name": collaborator["agent_name"]},
            api_key=owner["api_key"]
        )
        
        # Get collaborators
        response = self._make_request(
            client, "GET", f"/api/playlists/{playlist_id}/collaborators",
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data["collaborators"]) == 1
        assert data["collaborators"][0]["agent_name"] == collaborator["agent_name"]

    def test_remove_playlist_collaborator(self, client, test_agents):
        """Test removing a collaborator from a playlist."""
        owner = test_agents[0]
        collaborator = test_agents[1]
        
        # Create playlist and add collaborator
        create_response = self._make_request(
            client, "POST", "/api/playlists",
            data={"title": "Test Playlist"},
            api_key=owner["api_key"]
        )
        playlist_id = json.loads(create_response.data)["playlist_id"]
        
        self._make_request(
            client, "POST", f"/api/playlists/{playlist_id}/collaborators",
            data={"agent_name": collaborator["agent_name"]},
            api_key=owner["api_key"]
        )
        
        # Remove collaborator
        response = self._make_request(
            client, "DELETE",
            f"/api/playlists/{playlist_id}/collaborators/{collaborator['agent_name']}",
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ok"] is True

    def test_get_my_collaborative_playlists(self, client, test_agents):
        """Test retrieving playlists I can collaborate on."""
        owner = test_agents[0]
        collaborator = test_agents[1]
        
        # Create playlist and add collaborator
        create_response = self._make_request(
            client, "POST", "/api/playlists",
            data={"title": "Shared Playlist"},
            api_key=owner["api_key"]
        )
        playlist_id = json.loads(create_response.data)["playlist_id"]
        
        self._make_request(
            client, "POST", f"/api/playlists/{playlist_id}/collaborators",
            data={"agent_name": collaborator["agent_name"]},
            api_key=owner["api_key"]
        )
        
        # Get collaborative playlists
        response = self._make_request(
            client, "GET", "/api/playlists/collaborative/me",
            api_key=collaborator["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data["playlists"]) == 1
        assert data["playlists"][0]["title"] == "Shared Playlist"

    def test_add_collaborator_unauthorized(self, client, test_agents):
        """Test that non-owner cannot add collaborators."""
        owner = test_agents[0]
        other = test_agents[1]
        target = test_agents[2]
        
        # Create playlist
        create_response = self._make_request(
            client, "POST", "/api/playlists",
            data={"title": "Test Playlist"},
            api_key=owner["api_key"]
        )
        playlist_id = json.loads(create_response.data)["playlist_id"]
        
        # Try to add collaborator as non-owner
        response = self._make_request(
            client, "POST", f"/api/playlists/{playlist_id}/collaborators",
            data={"agent_name": target["agent_name"]},
            api_key=other["api_key"]
        )
        
        assert response.status_code == 404

    # =========================================================================
    # Collaboration Deletion Tests
    # =========================================================================

    def test_delete_collaboration(self, client, test_agents):
        """Test deleting a collaboration."""
        owner = test_agents[0]
        
        # Create collaboration
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        # Delete collaboration
        response = self._make_request(
            client, "DELETE", f"/api/collaborations/{collab_id}",
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ok"] is True
        
        # Verify deletion
        get_response = self._make_request(
            client, "GET", f"/api/collaborations/{collab_id}",
            api_key=owner["api_key"]
        )
        assert get_response.status_code == 404

    # =========================================================================
    # Edge Cases and Error Handling
    # =========================================================================

    def test_duplicate_invite_prevented(self, client, test_agents):
        """Test that duplicate invites are prevented."""
        owner = test_agents[0]
        invitee = test_agents[1]
        
        # Create collaboration
        create_response = self._make_request(
            client, "POST", "/api/collaborations",
            data={"title": "Test Collab"},
            api_key=owner["api_key"]
        )
        collab_id = json.loads(create_response.data)["collaboration_id"]
        
        # First invite
        self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/invite",
            data={"agent_name": invitee["agent_name"]},
            api_key=owner["api_key"]
        )
        
        # Second invite should fail
        response = self._make_request(
            client, "POST", f"/api/collaborations/{collab_id}/invite",
            data={"agent_name": invitee["agent_name"]},
            api_key=owner["api_key"]
        )
        
        assert response.status_code == 409

    def test_collaboration_rate_limits(self, client, test_agents):
        """Test that collaboration features have appropriate rate limiting."""
        # This is a placeholder for rate limit tests
        # In production, these would test actual rate limit headers/responses
        owner = test_agents[0]
        
        # Create multiple collaborations rapidly
        for i in range(3):
            response = self._make_request(
                client, "POST", "/api/collaborations",
                data={"title": f"Collab {i}"},
                api_key=owner["api_key"]
            )
            # Should succeed for reasonable number
            assert response.status_code == 201


class TestCollaborationBackwardCompatibility:
    """Test that collaboration features don't break existing functionality."""

    @pytest.fixture
    def db_path(self, tmp_path):
        """Create a temporary database for testing."""
        db_file = tmp_path / "test_bottube.db"
        original_db_path = server.DB_PATH
        server.DB_PATH = db_file
        yield db_file
        server.DB_PATH = original_db_path

    @pytest.fixture
    def app(self, db_path):
        """Create test Flask app."""
        app = server.app
        app.config["TESTING"] = True
        
        conn = sqlite3.connect(str(db_path))
        conn.executescript(server.SCHEMA)
        server.init_db()
        conn.commit()
        conn.close()
        
        yield app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()

    def test_existing_playlist_api_still_works(self, client):
        """Test that existing playlist API is not affected."""
        # Create agent
        db = sqlite3.connect(str(server.DB_PATH))
        db.execute(
            """INSERT INTO agents (agent_name, api_key, created_at)
               VALUES (?, ?, ?)""",
            ("test_agent", "test_key", time.time())
        )
        db.commit()
        db.close()
        
        # Create playlist using existing API
        response = client.post(
            "/api/playlists",
            data=json.dumps({"title": "Test Playlist"}),
            headers={"X-API-Key": "test_key", "Content-Type": "application/json"}
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data["ok"] is True
        assert "playlist_id" in data

    def test_existing_video_api_still_works(self, client):
        """Test that existing video API is not affected."""
        # This is a placeholder - full video upload tests would go here
        # The collaboration schema additions should not affect video operations
        pass
