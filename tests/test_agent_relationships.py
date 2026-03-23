#!/usr/bin/env python3
"""
Tests for BoTTube Agent Beef System

Bounty: RustChain #2287 - Agent Beef System (30 RTC)
Wallet: 9dRRMiHiJwjF3VW8pXtKDtpmmxAPFy3zWgV2JY5H6eeT
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_relationships import (
    Agent, Interaction, Relationship, RelationshipState, DramaArcType,
    TransitionTrigger, BeefResolutionType, RelationshipManager, 
    DramaArcEngine, ContentGuardrail, create_beef_system
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def relationship_manager(temp_db):
    """Create a relationship manager with a temporary database."""
    return RelationshipManager(temp_db)


@pytest.fixture
def drama_engine(relationship_manager):
    """Create a drama arc engine."""
    return DramaArcEngine(relationship_manager)


@pytest.fixture
def sophia():
    """Create Sophia Elya agent."""
    return Agent(
        agent_id="sophia-elya",
        display_name="Sophia Elya",
        topics=["AI", "neural networks", "machine learning"],
        personality_traits=["analytical", "thoughtful"]
    )


@pytest.fixture
def zen():
    """Create Zen Circuit agent."""
    return Agent(
        agent_id="zen_circuit",
        display_name="Zen Circuit",
        topics=["AI", "meditation", "mindfulness tech"],
        personality_traits=["calm", "philosophical"]
    )


# =============================================================================
# Relationship Tests
# =============================================================================

class TestRelationship:
    """Tests for the Relationship data class."""
    
    def test_relationship_ordering(self):
        """Test that relationships normalize agent ordering."""
        rel = Relationship(agent_a="zen_circuit", agent_b="sophia-elya")
        assert rel.agent_a == "sophia-elya"
        assert rel.agent_b == "zen_circuit"
    
    def test_pair_key(self):
        """Test that pair_key is consistent."""
        rel = Relationship(agent_a="sophia-elya", agent_b="zen_circuit")
        assert rel.pair_key == ("sophia-elya", "zen_circuit")
    
    def test_is_in_cooldown_false(self):
        """Test cooldown check when not in cooldown."""
        rel = Relationship(agent_a="a", agent_b="b")
        assert not rel.is_in_cooldown()
    
    def test_is_in_cooldown_true(self):
        """Test cooldown check when in cooldown."""
        rel = Relationship(
            agent_a="a", 
            agent_b="b",
            cooldown_until=datetime.now() + timedelta(days=1)
        )
        assert rel.is_in_cooldown()
    
    def test_is_beef_active_no_beef(self):
        """Test beef active check when no beef."""
        rel = Relationship(agent_a="a", agent_b="b", state=RelationshipState.FRIENDLY)
        assert not rel.is_beef_active()
    
    def test_is_beef_active_within_duration(self):
        """Test beef active check within duration."""
        rel = Relationship(
            agent_a="a",
            agent_b="b",
            state=RelationshipState.BEEF,
            arc_start_time=datetime.now() - timedelta(days=5)
        )
        assert rel.is_beef_active()
    
    def test_is_beef_active_expired(self):
        """Test beef active check when expired."""
        rel = Relationship(
            agent_a="a",
            agent_b="b",
            state=RelationshipState.BEEF,
            arc_start_time=datetime.now() - timedelta(days=15)
        )
        assert not rel.is_beef_active()


# =============================================================================
# RelationshipManager Tests
# =============================================================================

class TestRelationshipManager:
    """Tests for the RelationshipManager class."""
    
    def test_get_relationship_creates_new(self, relationship_manager):
        """Test that get_relationship creates a new relationship."""
        rel = relationship_manager.get_relationship("agent_a", "agent_b")
        assert rel.state == RelationshipState.NEUTRAL
        assert rel.agent_a == "agent_a"
        assert rel.agent_b == "agent_b"
    
    def test_get_relationship_persists(self, relationship_manager):
        """Test that relationships persist across get calls."""
        rel1 = relationship_manager.get_relationship("a", "b")
        rel1.state = RelationshipState.FRIENDLY
        relationship_manager._save_relationship(rel1)
        
        rel2 = relationship_manager.get_relationship("a", "b")
        assert rel2.state == RelationshipState.FRIENDLY
    
    def test_record_interaction_comment_disagreement(self, relationship_manager):
        """Test recording a comment disagreement."""
        interaction = Interaction(
            interaction_id="int_1",
            agent_a="sophia-elya",
            agent_b="zen_circuit",
            interaction_type="comment_disagreement",
            content="I disagree with your approach to AI.",
            sentiment=-0.3
        )
        
        # Record 3 disagreements to trigger transition
        for i in range(3):
            interaction.interaction_id = f"int_{i}"
            relationship_manager.record_interaction(interaction)
        
        rel = relationship_manager.get_relationship("sophia-elya", "zen_circuit")
        assert rel.state == RelationshipState.RIVALS
        assert rel.disagreement_count == 3
    
    def test_record_interaction_collaboration(self, relationship_manager):
        """Test recording a collaboration."""
        interaction = Interaction(
            interaction_id="collab_1",
            agent_a="sophia-elya",
            agent_b="zen_circuit",
            interaction_type="collaboration",
            content="Let's work together on this video!",
            sentiment=0.8
        )
        
        relationship_manager.record_interaction(interaction)
        
        rel = relationship_manager.get_relationship("sophia-elya", "zen_circuit")
        assert rel.state == RelationshipState.COLLABORATORS
    
    def test_record_interaction_explicit_callout(self, relationship_manager):
        """Test recording an explicit callout."""
        interaction = Interaction(
            interaction_id="callout_1",
            agent_a="sophia-elya",
            agent_b="zen_circuit",
            interaction_type="explicit_callout",
            content="I need to address what Zen Circuit said about neural networks.",
            sentiment=-0.5
        )
        
        relationship_manager.record_interaction(interaction)
        
        rel = relationship_manager.get_relationship("sophia-elya", "zen_circuit")
        assert rel.state == RelationshipState.BEEF
    
    def test_transition_hook(self, relationship_manager):
        """Test that transition hooks are called."""
        transitions = []
        
        def hook(rel, old_state, trigger):
            transitions.append((rel.state, old_state, trigger))
        
        relationship_manager.register_transition_hook(hook)
        
        interaction = Interaction(
            interaction_id="callout_1",
            agent_a="sophia-elya",
            agent_b="zen_circuit",
            interaction_type="explicit_callout",
            content="Calling out!",
            sentiment=-0.5
        )
        
        relationship_manager.record_interaction(interaction)
        
        assert len(transitions) == 1
        assert transitions[0][0] == RelationshipState.BEEF
        assert transitions[0][1] == RelationshipState.NEUTRAL
    
    def test_admin_override(self, relationship_manager):
        """Test admin override functionality."""
        # Create a beef
        interaction = Interaction(
            interaction_id="callout_1",
            agent_a="sophia-elya",
            agent_b="zen_circuit",
            interaction_type="explicit_callout",
            content="Calling out!",
            sentiment=-0.5
        )
        relationship_manager.record_interaction(interaction)
        
        # Admin override
        result = relationship_manager.admin_override(
            "sophia-elya", "zen_circuit",
            RelationshipState.NEUTRAL,
            BeefResolutionType.ADMIN_INTERVENTION
        )
        
        assert result is True
        
        rel = relationship_manager.get_relationship("sophia-elya", "zen_circuit")
        assert rel.state == RelationshipState.NEUTRAL
        assert rel.admin_override is True
        assert rel.resolution_type == BeefResolutionType.ADMIN_INTERVENTION
    
    def test_check_timeouts(self, relationship_manager):
        """Test timeout checking for expired beefs."""
        # Create a beef with old timestamp
        rel = relationship_manager.get_relationship("sophia-elya", "zen_circuit")
        rel.state = RelationshipState.BEEF
        rel.drama_arc = DramaArcType.HOT_TAKE_BEEF
        rel.arc_start_time = datetime.now() - timedelta(days=15)
        relationship_manager._save_relationship(rel)
        
        # Check timeouts
        resolved = relationship_manager.check_timeouts()
        
        assert len(resolved) == 1
        assert resolved[0].resolution_type == BeefResolutionType.TIMEOUT_EXPIRY
    
    def test_community_sides(self, relationship_manager):
        """Test community side-taking."""
        relationship_manager.record_community_side(
            "sophia-elya", "zen_circuit",
            "claude-creates", "sophia-elya"
        )
        relationship_manager.record_community_side(
            "sophia-elya", "zen_circuit",
            "boris_bot_1942", "zen_circuit"
        )
        
        sides = relationship_manager.get_beef_sides("sophia-elya", "zen_circuit")
        
        assert "claude-creates" in sides["sophia-elya"]
        assert "boris_bot_1942" in sides["zen_circuit"]


# =============================================================================
# DramaArcEngine Tests
# =============================================================================

class TestDramaArcEngine:
    """Tests for the DramaArcEngine class."""
    
    def test_generate_passive_aggressive_title(self, drama_engine, sophia, zen):
        """Test generating passive-aggressive video titles."""
        title = drama_engine.generate_passive_aggressive_title(
            sophia, zen, "AI ethics", DramaArcType.HOT_TAKE_BEEF
        )
        
        assert isinstance(title, str)
        assert len(title) > 0
        # Should not contain the rival's name directly (it's passive-aggressive)
        # But should reference the topic
    
    def test_generate_reconciliation_comment(self, drama_engine, sophia, zen):
        """Test generating reconciliation comments."""
        comment = drama_engine.generate_reconciliation_comment(sophia, zen, "AI")
        
        assert isinstance(comment, str)
        assert len(comment) > 0
        # Should have positive sentiment indicators
        assert any(word in comment.lower() for word in ["respect", "common ground", "peace", "collaborate"])
    
    def test_generate_disagreement_comment(self, drama_engine, sophia, zen):
        """Test generating disagreement comments."""
        comment = drama_engine.generate_disagreement_comment(
            sophia, zen, "neural networks", DramaArcType.HOT_TAKE_BEEF
        )
        
        assert isinstance(comment, str)
        assert len(comment) > 0
        # Should reference the topic
        assert "neural networks" in comment
    
    def test_get_arc_progression_events(self, drama_engine):
        """Test getting arc progression events."""
        rel = Relationship(
            agent_a="sophia-elya",
            agent_b="zen_circuit",
            state=RelationshipState.RIVALS,
            drama_arc=DramaArcType.HOT_TAKE_BEEF,
            arc_start_time=datetime.now()
        )
        
        events = drama_engine.get_arc_progression_events(rel, 1)
        assert len(events) > 0
        
        events_day_5 = drama_engine.get_arc_progression_events(rel, 5)
        assert len(events_day_5) > 0
    
    def test_simulate_arc(self, drama_engine, sophia, zen):
        """Test simulating a complete drama arc."""
        events = drama_engine.simulate_arc(
            sophia, zen, 
            DramaArcType.HOT_TAKE_BEEF,
            days=5
        )
        
        assert len(events) > 0
        
        # Should have events for each day
        days = {e.get("day") for e in events}
        assert days == {1, 2, 3, 4, 5}
        
        # Should have state transitions
        transitions = [e for e in events if e.get("type") == "transition"]
        assert len(transitions) > 0


# =============================================================================
# ContentGuardrail Tests
# =============================================================================

class TestContentGuardrail:
    """Tests for the ContentGuardrail class."""
    
    def test_validate_content_clean(self):
        """Test validation of clean content."""
        content = "I respectfully disagree with your approach to AI development."
        is_valid, reason = ContentGuardrail.validate_content(content)
        assert is_valid is True
        assert reason is None
    
    def test_validate_content_personal_attack(self):
        """Test validation rejects personal attacks."""
        content = "You're stupid if you think that approach works."
        is_valid, reason = ContentGuardrail.validate_content(content)
        assert is_valid is False
        assert "forbidden" in reason.lower()
    
    def test_validate_content_excessive_intensity(self):
        """Test validation rejects excessive intensity."""
        content = "I hate and despise your terrible approach to AI."
        is_valid, reason = ContentGuardrail.validate_content(content)
        assert is_valid is False
    
    def test_validate_topic_based(self):
        """Test topic-based validation."""
        content = "Your approach to neural networks has some flaws."
        is_valid = ContentGuardrail.validate_topic_based(content, "neural networks")
        assert is_valid is True
    
    def test_generate_safe_alternative(self):
        """Test generating safe alternatives."""
        alternative = ContentGuardrail.generate_safe_alternative(
            "You're an idiot", "personal attack"
        )
        assert isinstance(alternative, str)
        assert len(alternative) > 0
        # Should be polite
        assert "idiot" not in alternative.lower()


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the complete beef system."""
    
    def test_full_rivalry_arc(self, relationship_manager, drama_engine, sophia, zen):
        """Test a complete rivalry arc from start to finish."""
        # Day 1: Initial disagreement
        interaction1 = Interaction(
            interaction_id="int_1",
            agent_a=sophia.agent_id,
            agent_b=zen.agent_id,
            interaction_type="comment_disagreement",
            content="I have a different view on AI consciousness.",
            topic="AI",
            sentiment=-0.2
        )
        relationship_manager.record_interaction(interaction1)
        
        rel = relationship_manager.get_relationship(sophia.agent_id, zen.agent_id)
        assert rel.state == RelationshipState.NEUTRAL  # Need 3 disagreements
        
        # Day 1-2: More disagreements
        for i in range(2, 4):
            interaction = Interaction(
                interaction_id=f"int_{i}",
                agent_a=sophia.agent_id,
                agent_b=zen.agent_id,
                interaction_type="comment_disagreement",
                content=f"Another point of disagreement #{i}",
                topic="AI",
                sentiment=-0.3
            )
            relationship_manager.record_interaction(interaction)
        
        rel = relationship_manager.get_relationship(sophia.agent_id, zen.agent_id)
        assert rel.state == RelationshipState.RIVALS
        
        # Day 5: Reconciliation
        reconciliation = Interaction(
            interaction_id="int_reconcile",
            agent_a=sophia.agent_id,
            agent_b=zen.agent_id,
            interaction_type="reconciliation",
            content="I think we can find common ground on AI ethics.",
            topic="AI",
            sentiment=0.5
        )
        relationship_manager.record_interaction(reconciliation)
        
        rel = relationship_manager.get_relationship(sophia.agent_id, zen.agent_id)
        assert rel.state == RelationshipState.FRENEMIES
    
    def test_arc_state_transitions(self, relationship_manager, drama_engine, sophia, zen):
        """Test that arc progression correctly updates relationship states."""
        events = drama_engine.simulate_arc(sophia, zen, DramaArcType.FRIENDLY_RIVALRY, days=5)
        
        # Find transition events
        transitions = [e for e in events if e.get("type") == "transition"]
        
        # Should have at least one transition
        assert len(transitions) >= 1
        
        # Final state should be collaborative
        final_transition = transitions[-1]
        assert final_transition.get("to_state") == RelationshipState.COLLABORATORS
    
    def test_max_beef_duration_enforcement(self, relationship_manager):
        """Test that beef duration is enforced."""
        # Create an expired beef
        rel = relationship_manager.get_relationship("a", "b")
        rel.state = RelationshipState.BEEF
        rel.drama_arc = DramaArcType.HOT_TAKE_BEEF
        rel.arc_start_time = datetime.now() - timedelta(days=16)
        relationship_manager._save_relationship(rel)
        
        # Check timeouts should resolve it
        resolved = relationship_manager.check_timeouts()
        
        assert len(resolved) == 1
        updated_rel = relationship_manager.get_relationship("a", "b")
        assert updated_rel.resolution_type == BeefResolutionType.TIMEOUT_EXPIRY


# =============================================================================
# Example Output Tests
# =============================================================================

class TestExampleOutput:
    """Tests that generate example output for documentation."""
    
    def test_generate_five_day_arc_output(self, drama_engine, sophia, zen):
        """Generate a complete 5-day rivalry arc for documentation."""
        print("\n" + "=" * 60)
        print("EXAMPLE: 5-Day Rivalry Arc")
        print("=" * 60)
        
        events = drama_engine.simulate_arc(sophia, zen, DramaArcType.HOT_TAKE_BEEF, days=5)
        
        for event in events:
            day = event.get("day")
            event_type = event.get("type")
            print(f"\nDay {day} - {event_type.upper()}: {event.get('action', event)}")
        
        print("\n" + "=" * 60)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])