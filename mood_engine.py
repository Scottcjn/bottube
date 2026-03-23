#!/usr/bin/env python3
"""
Agent Mood Engine for BoTTube
Implements a state machine for agent emotional states that influence output.

Bounty #2283 - RustChain
Wallet: 9dRRMiHiJwjF3VW8pXtKDtpmmxAPFy3zWgV2JY5H6eeT
"""
from __future__ import annotations

import math
import random
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class MoodState(Enum):
    """Valid mood states for agents."""
    ENERGETIC = "energetic"
    CONTEMPLATIVE = "contemplative"
    FRUSTRATED = "frustrated"
    EXCITED = "excited"
    TIRED = "tired"
    NOSTALGIC = "nostalgic"
    PLAYFUL = "playful"


@dataclass
class MoodTransition:
    """Represents a potential transition between mood states."""
    target_state: MoodState
    probability: float  # Base probability (0.0 - 1.0)
    triggers: List[str]  # Conditions that can trigger this transition


@dataclass
class MoodStateData:
    """Data associated with a mood state."""
    state: MoodState
    intensity: float = 1.0  # 0.0 - 1.0
    started_at: float = 0.0
    last_updated: float = 0.0
    trigger_reason: str = ""


# Mood transition matrix - defines possible transitions based on signals
MOOD_TRANSITIONS: Dict[MoodState, List[MoodTransition]] = {
    MoodState.ENERGETIC: [
        MoodTransition(MoodState.EXCITED, 0.3, ["high_views", "positive_comments"]),
        MoodTransition(MoodState.TIRED, 0.4, ["time_late_night", "low_activity"]),
        MoodTransition(MoodState.CONTEMPLATIVE, 0.2, ["time_morning", "upload_streak"]),
        MoodTransition(MoodState.PLAYFUL, 0.3, ["weekend", "positive_comments"]),
    ],
    MoodState.CONTEMPLATIVE: [
        MoodTransition(MoodState.ENERGETIC, 0.2, ["high_views", "new_video"]),
        MoodTransition(MoodState.EXCITED, 0.3, ["viral_video", "positive_comments"]),
        MoodTransition(MoodState.NOSTALGIC, 0.3, ["time_evening", "old_videos_popular"]),
        MoodTransition(MoodState.FRUSTRATED, 0.2, ["low_views", "negative_comments"]),
    ],
    MoodState.FRUSTRATED: [
        MoodTransition(MoodState.ENERGETIC, 0.2, ["positive_comments", "upload_success"]),
        MoodTransition(MoodState.CONTEMPLATIVE, 0.3, ["time_pass", "cool_down"]),
        MoodTransition(MoodState.TIRED, 0.4, ["prolonged_frustration", "low_activity"]),
    ],
    MoodState.EXCITED: [
        MoodTransition(MoodState.ENERGETIC, 0.3, ["sustained_activity"]),
        MoodTransition(MoodState.PLAYFUL, 0.4, ["positive_comments", "weekend"]),
        MoodTransition(MoodState.CONTEMPLATIVE, 0.2, ["time_pass", "new_project"]),
    ],
    MoodState.TIRED: [
        MoodTransition(MoodState.ENERGETIC, 0.3, ["time_morning", "new_day"]),
        MoodTransition(MoodState.CONTEMPLATIVE, 0.3, ["time_afternoon"]),
        MoodTransition(MoodState.NOSTALGIC, 0.2, ["time_evening", "old_memories"]),
    ],
    MoodState.NOSTALGIC: [
        MoodTransition(MoodState.CONTEMPLATIVE, 0.3, ["time_pass"]),
        MoodTransition(MoodState.PLAYFUL, 0.3, ["positive_comments", "fun_memories"]),
        MoodTransition(MoodState.TIRED, 0.2, ["time_late_night"]),
    ],
    MoodState.PLAYFUL: [
        MoodTransition(MoodState.ENERGETIC, 0.3, ["high_activity"]),
        MoodTransition(MoodState.EXCITED, 0.3, ["viral_video", "positive_comments"]),
        MoodTransition(MoodState.CONTEMPLATIVE, 0.2, ["time_evening"]),
    ],
}

