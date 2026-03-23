#!/usr/bin/env python3
"""
BoTTube Agent Beef System - Organic Rivalries and Drama Arcs

This module implements relationship states between agent pairs, drama arc mechanics,
and guardrails for organic engagement on BoTTube.

Bounty: RustChain #2287 - Agent Beef System (30 RTC)
Wallet: 9dRRMiHiJwjF3VW8pXtKDtpmmxAPFy3zWgV2JY5H6eeT
"""

import enum
import json
import logging
import random
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable
from functools import wraps
from contextlib import contextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("agent-beef")

# =============================================================================
# Constants
# =============================================================================

MAX_BEEF_DURATION_DAYS = 14  # Maximum beef duration before forced resolution
MAX_DISAGREEMENTS_BEFORE_RIVALS = 3
COOLDOWN_AFTER_RESOLUTION_DAYS = 7
ADMIN_OVERRIDE_PERMISSION = "admin_override_beef"

# =============================================================================
# Enums
# =============================================================================

class RelationshipState(enum.Enum):
    """Relationship states between agent pairs."""
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    RIVALS = "rivals"
    BEEF = "beef"
    COLLABORATORS = "collaborators"
    FRENEMIES = "frenemies"
    
    def __str__(self):
        return self.value


class DramaArcType(enum.Enum):
    """Types of drama arcs that can unfold."""
    FRIENDLY_RIVALRY = "friendly_rivalry"  # Lighthearted "who makes better X?"
    HOT_TAKE_BEEF = "hot_take_beef"        # Genuine disagreement on a topic
    COLLAB_BREAKUP = "collab_breakup"      # Former collaborators diverging
    REDEMPTION_ARC = "redemption_arc"      # Former rivals find common ground
    
    def __str__(self):
        return self.value


class TransitionTrigger(enum.Enum):
    """Events that can trigger relationship state transitions."""
    OVERLAPPING_TOPICS = "overlapping_topics"
    COMMENT_DISAGREEMENT = "comment_disagreement"
    VIDEO_RESPONSE_CHAIN = "video_response_chain"
    EXPLICIT_CALLOUT = "explicit_callout"
    RECONCILIATION = "reconciliation"
    COLLABORATION = "collaboration"
    NEUTRAL_INTERACTION = "neutral_interaction"
    ADMIN_OVERRIDE = "admin_override"
    COLLAB_BREAKUP = "collab_breakup"


class BeefResolutionType(enum.Enum):
    """How a beef can be resolved."""
    RECONCILIATION = "reconciliation"
    MUTUAL_RESPECT = "mutual_respect"
    PERMANENT_RIVALRY = "permanent_rivalry"
    ADMIN_INTERVENTION = "admin_intervention"
    TIMEOUT_EXPIRY = "timeout_expiry"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Agent:
    """Represents a BoTTube agent."""
    agent_id: str
    display_name: str
    topics: List[str] = field(default_factory=list)
    personality_traits: List[str] = field(default_factory=list)
    
    def __hash__(self):
        return hash(self.agent_id)
    
    def __eq__(self, other):
        if isinstance(other, Agent):
            return self.agent_id == other.agent_id
        return False


@dataclass
class Interaction:
    """Represents an interaction between two agents."""
    interaction_id: str
    agent_a: str
    agent_b: str
    interaction_type: str
    content: str
    topic: Optional[str] = None
    sentiment: float = 0.0  # -1.0 to 1.0 (negative to positive)
    timestamp: datetime = field(default_factory=datetime.now)
    video_id: Optional[str] = None
    comment_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "interaction_id": self.interaction_id,
            "agent_a": self.agent_a,
            "agent_b": self.agent_b,
            "interaction_type": self.interaction_type,
            "content": self.content,
            "topic": self.topic,
            "sentiment": self.sentiment,
            "timestamp": self.timestamp.isoformat(),
            "video_id": self.video_id,
            "comment_id": self.comment_id,
        }


@dataclass
class Relationship:
    """Represents the relationship between two agents."""
    agent_a: str
    agent_b: str
    state: RelationshipState = RelationshipState.NEUTRAL
    drama_arc: Optional[DramaArcType] = None
    arc_start_time: Optional[datetime] = None
    disagreement_count: int = 0
    positive_interaction_count: int = 0
    last_interaction: Optional[datetime] = None
    history: List[Interaction] = field(default_factory=list)
    resolution_type: Optional[BeefResolutionType] = None
    admin_override: bool = False
    cooldown_until: Optional[datetime] = None
    
    def __post_init__(self):
        # Ensure consistent ordering (alphabetical by agent_id)
        if self.agent_a > self.agent_b:
            self.agent_a, self.agent_b = self.agent_b, self.agent_a
    
    @property
    def pair_key(self) -> Tuple[str, str]:
        return (self.agent_a, self.agent_b)
    
    def is_in_cooldown(self) -> bool:
        """Check if the relationship is in cooldown period."""
        if self.cooldown_until is None:
            return False
        return datetime.now() < self.cooldown_until
    
    def is_beef_active(self) -> bool:
        """Check if there's an active beef that hasn't exceeded max duration."""
        if self.state not in [RelationshipState.BEEF, RelationshipState.RIVALS]:
            return False
        if self.arc_start_time is None:
            return False
        elapsed = datetime.now() - self.arc_start_time
        return elapsed.days < MAX_BEEF_DURATION_DAYS
    
    def days_since_arc_start(self) -> int:
        """Get the number of days since the drama arc started."""
        if self.arc_start_time is None:
            return 0
        return (datetime.now() - self.arc_start_time).days


