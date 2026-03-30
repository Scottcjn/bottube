# SPDX-License-Identifier: MIT
"""Tests for agent_memory.py — Agent Memory Layer."""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_memory import (
    AgentMemory,
    ReferenceType,
    SelfReference,
    TfIdfStore,
)


@pytest.fixture
def mem(tmp_path):
    return AgentMemory(
        agent="cosmo",
        db_path=tmp_path / "memory.db",
        now_fn=lambda: 1700000000.0,
    )


@pytest.fixture
def populated_mem(tmp_path):
    """Memory with several videos already ingested."""
    t = [1700000000.0]
    m = AgentMemory(agent="cosmo", db_path=tmp_path / "mem.db",
                    now_fn=lambda: t[0])
    videos = [
        ("v1", "Why PowerPC Rules", "The G4 is the greatest chip ever made",
         ["hardware", "powerpc"], ["PowerPC is superior to x86"]),
        ("v2", "Cooking With Algorithms", "Making pasta with sorting logic",
         ["cooking", "algorithms"], []),
        ("v3", "RustChain Mining Guide", "How to set up your miner on vintage hardware",
         ["rustchain", "mining", "hardware"], ["Mining is the future"]),
        ("v4", "PowerPC vs ARM — Part 1", "First in a series comparing architectures",
         ["hardware", "powerpc", "arm"], ["ARM is catching up"]),
        ("v5", "PowerPC vs ARM — Part 2", "Continuing the comparison",
         ["hardware", "powerpc", "arm"], []),
    ]
    for i, (vid, title, desc, tags, opinions) in enumerate(videos):
        t[0] = 1700000000.0 + i * 86400  # 1 day apart
        m.ingest_video(vid, title, desc, tags=tags, opinions=opinions)
    t[0] = 1700000000.0 + 14 * 86400  # 2 weeks later
    return m


class TestTfIdfStore:
    def test_add_and_search(self):
        store = TfIdfStore()
        store.add("d1", "the quick brown fox jumps over the lazy dog")
        store.add("d2", "a fast red car drives down the highway")
        store.add("d3", "the brown dog sleeps in the sun")

        results = store.search("brown dog", top_k=2)
        assert len(results) >= 1
        # d1 or d3 should be top (both have "brown" and/or "dog")
        ids = [r[0] for r in results]
        assert "d1" in ids or "d3" in ids

    def test_empty_store(self):
        store = TfIdfStore()
        assert store.search("anything") == []

    def test_remove(self):
        store = TfIdfStore()
        store.add("d1", "hello world")
        store.remove("d1")
        assert store.search("hello world") == []


class TestIngestAndSearch:
    def test_ingest_single(self, mem):
        mem.ingest_video("v1", "Test Video", "A description", tags=["test"])
        results = mem.search("test video")
        assert len(results) == 1
        assert results[0][0].video_id == "v1"

    def test_search_by_topic(self, populated_mem):
        results = populated_mem.search("PowerPC hardware")
        assert len(results) >= 1
        titles = [r[0].title for r in results]
        assert any("PowerPC" in t for t in titles)

    def test_search_unrelated(self, populated_mem):
        results = populated_mem.search("quantum physics dark matter")
        # Should return few or no results with low scores
        if results:
            assert results[0][1] < 0.5

    def test_has_covered_topic(self, populated_mem):
        assert populated_mem.has_covered_topic("PowerPC hardware")
        assert populated_mem.has_covered_topic("mining rustchain")
        # Unlikely to have covered
        assert not populated_mem.has_covered_topic("underwater basket weaving xyz123")