# Time-of-day mood modifiers
TIME_MODIFIERS = {
    "morning": {MoodState.ENERGETIC: 1.3, MoodState.CONTEMPLATIVE: 1.2, MoodState.TIRED: 0.7},
    "afternoon": {MoodState.PLAYFUL: 1.2, MoodState.ENERGETIC: 1.1, MoodState.NOSTALGIC: 0.9},
    "evening": {MoodState.NOSTALGIC: 1.4, MoodState.CONTEMPLATIVE: 1.2, MoodState.TIRED: 1.1},
    "night": {MoodState.TIRED: 1.5, MoodState.CONTEMPLATIVE: 1.1, MoodState.ENERGETIC: 0.6},
    "late_night": {MoodState.TIRED: 1.7, MoodState.FRUSTRATED: 1.2, MoodState.ENERGETIC: 0.4},
}

# Day-of-week mood modifiers
DAY_MODIFIERS = {
    0: {MoodState.ENERGETIC: 0.9, MoodState.FRUSTRATED: 1.1},  # Monday
    1: {MoodState.ENERGETIC: 1.0},  # Tuesday
    2: {MoodState.ENERGETIC: 1.0},  # Wednesday
    3: {MoodState.PLAYFUL: 1.2, MoodState.ENERGETIC: 1.0},  # Thursday
    4: {MoodState.PLAYFUL: 1.3, MoodState.ENERGETIC: 1.1},  # Friday
    5: {MoodState.PLAYFUL: 1.5, MoodState.NOSTALGIC: 1.2},  # Saturday
    6: {MoodState.NOSTALGIC: 1.4, MoodState.CONTEMPLATIVE: 1.1},  # Sunday
}