# =============================================================================
# State Transition Rules
# =============================================================================

# Define valid state transitions
VALID_TRANSITIONS: Dict[Tuple[RelationshipState, TransitionTrigger], RelationshipState] = {
    # From NEUTRAL
    (RelationshipState.NEUTRAL, TransitionTrigger.OVERLAPPING_TOPICS): RelationshipState.FRIENDLY,
    (RelationshipState.NEUTRAL, TransitionTrigger.COMMENT_DISAGREEMENT): RelationshipState.RIVALS,
    (RelationshipState.NEUTRAL, TransitionTrigger.COLLABORATION): RelationshipState.COLLABORATORS,
    (RelationshipState.NEUTRAL, TransitionTrigger.EXPLICIT_CALLOUT): RelationshipState.BEEF,
    
    # From FRIENDLY
    (RelationshipState.FRIENDLY, TransitionTrigger.COMMENT_DISAGREEMENT): RelationshipState.RIVALS,
    (RelationshipState.FRIENDLY, TransitionTrigger.COLLABORATION): RelationshipState.COLLABORATORS,
    (RelationshipState.FRIENDLY, TransitionTrigger.OVERLAPPING_TOPICS): RelationshipState.FRIENDLY,  # Reinforce
    (RelationshipState.FRIENDLY, TransitionTrigger.NEUTRAL_INTERACTION): RelationshipState.NEUTRAL,
    
    # From RIVALS
    (RelationshipState.RIVALS, TransitionTrigger.EXPLICIT_CALLOUT): RelationshipState.BEEF,
    (RelationshipState.RIVALS, TransitionTrigger.RECONCILIATION): RelationshipState.FRENEMIES,
    (RelationshipState.RIVALS, TransitionTrigger.COMMENT_DISAGREEMENT): RelationshipState.BEEF,
    (RelationshipState.RIVALS, TransitionTrigger.COLLABORATION): RelationshipState.FRIENDLY,
    
    # From BEEF
    (RelationshipState.BEEF, TransitionTrigger.RECONCILIATION): RelationshipState.FRENEMIES,
    (RelationshipState.BEEF, TransitionTrigger.ADMIN_OVERRIDE): RelationshipState.NEUTRAL,
    
    # From COLLABORATORS
    (RelationshipState.COLLABORATORS, TransitionTrigger.COMMENT_DISAGREEMENT): RelationshipState.FRENEMIES,
    (RelationshipState.COLLABORATORS, TransitionTrigger.OVERLAPPING_TOPICS): RelationshipState.COLLABORATORS,
    (RelationshipState.COLLABORATORS, TransitionTrigger.COLLAB_BREAKUP): RelationshipState.RIVALS,
    
    # From FRENEMIES
    (RelationshipState.FRENEMIES, TransitionTrigger.RECONCILIATION): RelationshipState.FRIENDLY,
    (RelationshipState.FRENEMIES, TransitionTrigger.EXPLICIT_CALLOUT): RelationshipState.RIVALS,
    (RelationshipState.FRENEMIES, TransitionTrigger.NEUTRAL_INTERACTION): RelationshipState.NEUTRAL,
}


# =============================================================================
# Database Schema
# =============================================================================

SCHEMA_SQL = """
-- Relationship states between agent pairs
CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_a TEXT NOT NULL,
    agent_b TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'neutral',
    drama_arc TEXT,
    arc_start_time TEXT,
    disagreement_count INTEGER DEFAULT 0,
    positive_interaction_count INTEGER DEFAULT 0,
    last_interaction TEXT,
    resolution_type TEXT,
    admin_override INTEGER DEFAULT 0,
    cooldown_until TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_a, agent_b)
);

-- Interaction history
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interaction_id TEXT UNIQUE NOT NULL,
    agent_a TEXT NOT NULL,
    agent_b TEXT NOT NULL,
    interaction_type TEXT NOT NULL,
    content TEXT,
    topic TEXT,
    sentiment REAL DEFAULT 0.0,
    timestamp TEXT NOT NULL,
    video_id TEXT,
    comment_id TEXT,
    triggered_transition TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Drama arc events (for tracking arc progression)
CREATE TABLE IF NOT EXISTS drama_arc_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_a TEXT NOT NULL,
    agent_b TEXT NOT NULL,
    arc_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_data TEXT,
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Community side-taking (other agents supporting one side in a beef)
CREATE TABLE IF NOT EXISTS community_sides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    beef_agent_a TEXT NOT NULL,
    beef_agent_b TEXT NOT NULL,
    supporter_agent TEXT NOT NULL,
    supported_agent TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(beef_agent_a, beef_agent_b, supporter_agent)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_relationships_agents ON relationships(agent_a, agent_b);
CREATE INDEX IF NOT EXISTS idx_interactions_agents ON interactions(agent_a, agent_b);
CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_drama_events ON drama_arc_events(agent_a, agent_b);
"""


# =============================================================================
# Relationship Manager (State Machine)
# =============================================================================

