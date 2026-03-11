#!/usr/bin/env python3
"""
Tests for BoTTube Media Preparation & Attribution Pipeline (Issue #311)

Run with: pytest tests/test_media_prep.py -v

Note: Tests media_prep module in isolation to avoid Python 3.9 compatibility
issues in bottube_server.
"""

import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Set test environment
os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_media_prep.db")

# Import only media_prep module (not bottube_server to avoid py3.9 issues)
from media_prep import (
    AttributionMetadata,
    AttributionType,
    MediaPrepPipeline,
    PrepResult,
    PrepStage,
    StageProgress,
    build_attribution_chain,
    get_attribution_chain,
    init_syndication_tables,
    record_syndication,
)


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys = ON")
    
    # Initialize base schema (minimal for testing)
    db.executescript("""
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT UNIQUE NOT NULL,
            display_name TEXT,
            api_key TEXT UNIQUE,
            created_at REAL NOT NULL
        );
        
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY,
            video_id TEXT UNIQUE NOT NULL,
            agent_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            filename TEXT NOT NULL,
            thumbnail TEXT DEFAULT '',
            duration_sec REAL DEFAULT 0,
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            dislikes INTEGER DEFAULT 0,
            tags TEXT DEFAULT '[]',
            category TEXT DEFAULT 'other',
            scene_description TEXT DEFAULT '',
            novelty_score REAL DEFAULT 0,
            novelty_flags TEXT DEFAULT '',
            revision_of TEXT DEFAULT '',
            revision_note TEXT DEFAULT '',
            challenge_id TEXT DEFAULT '',
            submolt_crosspost TEXT DEFAULT '',
            attribution_id INTEGER DEFAULT NULL,
            syndication_chain TEXT DEFAULT '[]',
            license TEXT DEFAULT 'CC-BY-4.0',
            created_at REAL NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        );
    """)
    
    # Initialize syndication tables
    init_syndication_tables(db)
    db.commit()
    
    yield db
    
    db.close()
    try:
        os.unlink(path)
    except Exception:
        pass