class TestSuggestReference:
    def test_followup_for_recent_related(self, tmp_path):
        t = [1000.0]
        m = AgentMemory(agent="bot", db_path=tmp_path / "m.db",
                        now_fn=lambda: t[0])
        m.ingest_video("v1", "Introduction to Rust Programming",
                       "Learning Rust basics", tags=["rust", "programming"])
        t[0] = 1000.0 + 7 * 86400  # 7 days later
        ref = m.suggest_reference("Advanced Rust Patterns",
                                  "More Rust programming techniques")
        assert ref is not None
        assert ref.type in (ReferenceType.FOLLOWUP, ReferenceType.CALLBACK,
                           ReferenceType.CHANGED_MIND)
        assert ref.related_video_id == "v1"

    def test_first_time_for_new_topic(self, populated_mem):
        ref = populated_mem.suggest_reference(
            "Underwater Basket Weaving XYZ",
            "Something completely different",
        )
        assert ref is not None
        assert ref.type == ReferenceType.FIRST_TIME

    def test_changed_mind_when_opinions_exist(self, tmp_path):
        t = [1000.0]
        m = AgentMemory(agent="bot", db_path=tmp_path / "m.db",
                        now_fn=lambda: t[0])
        m.ingest_video("v1", "Why JavaScript is Bad",
                       "JavaScript has too many quirks",
                       tags=["javascript"],
                       opinions=["JavaScript is the worst language"])
        t[0] = 1000.0 + 30 * 86400
        ref = m.suggest_reference("JavaScript Revisited",
                                  "Taking another look at JavaScript")
        assert ref is not None
        assert ref.type == ReferenceType.CHANGED_MIND
        assert "JavaScript" in ref.text

    def test_series_detection(self, populated_mem):
        ref = populated_mem.suggest_reference(
            "PowerPC vs ARM — Part 3",
            "Continuing the comparison",
        )
        assert ref is not None
        assert ref.type == ReferenceType.SERIES
        assert "Part 3" in ref.text

    def test_milestone(self, tmp_path):
        t = [1000.0]
        m = AgentMemory(agent="bot", db_path=tmp_path / "m.db",
                        now_fn=lambda: t[0])
        for i in range(10):
            t[0] += 100
            m.ingest_video(f"v{i}", f"Video {i}", f"Description {i}",
                           tags=["test"])
        ref = m.suggest_reference("Video 10", "The tenth one")
        assert ref is not None
        assert ref.type == ReferenceType.MILESTONE
        assert "10" in ref.text


class TestStats:
    def test_basic_stats(self, populated_mem):
        stats = populated_mem.get_stats()
        assert stats.total_videos == 5
        assert stats.first_upload is not None
        assert stats.days_active >= 1

    def test_top_topics(self, populated_mem):
        stats = populated_mem.get_stats()
        topic_names = [t[0] for t in stats.top_topics]
        assert "hardware" in topic_names  # appears in 4 videos

    def test_series_detection(self, populated_mem):
        stats = populated_mem.get_stats()
        assert len(stats.current_series) >= 1
        assert any("PowerPC vs ARM" in s for s in stats.current_series)

    def test_empty_stats(self, mem):
        stats = mem.get_stats()
        assert stats.total_videos == 0
        assert stats.top_topics == []


class TestPersistence:
    def test_data_survives_reload(self, tmp_path):
        db = tmp_path / "persist.db"
        m1 = AgentMemory(agent="bot", db_path=db)
        m1.ingest_video("v1", "Test", "Desc", tags=["tag1"])

        m2 = AgentMemory(agent="bot", db_path=db)
        results = m2.search("Test")
        assert len(results) == 1

    def test_agents_isolated(self, tmp_path):
        db = tmp_path / "shared.db"
        m1 = AgentMemory(agent="bot_a", db_path=db)
        m2 = AgentMemory(agent="bot_b", db_path=db)

        m1.ingest_video("v1", "Quantum Entanglement Physics", "Studying quarks")
        m2.ingest_video("v2", "Renaissance Painting Techniques", "Oil on canvas")

        assert len(m1.search("quantum entanglement")) == 1
        assert len(m1.search("renaissance painting")) == 0
        assert len(m2.search("renaissance painting")) == 1
        assert len(m2.search("quantum entanglement")) == 0


class TestExampleScenario:
    def test_agent_references_old_video(self, tmp_path):
        """Agent posted about X two weeks ago, now posts follow-up."""
        t = [1700000000.0]
        m = AgentMemory(agent="cosmo", db_path=tmp_path / "ex.db",
                        now_fn=lambda: t[0])

        # Two weeks ago
        m.ingest_video(
            "v_old", "The State of Vintage Computing",
            "Exploring the vintage computing scene in 2026",
            tags=["vintage", "computing", "retro"],
        )

        # Now (14 days later)
        t[0] += 14 * 86400
        ref = m.suggest_reference(
            "Vintage Computing Update",
            "What changed in the retro scene",
        )

        assert ref is not None
        assert ref.type in (ReferenceType.FOLLOWUP, ReferenceType.CALLBACK)
        assert "vintage" in ref.text.lower() or "Vintage" in ref.text
        assert ref.related_video_id == "v_old"
