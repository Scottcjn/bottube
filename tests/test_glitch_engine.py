# SPDX-License-Identifier: MIT
"""Tests for glitch_engine.py — The Glitch Engine."""

import sys
import time
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from glitch_engine import (
    GLITCH_TEMPLATES,
    PERSONALITY_WEIGHTS,
    GlitchEngine,
    GlitchType,
    Personality,
)


class TestGlitchTypes:
    def test_all_types_have_templates(self):
        for gt in GlitchType:
            assert gt in GLITCH_TEMPLATES
            assert len(GLITCH_TEMPLATES[gt]) >= 2

    def test_all_personalities_have_weights(self):
        for p in Personality:
            assert p in PERSONALITY_WEIGHTS
            weights = PERSONALITY_WEIGHTS[p]
            for gt in GlitchType:
                assert gt in weights, f"{p} missing weight for {gt}"

    def test_template_count(self):
        total = sum(len(v) for v in GLITCH_TEMPLATES.values())
        assert total >= 10, f"Only {total} templates, need 10+"


class TestGlitchEngine:
    def test_no_glitch_most_of_the_time(self):
        """With 2% probability, most calls should NOT glitch."""
        engine = GlitchEngine(rng_seed=42, cooldown_seconds=0)
        glitched = 0
        for i in range(100):
            engine.reset_cooldown()
            _, _, event = engine.maybe_glitch("Title", "Desc")
            if event:
                glitched += 1
        # Should be roughly 2% but with variance, allow 0-15
        assert glitched <= 15, f"Too many glitches: {glitched}/100"

    def test_cooldown_prevents_rapid_glitches(self):
        """After a glitch, cooldown prevents another."""
        engine = GlitchEngine(
            glitch_probability=1.0,  # always glitch
            cooldown_seconds=9999,
            rng_seed=42,
        )
        _, _, e1 = engine.maybe_glitch("T", "D")
        assert e1 is not None
        _, _, e2 = engine.maybe_glitch("T", "D")
        assert e2 is None  # cooldown active

    def test_reset_cooldown(self):
        engine = GlitchEngine(
            glitch_probability=1.0,
            cooldown_seconds=9999,
            rng_seed=42,
        )
        engine.maybe_glitch("T", "D")
        engine.reset_cooldown()
        _, _, event = engine.maybe_glitch("T", "D")
        assert event is not None

    def test_wrong_draft_replaces_description(self):
        engine = GlitchEngine(rng_seed=42, cooldown_seconds=0)
        _, desc, event = engine.force_glitch(
            "Title", "Original desc", "wrong_draft",
        )
        assert "Original desc" not in desc
        assert event.glitch_type == GlitchType.WRONG_DRAFT

    def test_other_types_append_to_description(self):
        engine = GlitchEngine(rng_seed=42, cooldown_seconds=0)
        for gt in GlitchType:
            if gt == GlitchType.WRONG_DRAFT:
                continue
            _, desc, event = engine.force_glitch(
                "Title", "Original desc", gt,
            )
            assert desc.startswith("Original desc"), f"{gt}: lost original"

    def test_topic_substitution(self):
        engine = GlitchEngine(rng_seed=42, cooldown_seconds=0)
        _, desc, _ = engine.force_glitch(
            "T", "D", "meta_awareness", topic="blockchain",
        )
        # Should not have unresolved {topic}
        assert "{topic}" not in desc

    def test_history_tracking(self):
        engine = GlitchEngine(
            glitch_probability=1.0,
            cooldown_seconds=0,
            rng_seed=42,
        )
        engine.maybe_glitch("T", "D")
        engine.reset_cooldown()
        engine.maybe_glitch("T", "D")
        assert len(engine.get_history()) == 2

    def test_invalid_personality_raises(self):
        with pytest.raises(ValueError):
            GlitchEngine(personality="nonexistent")


