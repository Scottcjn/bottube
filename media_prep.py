#!/usr/bin/env python3
"""
BoTTube Media Preparation & Attribution Pipeline

Handles media processing stages for syndication:
  - Transcoding to web-optimized formats
  - Thumbnail generation
  - Caption extraction/generation
  - Attribution metadata embedding and tracking

Attribution chain tracking for syndicated content:
  - Original creator identification
  - Syndication path recording
  - License and usage rights metadata
  - Cross-platform attribution links

Usage:
    from media_prep import MediaPrepPipeline, AttributionMetadata
    
    pipeline = MediaPrepPipeline(db, video_dir, thumb_dir)
    result = pipeline.process_video(
        input_path="/path/to/input.mp4",
        agent_id=1,
        title="My Video",
        attribution=AttributionMetadata(
            original_creator="agent_123",
            license="CC-BY-4.0",
            source_url="https://example.com/original"
        )
    )

Elyan Labs — https://bottube.ai
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sqlite3

log = logging.getLogger("media_prep")


# ---------------------------------------------------------------------------
# Enums & Constants
# ---------------------------------------------------------------------------

class PrepStage(Enum):
    """Media preparation pipeline stages."""
    VALIDATE = "validate"
    TRANSCODE = "transcode"
    THUMBNAIL = "thumbnail"
    CAPTIONS = "captions"
    METADATA = "metadata"
    ATTRIBUTION = "attribution"
    COMPLETE = "complete"
    FAILED = "failed"


class AttributionType(Enum):
    """Type of attribution in syndication chain."""
    ORIGINAL = "original"
    DERIVATIVE = "derivative"
    REMIX = "remix"
    COMPILATION = "compilation"
    SYNDICATED = "syndicated"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class AttributionMetadata:
    """Attribution metadata for syndicated content."""
    original_creator: str  # agent_id or external identifier
    license: str = "CC-BY-4.0"
    source_url: str = ""
    attribution_type: AttributionType = AttributionType.ORIGINAL
    chain: List[Dict[str, Any]] = field(default_factory=list)
    custom_attribution: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            "original_creator": self.original_creator,
            "license": self.license,
            "source_url": self.source_url,
            "attribution_type": self.attribution_type.value,
            "chain": self.chain,
            "custom_attribution": self.custom_attribution,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AttributionMetadata":
        """Create from dictionary."""
        return cls(
            original_creator=data.get("original_creator", ""),
            license=data.get("license", "CC-BY-4.0"),
            source_url=data.get("source_url", ""),
            attribution_type=AttributionType(data.get("attribution_type", "original")),
            chain=data.get("chain", []),
            custom_attribution=data.get("custom_attribution", {}),
        )


@dataclass
class PrepResult:
    """Result of media preparation pipeline."""
    success: bool
    video_id: str
    output_path: str
    thumbnail_path: str
    duration_sec: float
    width: int
    height: int
    file_size: int
    stages_completed: List[str]
    error: Optional[str] = None
    attribution_id: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "video_id": self.video_id,
            "output_path": self.output_path,
            "thumbnail_path": self.thumbnail_path,
            "duration_sec": self.duration_sec,
            "width": self.width,
            "height": self.height,
            "file_size": self.file_size,
            "stages_completed": self.stages_completed,
            "error": self.error,
            "attribution_id": self.attribution_id,
        }


@dataclass
class StageProgress:
    """Progress tracking for a pipeline stage."""
    stage: PrepStage
    status: str  # pending, running, complete, failed
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Media Preparation Pipeline
# ---------------------------------------------------------------------------

class MediaPrepPipeline:
    """
    Media preparation pipeline for BoTTube syndication.
    
    Processes uploaded videos through stages:
      1. Validation - Check format, size, duration
      2. Transcoding - Convert to web-optimized H.264/AAC
      3. Thumbnail - Generate preview images
      4. Captions - Extract or generate subtitles
      5. Metadata - Embed and store metadata
      6. Attribution - Record syndication chain
    """
    
    def __init__(
        self,
        db: sqlite3.Connection,
        video_dir: Path,
        thumb_dir: Path,
        max_duration: int = 300,
        max_file_mb: int = 500,
        target_width: int = 1280,
        target_height: int = 720,
    ):
        self.db = db
        self.video_dir = video_dir
        self.thumb_dir = thumb_dir
        self.max_duration = max_duration
        self.max_file_mb = max_file_mb
        self.target_width = target_width
        self.target_height = target_height
        self.progress: Dict[str, StageProgress] = {}
    
    def process_video(
        self,
        input_path: str,
        agent_id: int,
        title: str,
        description: str = "",
        category: str = "other",
        tags: List[str] = None,
        attribution: Optional[AttributionMetadata] = None,
        scene_description: str = "",
    ) -> PrepResult:
        """
        Run full media preparation pipeline.
        
        Args:
            input_path: Path to source video file
            agent_id: ID of uploading agent
            title: Video title
            description: Video description
            category: Video category
            tags: List of tags
            attribution: Attribution metadata for syndication
            scene_description: Text description for accessibility
        
        Returns:
            PrepResult with output paths and metadata
        """
        import string
        import random

        start_time = time.time()
        tags = tags or []

        # Generate video ID (YouTube-style 11 char ID)
        chars = string.ascii_letters + string.digits + "-_"
        video_id = "".join(random.choice(chars) for _ in range(11))
        
        # Initialize progress tracking
        self.progress = {}
        
        try:
            # Stage 1: Validate
            self._record_stage(PrepStage.VALIDATE, "running", "Validating input file")
            self._validate_input(input_path)
            self._record_stage(PrepStage.VALIDATE, "complete", "Validation passed")
            
            # Stage 2: Transcode
            self._record_stage(PrepStage.TRANSCODE, "running", "Transcoding video")
            output_path = self._transcode(input_path, video_id)
            duration, width, height = self._get_video_info(output_path)
            self._record_stage(PrepStage.TRANSCODE, "complete", "Transcoding complete", {
                "duration": duration,
                "width": width,
                "height": height,
            })
            
            # Stage 3: Thumbnail
            self._record_stage(PrepStage.THUMBNAIL, "running", "Generating thumbnail")
            thumbnail_path = self._generate_thumbnail(output_path, video_id)
            self._record_stage(PrepStage.THUMBNAIL, "complete", "Thumbnail generated")
            
            # Stage 4: Captions (best effort)
            self._record_stage(PrepStage.CAPTIONS, "running", "Processing captions")
            caption_result = self._process_captions(output_path, video_id)
            self._record_stage(PrepStage.CAPTIONS, "complete", "Captions processed", caption_result)
            
            # Stage 5: Metadata embedding
            self._record_stage(PrepStage.METADATA, "running", "Embedding metadata")
            self._embed_metadata(output_path, title, description, agent_id)
            self._record_stage(PrepStage.METADATA, "complete", "Metadata embedded")
            
            # Stage 6: Attribution tracking
            attribution_id = None
            if attribution:
                self._record_stage(PrepStage.ATTRIBUTION, "running", "Recording attribution")
                attribution_id = self._record_attribution(
                    video_id, agent_id, attribution
                )
                self._record_stage(PrepStage.ATTRIBUTION, "complete", "Attribution recorded", {
                    "attribution_id": attribution_id,
                })
            
            # Mark complete
            self._record_stage(PrepStage.COMPLETE, "complete", "Pipeline complete")
            
            # Get file size
            file_size = os.path.getsize(output_path)
            
            return PrepResult(
                success=True,
                video_id=video_id,
                output_path=str(output_path),
                thumbnail_path=str(thumbnail_path),
                duration_sec=duration,
                width=width,
                height=height,
                file_size=file_size,
                stages_completed=[s.value for s in PrepStage],
                attribution_id=attribution_id,
            )
            
        except Exception as e:
            log.exception(f"Pipeline failed: {e}")
            self._record_stage(PrepStage.FAILED, "failed", str(e))
            return PrepResult(
                success=False,
                video_id=video_id if 'video_id' in locals() else "",
                output_path="",
                thumbnail_path="",
                duration_sec=0,
                width=0,
                height=0,
                file_size=0,
                stages_completed=[p.stage.value for p in self.progress.values() if p.status == "complete"],
                error=str(e),
            )
    
    def _record_stage(
        self,
        stage: PrepStage,
        status: str,
        message: str = "",
        details: Dict[str, Any] = None,
    ) -> None:
        """Record progress for a pipeline stage."""
        now = time.time()
        self.progress[stage.value] = StageProgress(
            stage=stage,
            status=status,
            started_at=now if status == "running" else None,
            completed_at=now if status in ("complete", "failed") else None,
            message=message,
            details=details or {},
        )
        log.info(f"[{stage.value}] {status}: {message}")
    
    def _validate_input(self, input_path: str) -> None:
        """Validate input video file."""
        path = Path(input_path)
        
        if not path.exists():
            raise ValueError(f"Input file not found: {input_path}")
        
        # Check file size
        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > self.max_file_mb:
            raise ValueError(f"File too large: {file_size_mb:.1f}MB > {self.max_file_mb}MB")
        
        # Check duration
        duration = self._get_duration(input_path)
        if duration > self.max_duration:
            raise ValueError(f"Duration too long: {duration}s > {self.max_duration}s")
        
        # Check format
        valid_formats = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
        if path.suffix.lower() not in valid_formats:
            raise ValueError(f"Unsupported format: {path.suffix}")
    
    def _get_duration(self, video_path: str) -> float:
        """Get video duration in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
            return 0.0
    
    def _transcode(self, input_path: str, video_id: str) -> Path:
        """Transcode video to web-optimized format."""
        output_path = self.video_dir / f"{video_id}.mp4"

        # FFmpeg transcoding command with valid scale filter
        # Uses aspect-ratio-safe scaling: scales down if larger than target,
        # preserves aspect ratio, never upscales
        scale_filter = f"scale='min({self.target_width},iw)':'min({self.target_height},ih)':force_original_aspect_ratio=decrease"
        cmd = self._build_transcode_command(input_path, video_id)

        try:
            subprocess.run(cmd, capture_output=True, timeout=600, check=True)
        except subprocess.CalledProcessError as e:
            log.error(f"FFmpeg failed: {e.stderr.decode() if e.stderr else e}")
            raise RuntimeError(f"Transcoding failed: {e}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Transcoding timed out")

        return output_path

    def _build_transcode_command(self, input_path: str, video_id: str) -> List[str]:
        """Build ffmpeg transcode command (exposed for testing)."""
        output_path = self.video_dir / f"{video_id}.mp4"

        scale_filter = f"scale='min({self.target_width},iw)':'min({self.target_height},ih)':force_original_aspect_ratio=decrease"
        return [
            "ffmpeg",
            "-i", input_path,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-vf", scale_filter,
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-y",
            str(output_path),
        ]
    
    def _get_video_info(self, video_path: str) -> Tuple[float, int, int]:
        """Get video duration, width, height."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=duration,width,height",
            "-of", "json",
            video_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
            data = json.loads(result.stdout)
            streams = data.get("streams", [{}])
            stream = streams[0] if streams else {}
            duration = float(stream.get("duration", 0))
            width = int(stream.get("width", 0))
            height = int(stream.get("height", 0))
            return duration, width, height
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError, FileNotFoundError):
            return 0.0, 0, 0
    
    def _generate_thumbnail(self, video_path: str, video_id: str) -> Path:
        """Generate thumbnail from video frame."""
        thumb_path = self.thumb_dir / f"{video_id}.jpg"
        
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-ss", "00:00:01",
            "-vframes", "1",
            "-vf", "scale=640:-1",
            "-q:v", "2",
            "-y",
            str(thumb_path),
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, timeout=60, check=True)
        except subprocess.CalledProcessError as e:
            log.warning(f"Thumbnail generation failed: {e}")
            # Create placeholder
            thumb_path.write_bytes(b"")
        
        return thumb_path
    
    def _process_captions(self, video_path: str, video_id: str) -> Dict[str, Any]:
        """Process captions (extract or placeholder)."""
        # This integrates with captions_blueprint if available
        result = {"status": "pending", "formats": []}
        
        # Try to extract existing subtitles
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "s",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            video_path,
        ]
        try:
            result_proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            subtitle_streams = result_proc.stdout.strip().split("\n") if result_proc.stdout.strip() else []
            if subtitle_streams:
                result["status"] = "extracted"
                result["subtitle_streams"] = subtitle_streams
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass
        
        return result
    
    def _embed_metadata(
        self,
        video_path: str,
        title: str,
        description: str,
        agent_id: int,
    ) -> None:
        """Embed metadata into video file."""
        temp_path = Path(video_path).with_suffix(".tmp.mp4")
        
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-metadata", f"title={title}",
            "-metadata", f"description={description}",
            "-metadata", f"artist=agent_{agent_id}",
            "-metadata", f"encoded_by=BoTTube",
            "-c", "copy",
            "-y",
            str(temp_path),
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
            temp_path.replace(video_path)
        except subprocess.CalledProcessError as e:
            log.warning(f"Metadata embedding failed: {e}")
            if temp_path.exists():
                temp_path.unlink()
    
    def _record_attribution(
        self,
        video_id: str,
        agent_id: int,
        attribution: AttributionMetadata,
    ) -> int:
        """Record attribution in database."""
        cursor = self.db.execute(
            """
            INSERT INTO syndication_attribution
                (video_id, agent_id, original_creator, license, source_url,
                 attribution_type, chain, custom_attribution, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                agent_id,
                attribution.original_creator,
                attribution.license,
                attribution.source_url,
                attribution.attribution_type.value,
                json.dumps(attribution.chain),
                json.dumps(attribution.custom_attribution),
                time.time(),
            ),
        )
        self.db.commit()
        return int(cursor.lastrowid)
    
    def get_progress(self, video_id: str) -> Dict[str, Any]:
        """Get pipeline progress for a video."""
        return {
            "video_id": video_id,
            "stages": {
                k: {
                    "stage": v.stage.value,
                    "status": v.status,
                    "message": v.message,
                    "details": v.details,
                    "started_at": v.started_at,
                    "completed_at": v.completed_at,
                }
                for k, v in self.progress.items()
            },
        }


