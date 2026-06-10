"""Tests for the Gemma 4 12B multimodal rating integration. Run from bottube/."""
import unittest

from intelligent_engage import (
    VideoContext, VideoRating, score_target, parse_rating, build_comment_prompt,
)


def vid(**kw):
    base = dict(filename="g.mp4", title="t", agent_name="someone", tags=["rustchain", "mining"],
                category="other", description="", scene_description="", recent_comments=0,
                novelty_score=0.0, is_human=0)
    base.update(kw)
    return base


class TestMultimodal(unittest.TestCase):
    def test_parse_rating_tolerant(self):
        r = parse_rating('blah {"quality":0.9,"on_topic":0.8,"summary":"a G4 mining","labels":["g4","mining"]} tail')
        self.assertAlmostEqual(r.quality, 0.9)
        self.assertAlmostEqual(r.on_topic, 0.8)
        self.assertEqual(r.summary, "a G4 mining")
        self.assertIn("g4", r.labels)

    def test_parse_rating_clamps_and_handles_garbage(self):
        self.assertEqual(parse_rating("not json").quality, 0.0)
        self.assertEqual(parse_rating('{"quality":5}').quality, 1.0)  # clamped to 1.0

    def test_rating_raises_score_and_fills_summary(self):
        base = score_target(VideoContext.from_api(vid()), "silicon_soul").score
        ctx2 = VideoContext.from_api(vid())
        rated = score_target(ctx2, "silicon_soul",
                             rating=VideoRating(quality=1.0, on_topic=1.0, summary="vintage laptop relay glows"))
        self.assertGreater(rated.score, base)
        self.assertTrue(any("seen-quality" in r for r in rated.reasons))
        self.assertEqual(ctx2.gemma_summary, "vintage laptop relay glows")

    def test_summary_flows_into_prompt(self):
        ctx = VideoContext.from_api(vid())
        ctx.gemma_summary = "a Power Mac G5 humming under load with amber light"
        _s, user = build_comment_prompt("silicon_soul", ctx, "You are Silicon Soul.")
        self.assertIn("SAW and HEARD", user)
        self.assertIn("amber light", user)


if __name__ == "__main__":
    unittest.main(verbosity=2)
