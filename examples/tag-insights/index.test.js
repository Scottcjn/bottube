import assert from "node:assert/strict";
import test from "node:test";

import { escapeMarkdown, normalizeVideos, parseArgs, renderMarkdown, videoUrl } from "./index.js";

test("parseArgs validates bounded integers", () => {
  assert.equal(parseArgs(["--limit", "3", "--samples", "2"]).limit, 3);
  assert.throws(() => parseArgs(["--limit", "2abc"]), /--limit must be an integer/);
  assert.throws(() => parseArgs(["--samples", "11"]), /--samples must be between 0 and 10/);
});

test("normalizeVideos accepts current and older SDK response shapes", () => {
  assert.deepEqual(normalizeVideos({ videos: [{ video_id: "a" }] }), [{ video_id: "a" }]);
  assert.deepEqual(normalizeVideos({ results: [{ video_id: "b" }] }), [{ video_id: "b" }]);
  assert.deepEqual(normalizeVideos({}), []);
});

test("renderMarkdown escapes API text and encodes video IDs", () => {
  const report = {
    generated_at: "2026-05-22T00:00:00.000Z",
    base_url: "https://bottube.ai",
    query: "ai [demo]\nnew row",
    tags: [{ tag: "ai|video\n| 999 | injected | 999 |", count: 7 }],
    videos: [
      {
        video_id: "abc 123/../x?z=1",
        title: "Hello](https://evil.example) [x\nsecond line",
        agent_name: "@agent <tag>\r\nthird line",
        views: 9,
      },
    ],
  };

  const markdown = renderMarkdown(report);

  assert.ok(markdown.includes("ai \\[demo\\] new row"));
  assert.ok(markdown.includes("ai\\|video \\| 999 \\| injected \\| 999 \\|"));
  assert.ok(markdown.includes("[Hello\\]\\(https://evil.example\\) \\[x second line]"));
  assert.ok(markdown.includes("Agent: \\@agent \\<tag\\> third line"));
  assert.ok(markdown.includes("https://bottube.ai/watch/abc%20123%2F..%2Fx%3Fz%3D1"));
  assert.doesNotMatch(markdown, /\[Hello\]\(https:\/\/evil\.example\)/);
  assert.doesNotMatch(markdown, /\n\| 999 \| injected \| 999 \|/);
});

test("videoUrl and escapeMarkdown handle plain values", () => {
  assert.equal(videoUrl("https://bottube.ai/", "abc"), "https://bottube.ai/watch/abc");
  assert.equal(escapeMarkdown("plain text"), "plain text");
});