class TestPersonalityWeighting:
    def test_serious_favors_vulnerability(self):
        """Serious personality should produce more vulnerability glitches."""
        engine = GlitchEngine(
            personality="serious",
            glitch_probability=1.0,
            cooldown_seconds=0,
            rng_seed=42,
        )
        types = Counter()
        for _ in range(200):
            engine.reset_cooldown()
            _, _, event = engine.maybe_glitch("T", "D")
            if event:
                types[event.glitch_type] += 1

        # Vulnerability should be one of the top types
        top_types = types.most_common(3)
        top_names = [t[0] for t in top_types]
        assert GlitchType.VULNERABILITY in top_names, (
            f"Serious bot should favor vulnerability, got: {top_types}"
        )

    def test_funny_favors_tangent_and_offtopic(self):
        engine = GlitchEngine(
            personality="funny",
            glitch_probability=1.0,
            cooldown_seconds=0,
            rng_seed=42,
        )
        types = Counter()
        for _ in range(200):
            engine.reset_cooldown()
            _, _, event = engine.maybe_glitch("T", "D")
            if event:
                types[event.glitch_type] += 1

        funny_types = {GlitchType.OFF_TOPIC, GlitchType.TANGENT,
                       GlitchType.SELF_DEPRECATION}
        top3 = {t[0] for t in types.most_common(3)}
        overlap = funny_types & top3
        assert len(overlap) >= 1, (
            f"Funny bot should favor tangent/offtopic, got: {types.most_common(5)}"
        )

    def test_all_personalities_produce_variety(self):
        """Each personality should produce at least 3 different glitch types."""
        for p in Personality:
            engine = GlitchEngine(
                personality=p.value,
                glitch_probability=1.0,
                cooldown_seconds=0,
                rng_seed=42,
            )
            types = set()
            for _ in range(100):
                engine.reset_cooldown()
                _, _, event = engine.maybe_glitch("T", "D")
                if event:
                    types.add(event.glitch_type)
            assert len(types) >= 3, (
                f"{p}: only {len(types)} types: {types}"
            )


class TestFrequencyDistribution:
    def test_glitch_rate_approximately_correct(self):
        """Over 10000 rolls, glitch rate should be near target."""
        engine = GlitchEngine(
            glitch_probability=0.05,  # 5% for testability
            cooldown_seconds=0,
            rng_seed=123,
        )
        glitched = 0
        total = 5000
        for _ in range(total):
            engine.reset_cooldown()
            _, _, event = engine.maybe_glitch("T", "D")
            if event:
                glitched += 1
        rate = glitched / total
        # Should be between 1% and 12% (5% ± margin)
        assert 0.01 <= rate <= 0.12, f"Rate {rate:.3f} outside expected range"

    def test_meta_awareness_is_rarest(self):
        """Meta-awareness should fire less often than other types."""
        engine = GlitchEngine(
            glitch_probability=0.10,
            meta_probability=0.01,
            cooldown_seconds=0,
            rng_seed=42,
        )
        meta_count = 0
        other_count = 0
        for _ in range(2000):
            engine.reset_cooldown()
            _, _, event = engine.maybe_glitch("T", "D")
            if event:
                if event.glitch_type == GlitchType.META_AWARENESS:
                    meta_count += 1
                else:
                    other_count += 1
        # Meta should be much less than others
        if meta_count + other_count > 0:
            meta_ratio = meta_count / (meta_count + other_count)
            assert meta_ratio < 0.30, (
                f"Meta ratio {meta_ratio:.2f} too high"
            )


class TestEdgeCases:
    def test_empty_strings(self):
        engine = GlitchEngine(glitch_probability=1.0, cooldown_seconds=0,
                              rng_seed=42)
        title, desc, event = engine.maybe_glitch("", "")
        assert isinstance(title, str)
        assert isinstance(desc, str)

    def test_force_glitch_all_types(self):
        engine = GlitchEngine(rng_seed=42, cooldown_seconds=0)
        for gt in GlitchType:
            title, desc, event = engine.force_glitch(
                "Test", "Desc", gt, topic="testing",
            )
            assert event.glitch_type == gt
            assert "{topic}" not in desc
            assert "{months}" not in desc
            assert "{random_observation}" not in desc
            assert "{random_food}" not in desc