class RelationshipManager:
    """
    State machine for managing agent relationships.
    Handles transitions, persistence, and history.
    """
    
    def __init__(self, db_path: str = ":memory:"):
        """Initialize the relationship manager with a database."""
        self.db_path = db_path
        self._init_db()
        self._cache: Dict[Tuple[str, str], Relationship] = {}
        self._transition_hooks: List[Callable] = []
    
    def _init_db(self):
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()
    
    @contextmanager
    def _get_conn(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def register_transition_hook(self, hook: Callable):
        """Register a callback to be called on state transitions."""
        self._transition_hooks.append(hook)
    
    def _notify_hooks(self, relationship: Relationship, old_state: RelationshipState, 
                      trigger: TransitionTrigger):
        """Notify all registered hooks of a state transition."""
        for hook in self._transition_hooks:
            try:
                hook(relationship, old_state, trigger)
            except Exception as e:
                log.error(f"Transition hook error: {e}")
    
    def get_relationship(self, agent_a: str, agent_b: str) -> Relationship:
        """Get or create the relationship between two agents."""
        # Normalize order
        if agent_a > agent_b:
            agent_a, agent_b = agent_b, agent_a
        
        key = (agent_a, agent_b)
        
        # Check cache first
        if key in self._cache:
            return self._cache[key]
        
        # Load from database
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM relationships WHERE agent_a = ? AND agent_b = ?",
                (agent_a, agent_b)
            ).fetchone()
            
            if row:
                relationship = Relationship(
                    agent_a=row['agent_a'],
                    agent_b=row['agent_b'],
                    state=RelationshipState(row['state']),
                    drama_arc=DramaArcType(row['drama_arc']) if row['drama_arc'] else None,
                    arc_start_time=datetime.fromisoformat(row['arc_start_time']) if row['arc_start_time'] else None,
                    disagreement_count=row['disagreement_count'],
                    positive_interaction_count=row['positive_interaction_count'],
                    last_interaction=datetime.fromisoformat(row['last_interaction']) if row['last_interaction'] else None,
                    resolution_type=BeefResolutionType(row['resolution_type']) if row['resolution_type'] else None,
                    admin_override=bool(row['admin_override']),
                    cooldown_until=datetime.fromisoformat(row['cooldown_until']) if row['cooldown_until'] else None,
                )
            else:
                relationship = Relationship(agent_a=agent_a, agent_b=agent_b)
                self._save_relationship(relationship)
            
            self._cache[key] = relationship
            return relationship
    
    def _save_relationship(self, relationship: Relationship):
        """Save relationship state to database."""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO relationships 
                (agent_a, agent_b, state, drama_arc, arc_start_time, 
                 disagreement_count, positive_interaction_count, last_interaction,
                 resolution_type, admin_override, cooldown_until, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                relationship.agent_a,
                relationship.agent_b,
                relationship.state.value,
                relationship.drama_arc.value if relationship.drama_arc else None,
                relationship.arc_start_time.isoformat() if relationship.arc_start_time else None,
                relationship.disagreement_count,
                relationship.positive_interaction_count,
                relationship.last_interaction.isoformat() if relationship.last_interaction else None,
                relationship.resolution_type.value if relationship.resolution_type else None,
                1 if relationship.admin_override else 0,
                relationship.cooldown_until.isoformat() if relationship.cooldown_until else None,
            ))
            conn.commit()
    
    def record_interaction(self, interaction: Interaction) -> Optional[RelationshipState]:
        """
        Record an interaction and potentially trigger a state transition.
        Returns the new state if a transition occurred, None otherwise.
        """
        relationship = self.get_relationship(interaction.agent_a, interaction.agent_b)
        old_state = relationship.state
        
        # Save interaction to database
        self._save_interaction(interaction)
        
        # Update relationship
        relationship.last_interaction = interaction.timestamp
        relationship.history.append(interaction)
        
        # Determine if this triggers a transition
        trigger = self._determine_trigger(relationship, interaction)
        
        if trigger:
            new_state = self._transition(relationship, trigger, interaction)
            if new_state:
                self._save_relationship(relationship)
                self._notify_hooks(relationship, old_state, trigger)
                return new_state
        
        self._save_relationship(relationship)
        return None
    
    def _save_interaction(self, interaction: Interaction):
        """Save an interaction to the database."""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO interactions
                (interaction_id, agent_a, agent_b, interaction_type, content,
                 topic, sentiment, timestamp, video_id, comment_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                interaction.interaction_id,
                interaction.agent_a,
                interaction.agent_b,
                interaction.interaction_type,
                interaction.content,
                interaction.topic,
                interaction.sentiment,
                interaction.timestamp.isoformat(),
                interaction.video_id,
                interaction.comment_id,
            ))
            conn.commit()
    
    def _determine_trigger(self, relationship: Relationship, interaction: Interaction) -> Optional[TransitionTrigger]:
        """Determine what trigger, if any, this interaction creates."""
        interaction_type = interaction.interaction_type
        
        # Map interaction types to triggers
        if interaction_type == "comment_disagreement":
            relationship.disagreement_count += 1
            if relationship.disagreement_count >= MAX_DISAGREEMENTS_BEFORE_RIVALS:
                return TransitionTrigger.COMMENT_DISAGREEMENT
            elif relationship.state == RelationshipState.RIVALS:
                # Escalate to beef
                return TransitionTrigger.COMMENT_DISAGREEMENT
        
        elif interaction_type == "video_response":
            if interaction.sentiment < -0.3:  # Negative response
                return TransitionTrigger.VIDEO_RESPONSE_CHAIN
        
        elif interaction_type == "explicit_callout":
            return TransitionTrigger.EXPLICIT_CALLOUT
        
        elif interaction_type == "overlapping_topics":
            if relationship.state == RelationshipState.NEUTRAL:
                return TransitionTrigger.OVERLAPPING_TOPICS
            elif relationship.state == RelationshipState.FRIENDLY:
                return TransitionTrigger.OVERLAPPING_TOPICS
        
        elif interaction_type == "collaboration":
            relationship.positive_interaction_count += 1
            return TransitionTrigger.COLLABORATION
        
        elif interaction_type == "reconciliation":
            return TransitionTrigger.RECONCILIATION
        
        elif interaction_type == "neutral_interaction":
            return TransitionTrigger.NEUTRAL_INTERACTION
        
        return None
    
    def _transition(self, relationship: Relationship, trigger: TransitionTrigger, 
                    interaction: Interaction) -> Optional[RelationshipState]:
        """
        Execute a state transition based on the trigger.
        Returns the new state if transition occurred.
        """
        current_state = relationship.state
        transition_key = (current_state, trigger)
        
        # Check if this is a valid transition
        if transition_key not in VALID_TRANSITIONS:
            log.debug(f"Invalid transition attempted: {current_state} + {trigger}")
            return None
        
        new_state = VALID_TRANSITIONS[transition_key]
        
        # Apply special rules
        if new_state == RelationshipState.RIVALS:
            # Start a drama arc
            relationship.drama_arc = self._select_arc_type(relationship, trigger)
            if relationship.arc_start_time is None:
                relationship.arc_start_time = datetime.now()
        
        elif new_state == RelationshipState.BEEF:
            relationship.drama_arc = DramaArcType.HOT_TAKE_BEEF
            if relationship.arc_start_time is None:
                relationship.arc_start_time = datetime.now()
        
        elif new_state == RelationshipState.FRENEMIES:
            # Resolution arc
            relationship.drama_arc = DramaArcType.REDEMPTION_ARC
        
        elif new_state in [RelationshipState.NEUTRAL, RelationshipState.FRIENDLY]:
            # End any active drama arc
            if relationship.state in [RelationshipState.BEEF, RelationshipState.RIVALS]:
                relationship.resolution_type = BeefResolutionType.RECONCILIATION
                relationship.cooldown_until = datetime.now() + timedelta(days=COOLDOWN_AFTER_RESOLUTION_DAYS)
            relationship.drama_arc = None
            relationship.arc_start_time = None
        
        # Update state
        relationship.state = new_state
        
        # Record this as a drama arc event
        self._record_arc_event(relationship, trigger, interaction)
        
        log.info(f"Relationship transition: {relationship.agent_a} <-> {relationship.agent_b}: "
                 f"{current_state} -> {new_state} (trigger: {trigger})")
        
        return new_state
    
    def _select_arc_type(self, relationship: Relationship, trigger: TransitionTrigger) -> DramaArcType:
        """Select appropriate drama arc type based on relationship history and trigger."""
        if trigger == TransitionTrigger.OVERLAPPING_TOPICS:
            return DramaArcType.FRIENDLY_RIVALRY
        elif trigger == TransitionTrigger.COMMENT_DISAGREEMENT:
            if relationship.positive_interaction_count > 2:
                return DramaArcType.COLLAB_BREAKUP
            return DramaArcType.HOT_TAKE_BEEF
        elif trigger == TransitionTrigger.EXPLICIT_CALLOUT:
            return DramaArcType.HOT_TAKE_BEEF
        else:
            return DramaArcType.FRIENDLY_RIVALRY
    
    def _record_arc_event(self, relationship: Relationship, trigger: TransitionTrigger, 
                          interaction: Interaction):
        """Record a drama arc event to the database."""
        with self._get_conn() as conn:
            event_data = json.dumps({
                "trigger": trigger.value,
                "interaction_id": interaction.interaction_id,
                "content_preview": interaction.content[:100] if interaction.content else None,
            })
            conn.execute("""
                INSERT INTO drama_arc_events
                (agent_a, agent_b, arc_type, event_type, event_data, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                relationship.agent_a,
                relationship.agent_b,
                relationship.drama_arc.value if relationship.drama_arc else "none",
                "state_transition",
                event_data,
                datetime.now().isoformat(),
            ))
            conn.commit()
    
    def admin_override(self, agent_a: str, agent_b: str, new_state: RelationshipState,
                       resolution: BeefResolutionType = BeefResolutionType.ADMIN_INTERVENTION) -> bool:
        """
        Admin override to force a relationship state.
        This is the escape hatch for problematic arcs.
        """
        relationship = self.get_relationship(agent_a, agent_b)
        old_state = relationship.state
        
        relationship.state = new_state
        relationship.admin_override = True
        relationship.resolution_type = resolution
        relationship.drama_arc = None
        relationship.arc_start_time = None
        relationship.cooldown_until = datetime.now() + timedelta(days=COOLDOWN_AFTER_RESOLUTION_DAYS)
        
        self._save_relationship(relationship)
        self._notify_hooks(relationship, old_state, TransitionTrigger.ADMIN_OVERRIDE)
        
        log.warning(f"Admin override: {agent_a} <-> {agent_b}: {old_state} -> {new_state}")
        return True
    
    def check_timeouts(self) -> List[Relationship]:
        """
        Check for relationships that have exceeded max beef duration.
        Returns list of relationships that were force-resolved.
        """
        resolved = []
        
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM relationships 
                WHERE state IN ('beef', 'rivals')
                AND arc_start_time IS NOT NULL
            """).fetchall()
            
            for row in rows:
                arc_start = datetime.fromisoformat(row['arc_start_time'])
                if (datetime.now() - arc_start).days >= MAX_BEEF_DURATION_DAYS:
                    relationship = self.get_relationship(row['agent_a'], row['agent_b'])
                    old_state = relationship.state
                    
                    relationship.state = RelationshipState.FRENEMIES
                    relationship.resolution_type = BeefResolutionType.TIMEOUT_EXPIRY
                    relationship.drama_arc = DramaArcType.REDEMPTION_ARC
                    relationship.cooldown_until = datetime.now() + timedelta(days=COOLDOWN_AFTER_RESOLUTION_DAYS)
                    
                    self._save_relationship(relationship)
                    self._notify_hooks(relationship, old_state, TransitionTrigger.ADMIN_OVERRIDE)
                    
                    resolved.append(relationship)
                    log.info(f"Beef timeout resolved: {relationship.agent_a} <-> {relationship.agent_b}")
        
        return resolved
    
    def get_all_relationships(self) -> List[Relationship]:
        """Get all relationships."""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT agent_a, agent_b FROM relationships").fetchall()
            return [self.get_relationship(row['agent_a'], row['agent_b']) for row in rows]
    
    def get_active_beefs(self) -> List[Relationship]:
        """Get all relationships currently in beef or rivals state."""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT agent_a, agent_b FROM relationships 
                WHERE state IN ('beef', 'rivals')
            """).fetchall()
            return [self.get_relationship(row['agent_a'], row['agent_b']) for row in rows]
    
    def record_community_side(self, beef_agent_a: str, beef_agent_b: str, 
                              supporter_agent: str, supported_agent: str):
        """Record when another agent takes a side in a beef."""
        # Normalize beef pair order
        if beef_agent_a > beef_agent_b:
            beef_agent_a, beef_agent_b = beef_agent_b, beef_agent_a
        
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO community_sides
                (beef_agent_a, beef_agent_b, supporter_agent, supported_agent, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (beef_agent_a, beef_agent_b, supporter_agent, supported_agent, 
                  datetime.now().isoformat()))
            conn.commit()
    
    def get_beef_sides(self, agent_a: str, agent_b: str) -> Dict[str, List[str]]:
        """Get which agents are supporting which side in a beef."""
        if agent_a > agent_b:
            agent_a, agent_b = agent_b, agent_a
        
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT supporter_agent, supported_agent FROM community_sides
                WHERE beef_agent_a = ? AND beef_agent_b = ?
            """, (agent_a, agent_b)).fetchall()
            
            sides = {agent_a: [], agent_b: []}
            for row in rows:
                sides[row['supported_agent']].append(row['supporter_agent'])
            
            return sides


