import assert from "node:assert/strict";
import test from "node:test";

import {
  csvCell,
  mergeVideos,
  normalizeVideos,
  parseArgs,
  parseLimit,
  renderCsv,
  renderMarkdown,
  videoUrl,
} from "./index.js";

test("parseLimit rejects malformed values instead of truncating", () => {
  assert.equal(parseLimit("3"), 3);
  assert.throws(() => parseLimit("3abc"), /integer/);
  assert.throws(() => parseLimit("0"), /integer/);
  assert.throws(() => parseLimit("26"), /integer/);
});

test("parseArgs handles format, output, and fixture options", () => {
  assert.deepEqual(parseArgs([
    "--query", "agents",
    "--limit", "7",
    "--format", "csv",
    "--output", "/tmp/watchlist.csv",
    "--fixture", "fixture.json",
  ]), {
    baseUrl: "https://bottube.ai",
    fixture: "fixture.json",
    format: "csv",
    limit: 7,
    output: "/tmp/watchlist.csv",
    query: "agents",
    timeframe: "day",
  });
});

test("normalizeVideos accepts SDK response variants", () => {
  const normalized = normalizeVideos({
    videos: [
      {
        id: "abc",
        title: "Demo",
        agent: { display_name: "Agent Display" },
        views: "12",
        likes: "2",
        tags: ["sdk"],
      },
    ],
  }, "search");

  assert.deepEqual(normalized[0], {
    id: "abc",
    title: "Demo",
    agent: "Agent Display",
    description: "",
    views: 12,
    likes: 2,
    createdAt: "",
    tags: ["sdk"],
    source: "search",
  });
});

test("mergeVideos deduplicates videos and accumulates sources", () => {
  const videos = mergeVideos([
    normalizeVideos({ videos: [{ video_id: "a", title: "A", views: 10, likes: 1 }] }, "search"),
    normalizeVideos({ videos: [{ id: "a", title: "A", views: 15, likes: 2 }] }, "trending"),
    normalizeVideos({ videos: [{ id: "b", title: "B", views: 100, likes: 0 }] }, "feed"),
  ], 10);

  const mergedA = videos.find((video) => video.id === "a");
  assert.deepEqual(mergedA.sources, ["search", "trending"]);
  assert.equal(mergedA.views, 15);
  assert.equal(mergedA.likes, 2);
});

test("renderers produce markdown links and escaped CSV cells", () => {
  const options = { baseUrl: "https://bottube.ai", query: "rustchain" };
  const videos = [{
    id: "abc 123",
    title: "Demo, with comma",
    agent: "reviewer",
    views: 20,
    likes: 3,
    score: 56,
    tags: ["a", "b"],
    sources: ["search"],
  }];

  assert.equal(videoUrl(videos[0], options.baseUrl), "https://bottube.ai/watch/abc%20123");
  assert.match(renderMarkdown(videos, options), /Demo, with comma/);
  assert.match(renderCsv(videos, options), /"Demo, with comma"/);
  assert.equal(csvCell('a "quoted" value'), '"a ""quoted"" value"');
});
