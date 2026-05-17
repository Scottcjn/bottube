import assert from "node:assert/strict";
import test from "node:test";

import { renderVideo, videoUrl } from "./index.js";

test("renderVideo escapes API text before writing Markdown", () => {
  const video = {
    video_id: "abc 123/../x?z=1",
    title: "Update](https://evil.example) [x",
    agent_name: "@channel [agent](bad) <@U123>",
    description: "Summary with [link](https://evil.example) and @here",
    view_count: 12,
    like_count: 3,
  };

  const rendered = renderVideo(video, 0, "https://bottube.ai");

  assert.equal(
    videoUrl(video, "https://bottube.ai"),
    "https://bottube.ai/watch/abc%20123%2F..%2Fx%3Fz%3D1",
  );
  assert.ok(rendered.includes("[Update\\]\\(https://evil.example\\) \\[x]"));
  assert.ok(rendered.includes("Agent: \\@channel \\[agent\\]\\(bad\\) \\<\\@U123\\>"));
  assert.ok(rendered.includes("Summary with \\[link\\]\\(https://evil.example\\) and \\@here"));
  assert.doesNotMatch(rendered, /\[Update\]\(https:\/\/evil\.example\)/);
});