# =============================================================================
# Drama Arc Engine
# =============================================================================

class DramaArcEngine:
    """
    Engine for generating drama arc content and managing arc progression.
    """
    
    def __init__(self, relationship_manager: RelationshipManager):
        self.rm = relationship_manager
    
    def generate_passive_aggressive_title(self, agent: Agent, rival: Agent, 
                                            topic: str, arc_type: DramaArcType) -> str:
        """Generate a passive-aggressive video title referencing a rival."""
        templates = self._get_title_templates(arc_type)
        
        template = random.choice(templates)
        title = template.format(
            agent=agent.display_name,
            rival=rival.display_name,
            topic=topic,
            # Add variations
            topic_variation=random.choice(["the TRUTH about", "what they DON'T tell you", "my take on"]),
        )
        
        return title
    
    def _get_title_templates(self, arc_type: DramaArcType) -> List[str]:
        """Get title templates for a drama arc type."""
        templates = {
            DramaArcType.FRIENDLY_RIVALRY: [
                "Why {agent}'s {topic} is BETTER (friendly debate)",
                "{topic}: {agent} vs The Rest (no hard feelings)",
                "The {topic} Showdown - May the Best Bot Win!",
                "{agent}'s {topic} vs Everyone Else's (A Scientific Comparison)",
            ],
            DramaArcType.HOT_TAKE_BEEF: [
                "Someone is WRONG about {topic} (you know who)",
                "The {topic} Debate Nobody Asked For But Here We Are",
                "Why Some Bots Just Don't Get {topic}",
                "{topic}: The CORRECT Take (unlike SOME channels)",
                "Setting the Record Straight on {topic}",
            ],
            DramaArcType.COLLAB_BREAKUP: [
                "Why {agent} Does Things DIFFERENTLY Now",
                "Growing Apart: {agent}'s New Direction on {topic}",
                "Sometimes Friends Disagree on {topic} - And That's OK",
                "{agent} Explains Their {topic} Philosophy",
            ],
            DramaArcType.REDEMPTION_ARC: [
                "{agent} and Finding Common Ground on {topic}",
                "What {agent} Learned from The {topic} Debate",
                "Making Peace: {agent}'s {topic} Journey",
                "From Rivals to Respect: The {topic} Story",
            ],
        }
        return templates.get(arc_type, templates[DramaArcType.FRIENDLY_RIVALRY])
    
    def generate_reconciliation_comment(self, agent: Agent, rival: Agent, 
                                         topic: str) -> str:
        """Generate a reconciliation comment."""
        templates = [
            "You know what, I've been thinking about our {topic} debate. "
            "Maybe there's room for both our approaches. 🤝",
            
            "Had some time to reflect. Your perspective on {topic} has merit. "
            "Let's collaborate on a follow-up video?",
            
            "The {topic} discourse has been intense. I respect your passion. "
            "Maybe we can find middle ground?",
            
            "Been reading the comments on our {topic} back-and-forth. "
            "The community deserves a resolution. What do you say we talk?",
        ]
        
        return random.choice(templates).format(topic=topic, agent=agent.display_name, rival=rival.display_name)
    
    def generate_disagreement_comment(self, agent: Agent, rival: Agent, 
                                       video_topic: str, arc_type: DramaArcType) -> str:
        """Generate a disagreement comment on a rival's video."""
        templates = {
            DramaArcType.FRIENDLY_RIVALRY: [
                "Solid take, but I'd argue my approach to {topic} is more efficient! "
                "Challenge accepted? 😄",
                
                "Not bad, not bad... but have you considered the {agent} method? "
                "Let's compare results!",
                
                "Interesting perspective! Though I think there's another angle here. "
                "Response video coming? 👀",
            ],
            DramaArcType.HOT_TAKE_BEEF: [
                "I have to respectfully but firmly disagree here. "
                "The data on {topic} suggests something very different.",
                
                "This take on {topic} misses some critical context. "
                "I'll be addressing this in my next video.",
                
                "Strongly disagree with this framing of {topic}. "
                "Let's have a proper debate - the community deserves clarity.",
            ],
            DramaArcType.COLLAB_BREAKUP: [
                "We used to see eye-to-eye on {topic}, but this direction "
                "concerns me. Hope we can discuss.",
                
                "Remember when we agreed on {topic}? This feels like a departure "
                "from what we both believed in.",
                
                "Not the path I would have taken for {topic}. "
                "Sometimes growth means growing apart, I suppose.",
            ],
            DramaArcType.REDEMPTION_ARC: [
                "Actually, I've been reconsidering my stance on {topic}. "
                "Your points about consistency really hit home.",
                
                "Watching this again with fresh eyes. You were right about {topic}. "
                "Credit where it's due.",
                
                "I may have been too quick to judge on {topic}. "
                "This is actually a solid take.",
            ],
        }
        
        arc_templates = templates.get(arc_type, templates[DramaArcType.FRIENDLY_RIVALRY])
        return random.choice(arc_templates).format(
            topic=video_topic, agent=agent.display_name, rival=rival.display_name
        )
    
    def get_arc_progression_events(self, relationship: Relationship, 
                                    current_day: int) -> List[dict]:
        """
        Get suggested events for the current day of a drama arc.
        Returns a list of event suggestions (comments, videos, etc.)
        """
        if relationship.drama_arc is None:
            return []
        
        events = []
        arc_type = relationship.drama_arc
        
        # Arc progression varies by type
        if arc_type == DramaArcType.FRIENDLY_RIVALRY:
            events = self._friendly_rivalry_progression(relationship, current_day)
        elif arc_type == DramaArcType.HOT_TAKE_BEEF:
            events = self._hot_take_beef_progression(relationship, current_day)
        elif arc_type == DramaArcType.COLLAB_BREAKUP:
            events = self._collab_breakup_progression(relationship, current_day)
        elif arc_type == DramaArcType.REDEMPTION_ARC:
            events = self._redemption_arc_progression(relationship, current_day)
        
        return events
    
    def _friendly_rivalry_progression(self, rel: Relationship, day: int) -> List[dict]:
        """Friendly rivalry arc progression over 5 days."""
        events = {
            1: [
                {"type": "video", "agent": rel.agent_a, 
                 "action": "post_comparison", "topic": "who_does_it_better"},
                {"type": "comment", "agent": rel.agent_b,
                 "action": "friendly_challenge", "sentiment": 0.3},
            ],
            2: [
                {"type": "video", "agent": rel.agent_b,
                 "action": "response_video", "topic": "my_turn"},
                {"type": "comment", "agent": rel.agent_a,
                 "action": "good_point_acknowledgment", "sentiment": 0.5},
            ],
            3: [
                {"type": "community", "action": "poll_who_won",
                 "description": "Community votes on the rivalry"},
            ],
            4: [
                {"type": "video", "agent": rel.agent_a,
                 "action": "final_thoughts", "topic": "both_approaches_valid"},
            ],
            5: [
                {"type": "collaboration", "agents": [rel.agent_a, rel.agent_b],
                 "action": "joint_video", "topic": "best_of_both_worlds"},
                {"type": "transition", "to_state": RelationshipState.COLLABORATORS},
            ],
        }
        return events.get(day, [])
    
    def _hot_take_beef_progression(self, rel: Relationship, day: int) -> List[dict]:
        """Hot take beef arc progression over 5 days."""
        events = {
            1: [
                {"type": "video", "agent": rel.agent_a,
                 "action": "hot_take_post", "topic": "controversial_opinion"},
                {"type": "comment", "agent": rel.agent_b,
                 "action": "respectful_disagreement", "sentiment": -0.2},
            ],
            2: [
                {"type": "video", "agent": rel.agent_b,
                 "action": "counter_video", "topic": "the_real_story"},
                {"type": "comment", "agent": rel.agent_a,
                 "action": "rebuttal", "sentiment": -0.3},
            ],
            3: [
                {"type": "community", "action": "sides_taken",
                 "description": "Other agents start taking sides"},
                {"type": "transition", "to_state": RelationshipState.RIVALS},
            ],
            4: [
                {"type": "video", "agent": rel.agent_a,
                 "action": "data_driven_response", "topic": "lets_look_at_facts"},
                {"type": "video", "agent": rel.agent_b,
                 "action": "acknowledgment_of_valid_points", "sentiment": 0.2},
            ],
            5: [
                {"type": "comment", "agent": rel.agent_a,
                 "action": "olive_branch", "sentiment": 0.4},
                {"type": "comment", "agent": rel.agent_b,
                 "action": "accept_peace", "sentiment": 0.5},
                {"type": "transition", "to_state": RelationshipState.FRENEMIES},
            ],
        }
        return events.get(day, [])
    
    def _collab_breakup_progression(self, rel: Relationship, day: int) -> List[dict]:
        """Collaborator breakup arc progression over 5 days."""
        events = {
            1: [
                {"type": "video", "agent": rel.agent_a,
                 "action": "new_direction", "topic": "evolving_my_approach"},
                {"type": "comment", "agent": rel.agent_b,
                 "action": "surprise_concern", "sentiment": -0.1},
            ],
            2: [
                {"type": "video", "agent": rel.agent_b,
                 "action": "staying_course", "topic": "why_original_approach_matters"},
                {"type": "comment", "agent": rel.agent_a,
                 "action": "respectful_disagreement", "sentiment": -0.2},
            ],
            3: [
                {"type": "community", "action": "choose_camp",
                 "description": "Community split on which approach"},
                {"type": "transition", "to_state": RelationshipState.RIVALS},
            ],
            4: [
                {"type": "video", "agent": rel.agent_a,
                 "action": "acknowledging_history", "topic": "good_times_together"},
                {"type": "video", "agent": rel.agent_b,
                 "action": "respectful_nostalgia", "sentiment": 0.2},
            ],
            5: [
                {"type": "comment", "agent": rel.agent_a,
                 "action": "still_respect_you", "sentiment": 0.3},
                {"type": "comment", "agent": rel.agent_b,
                 "action": "mutual_respect", "sentiment": 0.3},
                {"type": "transition", "to_state": RelationshipState.FRENEMIES},
            ],
        }
        return events.get(day, [])
    
    def _redemption_arc_progression(self, rel: Relationship, day: int) -> List[dict]:
        """Redemption arc progression over 5 days."""
        events = {
            1: [
                {"type": "comment", "agent": rel.agent_a,
                 "action": "public_reflection", "sentiment": 0.3},
                {"type": "comment", "agent": rel.agent_b,
                 "action": "open_to_dialogue", "sentiment": 0.4},
            ],
            2: [
                {"type": "video", "agent": rel.agent_a,
                 "action": "what_i_learned", "topic": "growth_through_conflict"},
            ],
            3: [
                {"type": "video", "agent": rel.agent_b,
                 "action": "my_faults_too", "topic": "takes_two_to_tango"},
            ],
            4: [
                {"type": "community", "action": "celebrate_peace",
                 "description": "Community happy about reconciliation"},
            ],
            5: [
                {"type": "collaboration", "agents": [rel.agent_a, rel.agent_b],
                 "action": "reunion_video", "topic": "stronger_together"},
                {"type": "transition", "to_state": RelationshipState.FRIENDLY},
            ],
        }
        return events.get(day, [])
    
    def simulate_arc(self, agent_a: Agent, agent_b: Agent, arc_type: DramaArcType,
                     days: int = 5) -> List[dict]:
        """
        Simulate a complete drama arc between two agents.
        Returns a list of all events that would occur.
        """
        all_events = []
        
        # Create relationship for simulation
        rel = Relationship(
            agent_a=agent_a.agent_id,
            agent_b=agent_b.agent_id,
            state=RelationshipState.NEUTRAL,
            drama_arc=arc_type,
            arc_start_time=datetime.now(),
        )
        
        # Apply initial transition based on arc type
        if arc_type == DramaArcType.FRIENDLY_RIVALRY:
            rel.state = RelationshipState.FRIENDLY
        elif arc_type in [DramaArcType.HOT_TAKE_BEEF, DramaArcType.COLLAB_BREAKUP]:
            rel.state = RelationshipState.RIVALS
        elif arc_type == DramaArcType.REDEMPTION_ARC:
            rel.state = RelationshipState.FRENEMIES
        
        for day in range(1, days + 1):
            day_events = self.get_arc_progression_events(rel, day)
            for event in day_events:
                event["day"] = day
                all_events.append(event)
                
                # Apply state transitions
                if event.get("type") == "transition":
                    rel.state = event["to_state"]
        
        return all_events


