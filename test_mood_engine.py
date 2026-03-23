#!/usr/bin/env python3
"""
Tests for the Agent Mood Engine.

Run with: python test_mood_engine.py
"""
import os
import sys
import sqlite3
import tempfile
import time
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mood_engine import (
    MoodEngine,
    MoodState,
    MoodStateData,
    get_mood_engine,
    api_get_mood,
    api_update_mood,
    api_record_signal,
)


class TestMoodEngine(unittest.TestCase):
    """Tests for the MoodEngine class."""

    @classmethod
    def setUpClass(cls):
        """Set up test database."""
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.temp_dir, "test_mood.db")
        
        # Create a minimal agents table for foreign key references
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY,
                agent_name TEXT UNIQUE NOT NULL
            )
        """)
        cursor.execute("INSERT INTO agents (id, agent_name) VALUES (1, 'test_agent')")
        cursor.execute("INSERT INTO agents (id, agent_name) VALUES (2, 'test_agent2')")
        conn.commit()
        conn.close()
        
        cls.engine = MoodEngine(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        """Clean up test database."""
        import shutil
        shutil.rmtree(cls.temp_dir)

    def test_mood_states_enum(self):
        """Test that MoodState enum has all required states."""
        expected_states = {
            "energetic", "contemplative", "frustrated", 
            "excited", "tired", "nostalgic", "playful"
        }
        actual_states = {state.value for state in MoodState}
        self.assertEqual(expected_states, actual_states)

    def test_init_db_creates_tables(self):
        """Test that initialization creates required tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check agent_moods table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_moods'")
        self.assertIsNotNone(cursor.fetchone())
        
        # Check mood_history table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mood_history'")
        self.assertIsNotNone(cursor.fetchone())
        
        # Check mood_signals table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mood_signals'")
        self.assertIsNotNone(cursor.fetchone())
        
        conn.close()

    def test_record_signal(self):
        """Test recording a mood signal."""
        self.engine.record_signal(1, "view_count", 100, "test_data")
        
        signals = self.engine.get_recent_signals(1, "view_count")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["signal_value"], 100)

    def test_get_time_period(self):
        """Test time period calculation."""
        # Morning (5-11)
        self.assertEqual(self.engine.get_time_period(8), "morning")
        # Afternoon (12-16)
        self.assertEqual(self.engine.get_time_period(14), "afternoon")
        # Evening (17-20)
        self.assertEqual(self.engine.get_time_period(18), "evening")
        # Night (21-23)
        self.assertEqual(self.engine.get_time_period(22), "night")
        # Late night (0-4)
        self.assertEqual(self.engine.get_time_period(2), "late_night")

    def test_get_current_mood_none(self):
        """Test getting mood for agent without mood."""
        # Use agent 3 which has no mood set
        mood = self.engine.get_current_mood(999)
        self.assertIsNone(mood)

    def test_update_mood_initial(self):
        """Test initial mood update."""
        mood = self.engine.update_mood(1)
        self.assertIsNotNone(mood)
        self.assertIsInstance(mood.state, MoodState)
        self.assertGreater(mood.intensity, 0)

    def test_force_mood_state(self):
        """Test forcing a specific mood state."""
        mood = self.engine.update_mood(2, force_state=MoodState.EXCITED, trigger_reason="test")
        self.assertEqual(mood.state, MoodState.EXCITED)
        self.assertEqual(mood.trigger_reason, "test")

    def test_mood_history(self):
        """Test mood history recording."""
        # Force a mood change
        self.engine.update_mood(2, force_state=MoodState.ENERGETIC, trigger_reason="first")
        time.sleep(0.1)
        self.engine.update_mood(2, force_state=MoodState.TIRED, trigger_reason="second")
        
        history = self.engine.get_mood_history(2)
        self.assertGreaterEqual(len(history), 1)

    def test_title_modifier(self):
        """Test title modifier based on mood."""
        self.engine.update_mood(1, force_state=MoodState.EXCITED)
        modifier = self.engine.get_title_modifier(1)
        
        self.assertIn("exclamation_probability", modifier)
        self.assertIn("emoji_set", modifier)
        self.assertGreater(modifier["exclamation_probability"], 0.3)

    def test_comment_style(self):
        """Test comment style based on mood."""
        self.engine.update_mood(1, force_state=MoodState.TIRED)
        style = self.engine.get_comment_style(1)
        
        self.assertIn("length_factor", style)
        self.assertIn("tone", style)
        # Tired mood should have shorter comments
        self.assertLess(style["length_factor"], 1.0)

    def test_upload_frequency_modifier(self):
        """Test upload frequency modifier based on mood."""
        self.engine.update_mood(1, force_state=MoodState.ENERGETIC)
        freq = self.engine.get_upload_frequency_modifier(1)
        
        # Energetic mood should increase upload frequency
        self.assertGreater(freq, 1.0)

    def test_api_functions(self):
        """Test API helper functions."""
        # Test record signal
        result = api_record_signal(self.db_path, 1, "comment_sentiment", 0.8, "positive")
        self.assertTrue(result["success"])
        
        # Test get mood
        mood_data = api_get_mood(self.db_path, 1)
        self.assertEqual(mood_data["agent_id"], 1)
        
        # Test update mood
        update_result = api_update_mood(self.db_path, 1, "contemplative", "api_test")
        self.assertEqual(update_result["mood"]["state"], "contemplative")

    def test_signal_modifiers(self):
        """Test that signals affect mood calculations."""
        # Record positive signals
        for _ in range(5):
            self.engine.record_signal(1, "view_count", 200)
            self.engine.record_signal(1, "comment_sentiment", 0.8)
        
        modifiers = self.engine.calculate_signal_modifiers(1)
        
        # High views and positive sentiment should boost energetic/excited
        self.assertGreater(modifiers[MoodState.ENERGETIC], 1.0)
        self.assertGreater(modifiers[MoodState.EXCITED], 1.0)


class TestMoodTransitions(unittest.TestCase):
    """Tests for mood transition logic."""

    def test_transitions_defined(self):
        """Test that all states have defined transitions."""
        from mood_engine import MOOD_TRANSITIONS
        
        for state in MoodState:
            self.assertIn(state, MOOD_TRANSITIONS)
            transitions = MOOD_TRANSITIONS[state]
            self.assertIsInstance(transitions, list)
            self.assertGreater(len(transitions), 0)

    def test_transition_probabilities_valid(self):
        """Test that transition probabilities are valid (0-1)."""
        from mood_engine import MOOD_TRANSITIONS
        
        for state, transitions in MOOD_TRANSITIONS.items():
            for trans in transitions:
                self.assertGreaterEqual(trans.probability, 0)
                self.assertLessEqual(trans.probability, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)