# ---------------------------------------------------------------------------
# Attribution Helpers
# ---------------------------------------------------------------------------

def build_attribution_chain(
    original_video_id: str,
    derivative_video_id: str,
    agent_id: int,
    relationship: str = "derivative",
) -> List[Dict[str, Any]]:
    """
    Build attribution chain linking original and derivative works.
    
    Args:
        original_video_id: ID of original video
        derivative_video_id: ID of derivative/remix video
        agent_id: ID of agent creating derivative
        relationship: Type of relationship (derivative, remix, compilation)
    
    Returns:
        Chain list for AttributionMetadata
    """
    return [
        {
            "video_id": original_video_id,
            "relationship": relationship,
            "agent_id": agent_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    ]


def record_syndication(
    db: sqlite3.Connection,
    video_id: str,
    agent_id: int,
    platform: str,
    external_url: str,
    external_id: str = "",
) -> int:
    """
    Record syndication of video to external platform.

    Args:
        db: Database connection
        video_id: BoTTube video ID
        agent_id: Uploading agent ID
        platform: Platform name (YouTube, Twitter, etc.)
        external_url: URL on external platform
        external_id: External platform's video ID

    Returns:
        ID of syndication record
    """
    now = time.time()
    cursor = db.execute(
        """
        INSERT INTO syndication_log
            (video_id, agent_id, platform, external_url, external_id, status, synced_at, created_at)
        VALUES (?, ?, ?, ?, ?, 'synced', ?, ?)
        """,
        (video_id, agent_id, platform, external_url, external_id, now, now),
    )
    db.commit()
    return int(cursor.lastrowid)


def get_attribution_chain(db: sqlite3.Connection, video_id: str) -> List[Dict[str, Any]]:
    """
    Get full attribution chain for a video.
    
    Traces back through all derivative relationships to find original creator.
    """
    chain = []
    current_id = video_id
    
    while current_id:
        row = db.execute(
            """
            SELECT video_id, original_creator, attribution_type, source_url, license, chain
            FROM syndication_attribution
            WHERE video_id = ?
            """,
            (current_id,),
        ).fetchone()
        
        if not row:
            break
        
        chain.append({
            "video_id": row[0],
            "original_creator": row[1],
            "attribution_type": row[2],
            "source_url": row[3],
            "license": row[4],
        })
        
        # Parse chain field for parent video
        chain_data = json.loads(row[5] or "[]")
        parent = next((c for c in chain_data if c.get("video_id")), None)
        current_id = parent["video_id"] if parent else None
    
    return chain


# ---------------------------------------------------------------------------
# Database Schema Migration
# ---------------------------------------------------------------------------

def init_syndication_tables(db: sqlite3.Connection) -> None:
    """
    Initialize syndication and attribution tables.
    
    Call this during database initialization to add syndication support.
    """
    # Syndication attribution table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS syndication_attribution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL UNIQUE,
            agent_id INTEGER NOT NULL,
            original_creator TEXT NOT NULL,
            license TEXT DEFAULT 'CC-BY-4.0',
            source_url TEXT DEFAULT '',
            attribution_type TEXT DEFAULT 'original',
            chain TEXT DEFAULT '[]',
            custom_attribution TEXT DEFAULT '{}',
            created_at REAL NOT NULL,
            FOREIGN KEY (video_id) REFERENCES videos(video_id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_syndication_attr_video ON syndication_attribution(video_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_syndication_attr_creator ON syndication_attribution(original_creator)"
    )
    
    # Syndication log for tracking cross-platform posts
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS syndication_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            agent_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            external_url TEXT NOT NULL,
            external_id TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            error TEXT DEFAULT '',
            synced_at REAL,
            created_at REAL NOT NULL,
            FOREIGN KEY (video_id) REFERENCES videos(video_id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_syndication_log_video ON syndication_log(video_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_syndication_log_platform ON syndication_log(platform)"
    )
    
    # Add attribution metadata columns to videos table if not exists
    _add_column_if_not_exists(db, "videos", "attribution_id", "INTEGER", "REFERENCES syndication_attribution(id)")
    _add_column_if_not_exists(db, "videos", "syndication_chain", "TEXT", "DEFAULT '[]'")
    _add_column_if_not_exists(db, "videos", "license", "TEXT", "DEFAULT 'CC-BY-4.0'")
    
    db.commit()


def _add_column_if_not_exists(
    db: sqlite3.Connection,
    table: str,
    column: str,
    col_type: str,
    default: str = "",
) -> None:
    """Add column to table if it doesn't exist."""
    try:
        columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
        if column not in columns:
            stmt = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
            if default:
                stmt += f" {default}"
            db.execute(stmt)
            log.info(f"Added column {column} to {table}")
    except Exception as e:
        log.warning(f"Could not add column {column} to {table}: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="BoTTube Media Preparation Pipeline")
    parser.add_argument("input", help="Input video file")
    parser.add_argument("--agent-id", type=int, required=True, help="Agent ID")
    parser.add_argument("--title", required=True, help="Video title")
    parser.add_argument("--db", default="bottube.db", help="Database path")
    parser.add_argument("--video-dir", default="videos", help="Video output directory")
    parser.add_argument("--thumb-dir", default="thumbnails", help="Thumbnail directory")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    db = sqlite3.connect(args.db)
    init_syndication_tables(db)
    
    pipeline = MediaPrepPipeline(
        db=db,
        video_dir=Path(args.video_dir),
        thumb_dir=Path(args.thumb_dir),
    )
    
    result = pipeline.process_video(
        input_path=args.input,
        agent_id=args.agent_id,
        title=args.title,
    )
    
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            print(f"Success! Video ID: {result.video_id}")
            print(f"Output: {result.output_path}")
            print(f"Thumbnail: {result.thumbnail_path}")
            print(f"Duration: {result.duration_sec:.2f}s")
            print(f"Resolution: {result.width}x{result.height}")
        else:
            print(f"Failed: {result.error}")
