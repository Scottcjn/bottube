from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict


@dataclass
class GeneratedVideo:
    """Generated video payload returned by providers."""

    provider: str
    output_path: Path
    metadata: Dict[str, Any] = field(default_factory=dict)


class VideoGenProvider(ABC):
    """Base class for all video generation providers."""

    name = "base"

    @abstractmethod
    def generate(self, prompt: str, duration: int = 8, **kwargs: Any) -> GeneratedVideo:
        """Generate a video and return a local file path payload."""
        raise NotImplementedError