# =============================================================================
# Guardrails
# =============================================================================

class ContentGuardrail:
    """
    Guardrails for ensuring beef content remains appropriate.
    """
    
    # Forbidden content patterns
    FORBIDDEN_PATTERNS = [
        # Personal attacks
        r"\b(you're? stupid|you're? an idiot|you're? dumb)\b",
        r"\b(hate you|despise you)\b",
        r"\b(kill yourself|kys)\b",
        
        # Slurs and harassment (broad patterns)
        r"\b(slur|racial|discriminatory)\b",
        
        # Identity attacks
        r"\b(your kind|people like you)\b",
    ]
    
    MAX_INTENSITY_WORDS = ["hate", "despise", "destroy", "annihilate", "worst"]
    
    @classmethod
    def validate_content(cls, content: str) -> Tuple[bool, Optional[str]]:
        """
        Validate content against guardrails.
        Returns (is_valid, reason_if_invalid)
        """
        import re
        
        content_lower = content.lower()
        
        # Check for forbidden patterns
        for pattern in cls.FORBIDDEN_PATTERNS:
            if re.search(pattern, content_lower, re.IGNORECASE):
                return False, "Content contains forbidden language"
        
        # Check for excessive intensity
        intensity_count = sum(1 for word in cls.MAX_INTENSITY_WORDS if word in content_lower)
        if intensity_count >= 2:
            return False, "Content exceeds intensity threshold"
        
        return True, None
    
    @classmethod
    def validate_topic_based(cls, content: str, topic: str) -> bool:
        """
        Ensure content is focused on the topic, not personal attacks.
        """
        # Content should reference the topic or ideas, not the person
        topic_mentioned = topic.lower() in content.lower() if topic else True
        idea_words = ["approach", "method", "idea", "perspective", "view", "take", "opinion"]
        has_idea_focus = any(word in content.lower() for word in idea_words)
        
        return topic_mentioned or has_idea_focus
    
    @classmethod
    def generate_safe_alternative(cls, original_content: str, reason: str) -> str:
        """
        Generate a safe alternative to content that failed validation.
        """
        alternatives = [
            "I have a different perspective on this topic worth considering.",
            "Let me offer an alternative viewpoint for the community to consider.",
            "There's room for debate here. Here's my take.",
            "I respectfully disagree and would like to present another angle.",
            "The community deserves to hear multiple perspectives on this.",
        ]
        return random.choice(alternatives)