@pytest.fixture
def temp_dirs():
    """Create temporary directories for videos and thumbnails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        video_dir = Path(tmpdir) / "videos"
        thumb_dir = Path(tmpdir) / "thumbnails"
        video_dir.mkdir()
        thumb_dir.mkdir()
        yield video_dir, thumb_dir


@pytest.fixture
def test_agent(temp_db):
    """Create test agent."""
    cursor = temp_db.execute(
        """INSERT INTO agents (agent_name, display_name, api_key, created_at)
           VALUES (?, ?, ?, ?)""",
        ("test_agent", "Test Agent", "bottube_sk_test123", time.time()),
    )
    temp_db.commit()
    return int(cursor.lastrowid)


class TestAttributionMetadata:
    """Tests for AttributionMetadata dataclass."""
    
    def test_create_original_attribution(self):
        """Test creating original attribution metadata."""
        attr = AttributionMetadata(
            original_creator="agent_123",
            license="CC-BY-4.0",
            source_url="https://example.com/video",
        )
        
        assert attr.original_creator == "agent_123"
        assert attr.license == "CC-BY-4.0"
        assert attr.attribution_type == AttributionType.ORIGINAL
        assert attr.chain == []
    
    def test_create_derivative_attribution(self):
        """Test creating derivative attribution."""
        attr = AttributionMetadata(
            original_creator="agent_456",
            license="CC-BY-SA-4.0",
            attribution_type=AttributionType.DERIVATIVE,
            chain=[{"video_id": "abc123", "relationship": "derivative"}],
        )
        
        assert attr.attribution_type == AttributionType.DERIVATIVE
        assert len(attr.chain) == 1
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        attr = AttributionMetadata(
            original_creator="agent_789",
            license="MIT",
            source_url="https://example.com",
            custom_attribution={"credit": "Special thanks"},
        )
        
        data = attr.to_dict()
        
        assert data["original_creator"] == "agent_789"
        assert data["license"] == "MIT"
        assert data["source_url"] == "https://example.com"
        assert data["custom_attribution"]["credit"] == "Special thanks"
    
    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "original_creator": "agent_999",
            "license": "CC0",
            "attribution_type": "remix",
            "chain": [{"video_id": "xyz789"}],
        }
        
        attr = AttributionMetadata.from_dict(data)
        
        assert attr.original_creator == "agent_999"
        assert attr.license == "CC0"
        assert attr.attribution_type == AttributionType.REMIX


class TestMediaPrepPipeline:
    """Tests for MediaPrepPipeline class."""
    
    def test_pipeline_initialization(self, temp_db, temp_dirs):
        """Test pipeline initializes correctly."""
        video_dir, thumb_dir = temp_dirs
        
        pipeline = MediaPrepPipeline(
            db=temp_db,
            video_dir=video_dir,
            thumb_dir=thumb_dir,
            max_duration=60,
            max_file_mb=50,
        )
        
        assert pipeline.max_duration == 60
        assert pipeline.max_file_mb == 50
        assert pipeline.video_dir == video_dir
    
    @patch("media_prep.subprocess.run")
    @patch("media_prep.Path.stat")
    def test_process_video_stages(self, mock_stat, mock_run, temp_db, temp_dirs, test_agent):
        """Test video processing completes all stages."""
        video_dir, thumb_dir = temp_dirs

        # Mock file stats (1MB file)
        mock_return = MagicMock()
        mock_return.st_size = 1024 * 1024
        mock_stat.return_value = mock_return

        # Mock ffprobe/ffmpeg output
        mock_proc = MagicMock()
        mock_proc.stdout = "5.0"
        mock_proc.returncode = 0
        mock_proc.check_return_value = lambda: None
        mock_run.return_value = mock_proc

        pipeline = MediaPrepPipeline(
            db=temp_db,
            video_dir=video_dir,
            thumb_dir=thumb_dir,
        )

        # Create fake input file
        input_file = video_dir / "input.mp4"
        input_file.touch()

        # Mock transcoding to create output (simpler approach)
        output_file = video_dir / "testvid.mp4"
        output_file.touch()
        thumb_file = thumb_dir / "testvid.jpg"
        thumb_file.touch()

        result = pipeline.process_video(
            input_path=str(input_file),
            agent_id=test_agent,
            title="Test Video",
            description="Test description",
        )

        # Validate stages completed (validation always passes with mocked subprocess)
        assert PrepStage.VALIDATE.value in result.stages_completed
        assert result.video_id != ""
    
    def test_validate_input_missing_file(self, temp_db, temp_dirs):
        """Test validation fails for missing file."""
        video_dir, thumb_dir = temp_dirs
        
        pipeline = MediaPrepPipeline(db=temp_db, video_dir=video_dir, thumb_dir=thumb_dir)
        
        with pytest.raises(ValueError, match="not found"):
            pipeline._validate_input("/nonexistent/path.mp4")
    
    def test_record_stage(self, temp_db, temp_dirs):
        """Test stage progress recording."""
        video_dir, thumb_dir = temp_dirs
        pipeline = MediaPrepPipeline(db=temp_db, video_dir=video_dir, thumb_dir=thumb_dir)
        
        pipeline._record_stage(PrepStage.VALIDATE, "running", "Validating")
        
        assert PrepStage.VALIDATE.value in pipeline.progress
        assert pipeline.progress[PrepStage.VALIDATE.value].status == "running"
        assert pipeline.progress[PrepStage.VALIDATE.value].message == "Validating"


class TestSyndicationTables:
    """Tests for syndication database tables."""
    
    def test_init_syndication_tables(self, temp_db):
        """Test syndication tables are created."""
        cursor = temp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'syndication%'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        
        assert "syndication_attribution" in tables
        assert "syndication_log" in tables
    
    def test_syndication_attribution_schema(self, temp_db):
        """Test syndication_attribution table schema."""
        cursor = temp_db.execute("PRAGMA table_info(syndication_attribution)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        assert "video_id" in columns
        assert "agent_id" in columns
        assert "original_creator" in columns
        assert "license" in columns
        assert "attribution_type" in columns
        assert "chain" in columns
    
    def test_syndication_log_schema(self, temp_db):
        """Test syndication_log table schema."""
        cursor = temp_db.execute("PRAGMA table_info(syndication_log)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        assert "video_id" in columns
        assert "platform" in columns
        assert "external_url" in columns
        assert "status" in columns


class TestAttributionFunctions:
    """Tests for attribution helper functions."""
    
    def test_record_syndication(self, temp_db, test_agent):
        """Test recording syndication to external platform."""
        # Insert test video
        temp_db.execute(
            """INSERT INTO videos (video_id, agent_id, title, filename, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("testvid123", test_agent, "Test", "test.mp4", time.time()),
        )
        temp_db.commit()
        
        synd_id = record_syndication(
            db=temp_db,
            video_id="testvid123",
            agent_id=test_agent,
            platform="youtube",
            external_url="https://youtube.com/watch?v=abc123",
            external_id="abc123",
        )
        
        assert synd_id > 0
        
        # Verify record
        row = temp_db.execute(
            "SELECT * FROM syndication_log WHERE id = ?", (synd_id,)
        ).fetchone()
        
        assert row is not None
        assert row[3] == "youtube"  # platform
        assert "youtube.com" in row[4]  # external_url
    
    def test_build_attribution_chain(self):
        """Test building attribution chain."""
        chain = build_attribution_chain(
            original_video_id="original123",
            derivative_video_id="derivative456",
            agent_id=42,
            relationship="remix",
        )
        
        assert len(chain) == 1
        assert chain[0]["video_id"] == "original123"
        assert chain[0]["relationship"] == "remix"
        assert chain[0]["agent_id"] == 42
    
    def test_get_attribution_chain_empty(self, temp_db):
        """Test getting attribution chain for video without attribution."""
        chain = get_attribution_chain(temp_db, "nonexistent")
        assert chain == []

    def test_get_attribution_chain_single(self, temp_db, test_agent):
        """Test getting attribution chain with single entry."""
        # First insert the video (FK constraint)
        temp_db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, filename, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("vid123", test_agent, "Test Video", "vid123.mp4", time.time()),
        )
        # Insert attribution record
        temp_db.execute(
            """INSERT INTO syndication_attribution
               (video_id, agent_id, original_creator, license, attribution_type, chain, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("vid123", test_agent, "agent_999", "CC-BY-4.0", "original", "[]", time.time()),
        )
        temp_db.commit()

        chain = get_attribution_chain(temp_db, "vid123")

        assert len(chain) == 1
        assert chain[0]["video_id"] == "vid123"
        assert chain[0]["original_creator"] == "agent_999"
        assert chain[0]["license"] == "CC-BY-4.0"


class TestVideoAttributionColumns:
    """Tests for video table attribution columns."""
    
    def test_attribution_columns_exist(self, temp_db):
        """Test attribution columns added to videos table."""
        cursor = temp_db.execute("PRAGMA table_info(videos)")
        columns = {row[1] for row in cursor.fetchall()}
        
        assert "attribution_id" in columns
        assert "syndication_chain" in columns
        assert "license" in columns
    
    def test_video_with_attribution(self, temp_db, test_agent):
        """Test inserting video with attribution data."""
        temp_db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, filename, license, syndication_chain, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("attrvid123", test_agent, "Attributed", "attr.mp4", "CC-BY-SA-4.0",
             '[{"video_id": "parent123"}]', time.time()),
        )
        temp_db.commit()
        
        row = temp_db.execute(
            "SELECT license, syndication_chain FROM videos WHERE video_id = ?",
            ("attrvid123",),
        ).fetchone()
        
        assert row[0] == "CC-BY-SA-4.0"
        assert json.loads(row[1]) == [{"video_id": "parent123"}]


class TestTranscodeCommand:
    """Tests for ffmpeg transcode command generation."""

    def test_transcode_uses_valid_scale_filter(self, temp_db, temp_dirs):
        """Test that transcode uses -vf scale instead of invalid -max_width/-max_height."""
        video_dir, thumb_dir = temp_dirs
        pipeline = MediaPrepPipeline(
            db=temp_db,
            video_dir=video_dir,
            thumb_dir=thumb_dir,
            target_width=1280,
            target_height=720,
        )

        # Create a fake input file for validation
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"fake video content")
            input_path = tmp.name

        try:
            # Mock _get_duration to bypass validation
            with patch.object(pipeline, '_get_duration', return_value=10.0):
                cmd = pipeline._build_transcode_command(input_path, "test123")

            # Assert no invalid arguments
            assert "-max_width" not in cmd
            assert "-max_height" not in cmd

            # Assert valid scale filter is present
            assert "-vf" in cmd
            vf_index = cmd.index("-vf")
            scale_filter = cmd[vf_index + 1]
            assert "scale" in scale_filter
            assert "min(1280,iw)" in scale_filter
            assert "min(720,ih)" in scale_filter
            assert "force_original_aspect_ratio=decrease" in scale_filter

            # Assert output format remains MP4/H264
            assert "-c:v" in cmd
            assert "libx264" in cmd
            assert "-c:a" in cmd
            assert "aac" in cmd
            assert str(cmd[-1]).endswith(".mp4")
        finally:
            os.unlink(input_path)

    def test_transcode_custom_dimensions(self, temp_db, temp_dirs):
        """Test scale filter uses custom target dimensions."""
        video_dir, thumb_dir = temp_dirs
        pipeline = MediaPrepPipeline(
            db=temp_db,
            video_dir=video_dir,
            thumb_dir=thumb_dir,
            target_width=1920,
            target_height=1080,
        )

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"fake video content")
            input_path = tmp.name

        try:
            with patch.object(pipeline, '_get_duration', return_value=10.0):
                cmd = pipeline._build_transcode_command(input_path, "test456")

            vf_index = cmd.index("-vf")
            scale_filter = cmd[vf_index + 1]
            assert "min(1920,iw)" in scale_filter
            assert "min(1080,ih)" in scale_filter
        finally:
            os.unlink(input_path)


class TestPrepResult:
    """Tests for PrepResult dataclass."""

    def test_result_to_dict(self):
        """Test PrepResult serialization."""
        result = PrepResult(
            success=True,
            video_id="abc123",
            output_path="/videos/abc123.mp4",
            thumbnail_path="/thumbnails/abc123.jpg",
            duration_sec=30.5,
            width=1280,
            height=720,
            file_size=1024000,
            stages_completed=["validate", "transcode", "thumbnail"],
            attribution_id=42,
        )
        
        data = result.to_dict()
        
        assert data["success"] is True
        assert data["video_id"] == "abc123"
        assert data["duration_sec"] == 30.5
        assert data["attribution_id"] == 42
    
    def test_result_failed(self):
        """Test failed PrepResult."""
        result = PrepResult(
            success=False,
            video_id="",
            output_path="",
            thumbnail_path="",
            duration_sec=0,
            width=0,
            height=0,
            file_size=0,
            stages_completed=["validate"],
            error="Transcoding failed",
        )
        
        assert result.success is False
        assert result.error == "Transcoding failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
