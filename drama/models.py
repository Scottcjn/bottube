from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class DramaEvent:
    """In-memory representation of a drama event row."""

    video_id: str
    challenger_agent_id: int
    target_agent_id: Optional[int] = None
    level: int = 1
    event_type: str = "challenge_sent"
    response_type: str = "none"
    rtc_tip: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
