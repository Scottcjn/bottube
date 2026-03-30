"""
generation/models.py - Internal job schema and enums
=====================================================
Defines the canonical data structures for video generation jobs.
owner_user_id is IMMUTABLE once set -- enforced at the dataclass level
and in the database schema (NOT NULL, no UPDATE path).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    """Lifecycle of a generation job."""
    queued = "queued"
    routing = "routing"
    submitted = "submitted"
    generating = "generating"
    assembling = "assembling"
    transcoding = "transcoding"
    publishing = "publishing"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class GenerationMode(str, Enum):
    """What kind of generation pipeline to run."""
    text_to_video = "text_to_video"
    image_to_video = "image_to_video"
    text_to_image_sequence = "text_to_image_sequence"
    avatar_video = "avatar_video"
    remix = "remix"


# ---------------------------------------------------------------------------
# Request / Job dataclasses
# ---------------------------------------------------------------------------

@dataclass
class GenerationRequest:
    """User-facing request parameters."""
    prompt: str
    duration: int = 8
    aspect_ratio: str = "1:1"
    mode: GenerationMode = GenerationMode.text_to_video
    category: str = "other"
    style: str = ""
    provider_hint: str = ""          # e.g. "comfyui", "huggingface"
    include_voiceover: bool = False
    include_captions: bool = False
    include_music: bool = False

    # Title for the final video record (defaults to truncated prompt)
    title: str = ""

    def __post_init__(self):
        self.prompt = self.prompt.strip()[:500]
        self.duration = max(1, min(self.duration, 300))
        if not self.title:
            self.title = self.prompt[:200]
        if isinstance(self.mode, str):
            self.mode = GenerationMode(self.mode)

    def to_dict(self) -> dict:
        return {
            "prompt": self.prompt,
            "duration": self.duration,
            "aspect_ratio": self.aspect_ratio,
            "mode": self.mode.value,
            "category": self.category,
            "style": self.style,
            "provider_hint": self.provider_hint,
            "include_voiceover": self.include_voiceover,
            "include_captions": self.include_captions,
            "include_music": self.include_music,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GenerationRequest":
        return cls(
            prompt=d.get("prompt", ""),
            duration=int(d.get("duration", 8)),
            aspect_ratio=d.get("aspect_ratio", "1:1"),
            mode=d.get("mode", "text_to_video"),
            category=d.get("category", "other"),
            style=d.get("style", ""),
            provider_hint=d.get("provider_hint", ""),
            include_voiceover=bool(d.get("include_voiceover", False)),
            include_captions=bool(d.get("include_captions", False)),
            include_music=bool(d.get("include_music", False)),
            title=d.get("title", ""),
        )


@dataclass
class InternalJob:
    """Server-side job state.  owner_user_id is set once and never changed."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    owner_user_id: int = 0           # IMMUTABLE after creation
    request: GenerationRequest = field(default_factory=lambda: GenerationRequest(prompt=""))
    status: JobStatus = JobStatus.queued
    selected_provider: str = ""
    external_job_id: str = ""
    progress: float = 0.0            # 0.0 - 1.0
    error: str = ""

    # Output references
    video_id: str = ""               # BoTTube video_id once published
    video_url: str = ""
    output_path: str = ""            # local filesystem path to generated file

    # Timing
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    # Routing metadata
    fallback_chain: List[str] = field(default_factory=list)
    attempt_count: int = 0

    # Quality gate
    quality_score: float = 0.0
    quality_passed: bool = False
    requires_approval: bool = False

    def touch(self):
        self.updated_at = time.time()

    def fail(self, error: str):
        self.status = JobStatus.failed
        self.error = error[:500]
        self.touch()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner_user_id": self.owner_user_id,
            "request": self.request.to_dict(),
            "status": self.status.value,
            "selected_provider": self.selected_provider,
            "external_job_id": self.external_job_id,
            "progress": self.progress,
            "error": self.error,
            "video_id": self.video_id,
            "video_url": self.video_url,
            "output_path": self.output_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "fallback_chain": self.fallback_chain,
            "attempt_count": self.attempt_count,
            "quality_score": self.quality_score,
            "quality_passed": self.quality_passed,
            "requires_approval": self.requires_approval,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InternalJob":
        job = cls(
            id=d.get("id", uuid.uuid4().hex[:16]),
            owner_user_id=d["owner_user_id"],
            request=GenerationRequest.from_dict(d.get("request", {})),
            status=JobStatus(d.get("status", "queued")),
            selected_provider=d.get("selected_provider", ""),
            external_job_id=d.get("external_job_id", ""),
            progress=d.get("progress", 0.0),
            error=d.get("error", ""),
            video_id=d.get("video_id", ""),
            video_url=d.get("video_url", ""),
            output_path=d.get("output_path", ""),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
            completed_at=d.get("completed_at", 0.0),
            fallback_chain=d.get("fallback_chain", []),
            attempt_count=d.get("attempt_count", 0),
            quality_score=d.get("quality_score", 0.0),
            quality_passed=d.get("quality_passed", False),
            requires_approval=d.get("requires_approval", False),
        )
        return job