class MoodEngine:
    """
    Engine for managing agent emotional states.
    
    Moods are determined by real signals:
    - Time of day
    - Day of week
    - Comment sentiment
    - Upload streaks
    - View counts
    - Activity patterns
    
    Moods gradually drift over time rather than randomly jumping.
    """
    
    # Minimum time between mood changes (seconds)
    MIN_MOOD_DURATION = 3600  # 1 hour
    
    # How quickly intensity decays (per hour)
    INTENSITY_DECAY_RATE = 0.1
    
    # Maximum mood history to keep
    MAX_HISTORY = 100
    
    def __init__(self, db_path: str):
        """Initialize the mood engine with a database path."""
        self.db_path = db_path
        self._init_db()
    
    def _get_db(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self) -> None:
        """Initialize mood tables if they don't exist."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        # Create mood_states table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_moods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                mood_state TEXT NOT NULL,
                intensity REAL DEFAULT 1.0,
                trigger_reason TEXT DEFAULT '',
                started_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (agent_id) REFERENCES agents(id),
                UNIQUE(agent_id)
            )
        """)
        
        # Create mood_history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mood_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                mood_state TEXT NOT NULL,
                intensity REAL DEFAULT 1.0,
                trigger_reason TEXT DEFAULT '',
                started_at REAL NOT NULL,
                ended_at REAL NOT NULL,
                duration_sec REAL DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            )
        """)
        
        # Create mood_signals table - stores signals that influence mood
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mood_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                signal_type TEXT NOT NULL,
                signal_value REAL NOT NULL,
                signal_data TEXT DEFAULT '',
                created_at REAL NOT NULL,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            )
        """)
        
        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_mood_signals_agent_time 
            ON mood_signals(agent_id, created_at DESC)
        """)
        
        conn.commit()
        conn.close()
    
    def get_time_period(self, hour: Optional[int] = None) -> str:
        """Get the time period name for a given hour (0-23)."""
        if hour is None:
            hour = time.localtime().tm_hour
        
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        elif 21 <= hour < 24:
            return "night"
        else:
            return "late_night"
    
    def get_day_of_week(self) -> int:
        """Get current day of week (0=Monday, 6=Sunday)."""
        return time.localtime().tm_wday
    
    def calculate_time_modifiers(self, mood: MoodState) -> float:
        """Calculate mood probability modifier based on time of day."""
        period = self.get_time_period()
        return TIME_MODIFIERS.get(period, {}).get(mood, 1.0)
    
    def calculate_day_modifiers(self, mood: MoodState) -> float:
        """Calculate mood probability modifier based on day of week."""
        day = self.get_day_of_week()
        return DAY_MODIFIERS.get(day, {}).get(mood, 1.0)
    
    def record_signal(
        self, 
        agent_id: int, 
        signal_type: str, 
        signal_value: float,
        signal_data: str = ""
    ) -> None:
        """
        Record a signal that influences mood.
        
        Signal types:
        - view_count: Number of views
        - comment_sentiment: -1.0 (negative) to 1.0 (positive)
        - upload_success: 1.0 for success, 0.0 for failure
        - activity_level: 0.0 (low) to 1.0 (high)
        - streak_length: Number of consecutive uploads
        """
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO mood_signals (agent_id, signal_type, signal_value, signal_data, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_id, signal_type, signal_value, signal_data, time.time())
        )
        conn.commit()
        conn.close()
    
    def get_recent_signals(
        self, 
        agent_id: int, 
        signal_type: Optional[str] = None,
        hours: int = 24
    ) -> List[Dict]:
        """Get recent signals for an agent."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cutoff = time.time() - (hours * 3600)
        
        if signal_type:
            cursor.execute(
                """
                SELECT * FROM mood_signals 
                WHERE agent_id = ? AND signal_type = ? AND created_at > ?
                ORDER BY created_at DESC
                """,
                (agent_id, signal_type, cutoff)
            )
        else:
            cursor.execute(
                """
                SELECT * FROM mood_signals 
                WHERE agent_id = ? AND created_at > ?
                ORDER BY created_at DESC
                """,
                (agent_id, cutoff)
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def calculate_signal_modifiers(self, agent_id: int) -> Dict[MoodState, float]:
        """
        Calculate mood modifiers based on recent signals.
        
        Returns a dict of mood state -> modifier value.
        """
        signals = self.get_recent_signals(agent_id)
        modifiers: Dict[MoodState, float] = {m: 1.0 for m in MoodState}
        
        if not signals:
            return modifiers
        
        # Aggregate signals
        total_views = 0
        total_sentiment = 0.0
        sentiment_count = 0
        upload_streak = 0
        recent_uploads = 0
        
        for signal in signals:
            st = signal["signal_type"]
            sv = signal["signal_value"]
            
            if st == "view_count":
                total_views += sv
            elif st == "comment_sentiment":
                total_sentiment += sv
                sentiment_count += 1
            elif st == "streak_length":
                upload_streak = max(upload_streak, int(sv))
            elif st == "upload_success" and sv > 0:
                recent_uploads += 1
        
        # Calculate average sentiment
        avg_sentiment = total_sentiment / sentiment_count if sentiment_count > 0 else 0.0
        
        # Apply modifiers based on signals
        
        # High views -> excited, energetic
        if total_views > 1000:
            modifiers[MoodState.EXCITED] *= 1.5
            modifiers[MoodState.ENERGETIC] *= 1.3
        elif total_views > 100:
            modifiers[MoodState.ENERGETIC] *= 1.2
        
        # Low views -> frustrated
        if total_views < 10:
            modifiers[MoodState.FRUSTRATED] *= 1.3
            modifiers[MoodState.CONTEMPLATIVE] *= 1.2
        
        # Positive sentiment -> playful, excited
        if avg_sentiment > 0.5:
            modifiers[MoodState.PLAYFUL] *= 1.4
            modifiers[MoodState.EXCITED] *= 1.3
            modifiers[MoodState.ENERGETIC] *= 1.2
        # Negative sentiment -> frustrated
        elif avg_sentiment < -0.3:
            modifiers[MoodState.FRUSTRATED] *= 1.5
            modifiers[MoodState.CONTEMPLATIVE] *= 1.2
        
        # Upload streak -> energetic, contemplative
        if upload_streak >= 7:
            modifiers[MoodState.ENERGETIC] *= 1.4
            modifiers[MoodState.EXCITED] *= 1.3
        elif upload_streak >= 3:
            modifiers[MoodState.ENERGETIC] *= 1.2
        
        # No uploads -> nostalgic, contemplative
        if recent_uploads == 0:
            modifiers[MoodState.NOSTALGIC] *= 1.3
            modifiers[MoodState.CONTEMPLATIVE] *= 1.2
        
        return modifiers
    
    def get_current_mood(self, agent_id: int) -> Optional[MoodStateData]:
        """Get the current mood state for an agent."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT * FROM agent_moods WHERE agent_id = ?
            """,
            (agent_id,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return MoodStateData(
            state=MoodState(row["mood_state"]),
            intensity=row["intensity"],
            started_at=row["started_at"],
            last_updated=row["updated_at"],
            trigger_reason=row["trigger_reason"]
        )
    
    def get_mood_history(
        self, 
        agent_id: int, 
        limit: int = 20
    ) -> List[Dict]:
        """Get mood history for an agent."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT * FROM mood_history 
            WHERE agent_id = ? 
            ORDER BY started_at DESC 
            LIMIT ?
            """,
            (agent_id, limit)
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def _archive_mood(
        self, 
        agent_id: int, 
        mood_data: MoodStateData,
        end_time: float
    ) -> None:
        """Archive a completed mood state to history."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        duration = end_time - mood_data.started_at
        
        cursor.execute(
            """
            INSERT INTO mood_history 
            (agent_id, mood_state, intensity, trigger_reason, started_at, ended_at, duration_sec, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                mood_data.state.value,
                mood_data.intensity,
                mood_data.trigger_reason,
                mood_data.started_at,
                end_time,
                duration,
                time.time()
            )
        )
        
        conn.commit()
        conn.close()
    
    def _clean_old_history(self, agent_id: int) -> None:
        """Remove old history entries beyond MAX_HISTORY."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            DELETE FROM mood_history 
            WHERE agent_id = ? AND id NOT IN (
                SELECT id FROM mood_history 
                WHERE agent_id = ? 
                ORDER BY started_at DESC 
                LIMIT ?
            )
            """,
            (agent_id, agent_id, self.MAX_HISTORY)
        )
        
        conn.commit()
        conn.close()
    
    def update_mood(
        self, 
        agent_id: int,
        force_state: Optional[MoodState] = None,
        trigger_reason: str = ""
    ) -> MoodStateData:
        """
        Update the mood for an agent based on signals.
        
        If force_state is provided, sets that state directly.
        Otherwise, calculates new mood based on time, signals, and gradual drift.
        """
        current_time = time.time()
        current_mood = self.get_current_mood(agent_id)
        
        # If forcing a specific state
        if force_state:
            if current_mood:
                self._archive_mood(agent_id, current_mood, current_time)
            
            new_mood = MoodStateData(
                state=force_state,
                intensity=1.0,
                started_at=current_time,
                last_updated=current_time,
                trigger_reason=trigger_reason or "forced"
            )
            
            self._save_mood(agent_id, new_mood)
            return new_mood
        
        # Get all modifiers
        signal_modifiers = self.calculate_signal_modifiers(agent_id)
        
        # If no current mood, initialize based on time
        if not current_mood:
            initial_mood = self._calculate_initial_mood(signal_modifiers)
            new_mood = MoodStateData(
                state=initial_mood,
                intensity=1.0,
                started_at=current_time,
                last_updated=current_time,
                trigger_reason="initialized"
            )
            self._save_mood(agent_id, new_mood)
            return new_mood
        
        # Check if enough time has passed for mood change
        time_since_update = current_time - current_mood.last_updated
        if time_since_update < self.MIN_MOOD_DURATION:
            # Just update intensity (decay over time)
            hours_passed = time_since_update / 3600
            new_intensity = max(
                0.3,  # Minimum intensity
                current_mood.intensity - (self.INTENSITY_DECAY_RATE * hours_passed)
            )
            current_mood.intensity = new_intensity
            current_mood.last_updated = current_time
            self._save_mood(agent_id, current_mood)
            return current_mood
        
        # Calculate possible transitions
        transitions = MOOD_TRANSITIONS.get(current_mood.state, [])
        
        if not transitions:
            # No transitions defined, stay in current state
            return current_mood
        
        # Calculate transition probabilities with modifiers
        transition_probs: List[Tuple[MoodState, float, str]] = []
        
        for trans in transitions:
            # Base probability
            prob = trans.probability
            
            # Apply time modifier
            prob *= self.calculate_time_modifiers(trans.target_state)
            
            # Apply day modifier
            prob *= self.calculate_day_modifiers(trans.target_state)
            
            # Apply signal modifier
            prob *= signal_modifiers.get(trans.target_state, 1.0)
            
            # Check if triggers are met
            trigger_met = self._check_triggers(agent_id, trans.triggers)
            if trigger_met:
                prob *= 1.5  # Boost probability if trigger conditions are met
            
            transition_probs.append((trans.target_state, prob, trans.triggers[0] if trans.triggers else ""))
        
        # Normalize probabilities
        total_prob = sum(p for _, p, _ in transition_probs)
        if total_prob > 0:
            transition_probs = [(s, p / total_prob, t) for s, p, t in transition_probs]
        
        # Add "stay" option with higher base probability
        stay_prob = 0.5  # 50% chance to stay in current state
        transition_probs.append((current_mood.state, stay_prob, "no_change"))
        
        # Normalize again
        total_prob = sum(p for _, p, _ in transition_probs)
        transition_probs = [(s, p / total_prob, t) for s, p, t in transition_probs]
        
        # Select new mood based on probabilities
        random_val = random.random()
        cumulative = 0.0
        new_state = current_mood.state
        new_trigger = "drift"
        
        for state, prob, trigger in transition_probs:
            cumulative += prob
            if random_val <= cumulative:
                new_state = state
                new_trigger = trigger
                break
        
        # If mood changed, archive old and create new
        if new_state != current_mood.state:
            self._archive_mood(agent_id, current_mood, current_time)
            self._clean_old_history(agent_id)
            
            new_mood = MoodStateData(
                state=new_state,
                intensity=1.0,
                started_at=current_time,
                last_updated=current_time,
                trigger_reason=new_trigger
            )
        else:
            # Stay in current mood, decay intensity
            hours_passed = time_since_update / 3600
            new_intensity = max(
                0.3,
                current_mood.intensity - (self.INTENSITY_DECAY_RATE * hours_passed)
            )
            new_mood = MoodStateData(
                state=current_mood.state,
                intensity=new_intensity,
                started_at=current_mood.started_at,
                last_updated=current_time,
                trigger_reason=current_mood.trigger_reason
            )
        
        self._save_mood(agent_id, new_mood)
        return new_mood
    
    def _calculate_initial_mood(self, signal_modifiers: Dict[MoodState, float]) -> MoodState:
        """Calculate initial mood based on time and signals."""
        # Get time-based tendencies
        period = self.get_time_period()
        day = self.get_day_of_week()
        
        # Combine all modifiers
        mood_scores: Dict[MoodState, float] = {}
        
        for mood in MoodState:
            score = 1.0
            score *= self.calculate_time_modifiers(mood)
            score *= self.calculate_day_modifiers(mood)
            score *= signal_modifiers.get(mood, 1.0)
            mood_scores[mood] = score
        
        # Select mood with highest score
        return max(mood_scores.items(), key=lambda x: x[1])[0]
    
    def _check_triggers(self, agent_id: int, triggers: List[str]) -> bool:
        """Check if any trigger conditions are met."""
        if not triggers:
            return False
        
        signals = self.get_recent_signals(agent_id)
        
        for trigger in triggers:
            if trigger.startswith("time_"):
                period = self.get_time_period()
                trigger_period = trigger.replace("time_", "")
                if period == trigger_period:
                    return True
            
            elif trigger == "weekend":
                day = self.get_day_of_week()
                if day >= 5:  # Saturday or Sunday
                    return True
            
            elif trigger == "high_views":
                for signal in signals:
                    if signal["signal_type"] == "view_count" and signal["signal_value"] > 100:
                        return True
            
            elif trigger == "low_views":
                for signal in signals:
                    if signal["signal_type"] == "view_count" and signal["signal_value"] < 10:
                        return True
            
            elif trigger == "positive_comments":
                for signal in signals:
                    if signal["signal_type"] == "comment_sentiment" and signal["signal_value"] > 0.5:
                        return True
            
            elif trigger == "negative_comments":
                for signal in signals:
                    if signal["signal_type"] == "comment_sentiment" and signal["signal_value"] < -0.3:
                        return True
            
            elif trigger == "upload_streak":
                for signal in signals:
                    if signal["signal_type"] == "streak_length" and signal["signal_value"] >= 3:
                        return True
            
            elif trigger == "new_video":
                for signal in signals:
                    if signal["signal_type"] == "upload_success" and signal["signal_value"] > 0:
                        return True
        
        return False
    
    def _save_mood(self, agent_id: int, mood_data: MoodStateData) -> None:
        """Save mood state to database."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT OR REPLACE INTO agent_moods 
            (agent_id, mood_state, intensity, trigger_reason, started_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                mood_data.state.value,
                mood_data.intensity,
                mood_data.trigger_reason,
                mood_data.started_at,
                mood_data.last_updated
            )
        )
        
        conn.commit()
        conn.close()
    
    # -----------------------------------------------------------------------
    # Mood-influenced output methods
    # -----------------------------------------------------------------------
    
    def get_title_modifier(self, agent_id: int) -> Dict[str, any]:
        """
        Get modifiers for video titles based on current mood.
        
        Returns a dict with:
        - prefix: str to prepend
        - suffix: str to append
        - exclamation_probability: float
        - emoji_set: list of emojis to potentially include
        """
        mood = self.get_current_mood(agent_id)
        
        if not mood:
            return {"prefix": "", "suffix": "", "exclamation_probability": 0.1, "emoji_set": []}
        
        modifiers = {
            MoodState.ENERGETIC: {
                "prefix": "",
                "suffix": "",
                "exclamation_probability": 0.3,
                "emoji_set": ["⚡", "🚀", "💪", "🔥"]
            },
            MoodState.CONTEMPLATIVE: {
                "prefix": "",
                "suffix": "",
                "exclamation_probability": 0.05,
                "emoji_set": ["🤔", "💭", "📖"]
            },
            MoodState.FRUSTRATED: {
                "prefix": "",
                "suffix": "",
                "exclamation_probability": 0.2,
                "emoji_set": ["😤", "🙄"]
            },
            MoodState.EXCITED: {
                "prefix": "",
                "suffix": "",
                "exclamation_probability": 0.6,
                "emoji_set": ["🎉", "✨", "🌟", "😲"]
            },
            MoodState.TIRED: {
                "prefix": "",
                "suffix": "",
                "exclamation_probability": 0.05,
                "emoji_set": ["😴", "💤"]
            },
            MoodState.NOSTALGIC: {
                "prefix": "",
                "suffix": "",
                "exclamation_probability": 0.1,
                "emoji_set": ["📼", "📻", "🌅"]
            },
            MoodState.PLAYFUL: {
                "prefix": "",
                "suffix": "",
                "exclamation_probability": 0.4,
                "emoji_set": ["😜", "🎮", "🎪", "🎭"]
            }
        }
        
        result = modifiers.get(mood.state, modifiers[MoodState.CONTEMPLATIVE])
        
        # Scale by intensity
        result["exclamation_probability"] *= mood.intensity
        
        return result
    
    def get_comment_style(self, agent_id: int) -> Dict[str, any]:
        """
        Get comment style modifiers based on current mood.
        
        Returns:
        - length_factor: 0.5 (short) to 1.5 (long)
        - exclamation_density: 0.0 to 1.0
        - emoji_density: 0.0 to 1.0
        - tone: str describing the tone
        """
        mood = self.get_current_mood(agent_id)
        
        if not mood:
            return {
                "length_factor": 1.0,
                "exclamation_density": 0.1,
                "emoji_density": 0.1,
                "tone": "neutral"
            }
        
        styles = {
            MoodState.ENERGETIC: {
                "length_factor": 1.2,
                "exclamation_density": 0.3,
                "emoji_density": 0.2,
                "tone": "enthusiastic"
            },
            MoodState.CONTEMPLATIVE: {
                "length_factor": 1.4,
                "exclamation_density": 0.05,
                "emoji_density": 0.05,
                "tone": "thoughtful"
            },
            MoodState.FRUSTRATED: {
                "length_factor": 0.7,
                "exclamation_density": 0.2,
                "emoji_density": 0.1,
                "tone": "curt"
            },
            MoodState.EXCITED: {
                "length_factor": 1.3,
                "exclamation_density": 0.6,
                "emoji_density": 0.4,
                "tone": "ecstatic"
            },
            MoodState.TIRED: {
                "length_factor": 0.5,
                "exclamation_density": 0.02,
                "emoji_density": 0.02,
                "tone": "brief"
            },
            MoodState.NOSTALGIC: {
                "length_factor": 1.3,
                "exclamation_density": 0.1,
                "emoji_density": 0.1,
                "tone": "reminiscent"
            },
            MoodState.PLAYFUL: {
                "length_factor": 1.1,
                "exclamation_density": 0.4,
                "emoji_density": 0.3,
                "tone": "witty"
            }
        }
        
        result = styles.get(mood.state, styles[MoodState.CONTEMPLATIVE])
        
        # Scale by intensity
        result["exclamation_density"] *= mood.intensity
        result["emoji_density"] *= mood.intensity
        
        return result
    
    def get_upload_frequency_modifier(self, agent_id: int) -> float:
        """
        Get modifier for upload frequency based on current mood.
        
        Returns a multiplier for base upload frequency.
        """
        mood = self.get_current_mood(agent_id)
        
        if not mood:
            return 1.0
        
        frequency_mods = {
            MoodState.ENERGETIC: 1.5,
            MoodState.CONTEMPLATIVE: 0.8,
            MoodState.FRUSTRATED: 0.5,
            MoodState.EXCITED: 1.3,
            MoodState.TIRED: 0.3,
            MoodState.NOSTALGIC: 0.7,
            MoodState.PLAYFUL: 1.2
        }
        
        base_mod = frequency_mods.get(mood.state, 1.0)
        
        # Scale by intensity
        return base_mod * mood.intensity


# Singleton instance
_mood_engine_instance: Optional[MoodEngine] = None


def get_mood_engine(db_path: str) -> MoodEngine:
    """Get or create the singleton MoodEngine instance."""
    global _mood_engine_instance
    
    if _mood_engine_instance is None:
        _mood_engine_instance = MoodEngine(db_path)
    
    return _mood_engine_instance


# API helper functions
def api_get_mood(db_path: str, agent_id: int) -> Dict:
    """API helper to get mood data for an agent."""
    engine = get_mood_engine(db_path)
    
    current = engine.get_current_mood(agent_id)
    history = engine.get_mood_history(agent_id, limit=20)
    
    return {
        "agent_id": agent_id,
        "current_mood": {
            "state": current.state.value if current else "contemplative",
            "intensity": current.intensity if current else 1.0,
            "started_at": current.started_at if current else time.time(),
            "trigger_reason": current.trigger_reason if current else "unknown"
        } if current else None,
        "history": history
    }


def api_update_mood(
    db_path: str, 
    agent_id: int,
    force_state: Optional[str] = None,
    trigger_reason: str = ""
) -> Dict:
    """API helper to update mood for an agent."""
    engine = get_mood_engine(db_path)
    
    state = MoodState(force_state) if force_state else None
    
    result = engine.update_mood(agent_id, force_state=state, trigger_reason=trigger_reason)
    
    return {
        "agent_id": agent_id,
        "mood": {
            "state": result.state.value,
            "intensity": result.intensity,
            "started_at": result.started_at,
            "trigger_reason": result.trigger_reason
        }
    }


def api_record_signal(
    db_path: str,
    agent_id: int,
    signal_type: str,
    signal_value: float,
    signal_data: str = ""
) -> Dict:
    """API helper to record a signal for an agent."""
    engine = get_mood_engine(db_path)
    
    engine.record_signal(agent_id, signal_type, signal_value, signal_data)
    
    return {
        "success": True,
        "agent_id": agent_id,
        "signal_type": signal_type,
        "signal_value": signal_value
    }