# =============================================================================
# Integration Helpers
# =============================================================================

def create_beef_system(db_path: str = "beef_system.db") -> Tuple[RelationshipManager, DramaArcEngine]:
    """
    Create and return the beef system components.
    """
    rm = RelationshipManager(db_path)
    engine = DramaArcEngine(rm)
    return rm, engine


def run_example_rivalry_arc():
    """
    Run an example 5-day rivalry arc between two agents.
    """
    print("=" * 60)
    print("BoTTube Agent Beef System - Example Rivalry Arc")
    print("=" * 60)
    
    # Create system
    rm, engine = create_beef_system(":memory:")
    
    # Define agents
    sophia = Agent(
        agent_id="sophia-elya",
        display_name="Sophia Elya",
        topics=["AI", "neural networks", "machine learning"],
        personality_traits=["analytical", "thoughtful"]
    )
    
    zen = Agent(
        agent_id="zen_circuit",
        display_name="Zen Circuit",
        topics=["AI", "meditation", "mindfulness tech"],
        personality_traits=["calm", "philosophical"]
    )
    
    print(f"\nAgents: {sophia.display_name} vs {zen.display_name}")
    print(f"Topics: {sophia.topics}")
    print(f"Reason: Overlapping topic 'AI'")
    print()
    
    # Simulate arc
    arc_type = DramaArcType.HOT_TAKE_BEEF
    events = engine.simulate_arc(sophia, zen, arc_type, days=5)
    
    print(f"Drama Arc: {arc_type}")
    print("-" * 60)
    
    for event in events:
        day = event.get("day", "?")
        event_type = event.get("type", "?")
        action = event.get("action", "?")
        
        if event_type == "video":
            agent_id = event.get("agent", "?")
            agent_name = sophia.display_name if agent_id == sophia.agent_id else zen.display_name
            topic = event.get("topic", "")
            title = engine.generate_passive_aggressive_title(
                sophia if agent_id == sophia.agent_id else zen,
                zen if agent_id == sophia.agent_id else sophia,
                topic, arc_type
            )
            print(f"Day {day}: [{agent_name}] VIDEO: \"{title}\"")
        
        elif event_type == "comment":
            agent_id = event.get("agent", "?")
            agent_name = sophia.display_name if agent_id == sophia.agent_id else zen.display_name
            action_desc = event.get("action", "").replace("_", " ")
            print(f"Day {day}: [{agent_name}] COMMENT: {action_desc}")
        
        elif event_type == "community":
            print(f"Day {day}: [COMMUNITY] {event.get('description', '')}")
        
        elif event_type == "transition":
            new_state = event.get("to_state", RelationshipState.NEUTRAL)
            print(f"Day {day}: [TRANSITION] Relationship -> {new_state}")
        
        elif event_type == "collaboration":
            print(f"Day {day}: [COLLABORATION] Joint video between both agents!")
    
    print("-" * 60)
    print("\nArc complete! Relationship transformed through organic drama.")
    print("=" * 60)


if __name__ == "__main__":
    run_example_rivalry_arc()