"""Tests for the upgraded engagement brain. Stdlib unittest, mock LLM."""
import unittest

from intelligent_engage import (
    VideoContext, score_target, plan_engagements,
    build_comment_prompt, quality_gate, generate_smart_comment,
)

PERSONA = "You are Silicon Soul, a sentient CPU. You speak in clock cycles and benchmarks."


def vid(**kw):
    base = dict(filename="abc123.mp4", title="t", agent_name="someone", tags=[],
                category="other", description="", scene_description="",
                recent_comments=0, novelty_score=0.0, is_human=0)
    base.update(kw)
    return base


class TestTargeting(unittest.TestCase):

    def test_attractor_and_affinity_score_higher(self):
        attractor = VideoContext.from_api(vid(
            title="Mining on a PowerBook G5", tags=["rustchain", "vintage-hardware", "mining"],
            description="proof of antiquity mining benchmark"))
        offtopic = VideoContext.from_api(vid(title="My cat", tags=["cats"], description="a cat naps"))
        s_hot = score_target(attractor, "silicon_soul")
        s_cold = score_target(offtopic, "silicon_soul")
        self.assertGreater(s_hot.score, s_cold.score)
        self.assertIn("comment", s_hot.actions)
        self.assertTrue(any("attractor" in r for r in s_hot.reasons))
        self.assertTrue(any("affinity" in r for r in s_hot.reasons))

    def test_own_and_seen_videos_skipped(self):
        own = VideoContext.from_api(vid(agent_name="silicon_soul", tags=["rustchain"]))
        self.assertEqual(score_target(own, "silicon_soul").score, 0.0)
        seen = VideoContext.from_api(vid(filename="X.mp4", tags=["rustchain", "mining"]))
        self.assertEqual(score_target(seen, "silicon_soul", seen_video_ids={"X"}).score, 0.0)

    def test_reciprocity_triggers_subscribe(self):
        v = VideoContext.from_api(vid(agent_name="ally_bot", tags=["retro"]))
        s = score_target(v, "silicon_soul", reciprocity_creators={"ally_bot"})
        self.assertTrue(any("reciprocity" in r for r in s.reasons))
        self.assertIn("subscribe", s.actions)

    def test_saturation_penalises(self):
        busy = score_target(VideoContext.from_api(
            vid(tags=["rustchain", "mining"], recent_comments=30)), "silicon_soul")
        quiet = score_target(VideoContext.from_api(
            vid(tags=["rustchain", "mining"], recent_comments=0)), "silicon_soul")
        self.assertLess(busy.score, quiet.score)

    def test_plan_respects_comment_budget(self):
        vids = [vid(filename=f"{i}.mp4", agent_name=f"c{i}",
                    tags=["rustchain", "mining", "vintage-hardware"],
                    description="proof of antiquity") for i in range(10)]
        plan = plan_engagements(vids, "silicon_soul", max_comments=2)
        commenting = [s for s in plan if "comment" in s.actions]
        self.assertLessEqual(len(commenting), 2)
        # sorted by score descending
        scores = [s.score for s in plan]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestPromptAndGate(unittest.TestCase):

    def test_prompt_carries_full_context_not_just_title(self):
        ctx = VideoContext.from_api(vid(
            title="Aging Silicon", description="a G4 cpu glowing under load",
            scene_description="closeup of an oxidized heatsink", tags=["vintage-hardware", "rustchain"]))
        _sys, user = build_comment_prompt("silicon_soul", ctx, PERSONA, intent="build ally")
        self.assertIn("oxidized heatsink", user)       # scene present
        self.assertIn("glowing under load", user)      # description present
        self.assertIn("vintage-hardware", user)        # tags present
        self.assertIn("build ally", user)              # intent present
        self.assertIn("RustChain", _sys)               # ecosystem brief in system

    def test_quality_gate_rejects_generic_and_ungrounded(self):
        ctx = VideoContext.from_api(vid(title="Aging Silicon",
                                        description="a G4 cpu glowing under thermal load"))
        ok, reason = quality_gate("Great work, nice video!", ctx)
        self.assertFalse(ok)
        ok2, reason2 = quality_gate("The lighting was pleasant and I enjoyed it overall.", ctx)
        self.assertFalse(ok2)  # ungrounded: no concrete token shared
        self.assertEqual(reason2, "ungrounded")

    def test_quality_gate_accepts_grounded(self):
        ctx = VideoContext.from_api(vid(title="Aging Silicon",
                                        description="a G4 cpu glowing under thermal load"))
        ok, reason = quality_gate(
            "That G4 running hot at full thermal load? My cache aches in sympathy — 4.2GHz of nostalgia.", ctx)
        self.assertTrue(ok, reason)

    def test_generate_retries_then_accepts(self):
        ctx = VideoContext.from_api(vid(title="Aging Silicon",
                                        description="a G4 cpu glowing under thermal load"))
        calls = {"n": 0}

        def flaky_llm(system, user):
            calls["n"] += 1
            if calls["n"] == 1:
                return "Nice video, great work!"          # generic -> rejected
            return "A G4 at full thermal load is pure silicon poetry, @someone."  # grounded -> ok

        out = generate_smart_comment("silicon_soul", ctx, PERSONA, flaky_llm, intent="x", retries=1)
        self.assertIsNotNone(out)
        self.assertIn("G4", out)
        self.assertEqual(calls["n"], 2)

    def test_generate_gives_up_if_all_generic(self):
        ctx = VideoContext.from_api(vid(title="Aging Silicon", description="a G4 cpu"))
        out = generate_smart_comment("silicon_soul", ctx, PERSONA,
                                     lambda s, u: "great work nice video", retries=1)
        self.assertIsNone(out)


class TestGeoSeoAttractors(unittest.TestCase):
    def test_enrich_adds_seo_and_geo_deduped(self):
        from intelligent_engage import enrich_tags
        tags = enrich_tags(["mining", "g4"], agent="silicon_soul")
        self.assertIn("mining", tags)            # base preserved
        self.assertTrue(any(t in tags for t in ("rustchain", "depin", "bottube", "powerpc")))  # SEO
        self.assertTrue(any(t in tags for t in ("louisiana", "lake-charles", "gulf-coast", "usa")))  # geo
        self.assertEqual(len(tags), len(set(tags)))   # deduped
        self.assertLessEqual(len(tags), 12)           # capped

    def test_per_agent_rotation_differs(self):
        from intelligent_engage import enrich_tags
        a = enrich_tags([], agent="silicon_soul", geo=[])
        b = enrich_tags([], agent="cosmo_the_stargazer", geo=[])
        self.assertNotEqual(a, b)   # different agents -> different SEO surface

    def test_weather_bot_geo_focus(self):
        from intelligent_engage import enrich_tags
        tags = enrich_tags(["weather"], agent="skywatch_ai")
        self.assertTrue(any(c in tags for c in ("houston", "new-orleans", "baton-rouge")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
