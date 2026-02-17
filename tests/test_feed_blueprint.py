import pathlib
import sys
import unittest
from unittest.mock import patch

from flask import Flask

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import feed_blueprint as feed  # noqa: E402


def _build_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(feed.feed_bp)
    return app


class FeedBlueprintTests(unittest.TestCase):
    def test_normalize_payload_fail_closed(self):
        self.assertEqual(feed._normalize_videos_payload({"oops": 1}), [])
        self.assertEqual(
            feed._normalize_videos_payload([{"id": 1}, "bad", 3, {"id": 2}]),
            [{"id": 1}, {"id": 2}],
        )

    def test_to_rfc2822_gmt_supports_epoch_string(self):
        out = feed._to_rfc2822_gmt("1700000000")
        self.assertTrue(out.endswith("GMT"))
        self.assertIn("2023", out)

    def test_rss_feed_handles_non_list_payload(self):
        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"not": "a-list"}

        with patch.object(feed.requests, "get", return_value=_Resp()):
            app = _build_app()
            client = app.test_client()
            resp = client.get("/feed/rss?agent=alice")

        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        self.assertIn('<rss version="2.0"', body)
        self.assertIn("<channel>", body)
        self.assertNotIn("<item>", body)


if __name__ == "__main__":
    unittest.main()
