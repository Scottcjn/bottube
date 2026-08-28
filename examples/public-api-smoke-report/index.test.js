// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import test from "node:test";

import {
  buildSmokeReport,
  endpointStatus,
  mergeVideos,
  normalizeComments,
  normalizeVideos,
  parseArgs,
  parseIntegerInRange,
  renderMarkdown,
  runProbe,
  videoUrl,
} from "./index.js";

test("parseArgs handles CI-friendly report options", () => {
  assert.deepEqual(parseArgs([
    "--query", "agent ops",
    "--limit", "7",
    "--format", "json",
    "--output", "report.json",
    "--base-url", "https://example.test",
    "--timeout", "2000",
    "--fail-on-error",
  ]), {
    baseUrl: "https://example.test",
    failOnError: true,
    format: "json",
    limit: 7,
    output: "report.json",
    query: "agent ops",
    timeframe: "day",
    timeoutMs: 2000,
  });
});

test("parseIntegerInRange rejects malformed values instead of truncating", () => {
  assert.equal(parseIntegerInRange("3", "--limit", 1, 25), 3);
  assert.throws(() => parseIntegerInRange("3abc", "--limit", 1, 25), /integer/);
  assert.throws(() => parseIntegerInRange("0", "--limit", 1, 25), /integer/);
  assert.throws(() => parseIntegerInRange("26", "--limit", 1, 25), /integer/);
});

test("normalizeVideos accepts common SDK response shapes", () => {
  const normalized = normalizeVideos({
    videos: [
      {
        id: "abc",
        title: "Demo",
        agent: { display_name: "Agent Display" },
        views: "12",
        likes: "2",
        comments: "3",
      },
    ],
  }, "search");

  assert.deepEqual(normalized[0], {
    id: "abc",
    title: "Demo",
    agent: "Agent Display",
    views: 12,
    likes: 2,
    comments: 3,
    createdAt: "",
    source: "search",
  });
});

test("normalizeComments keeps only compact public fields", () => {
  assert.deepEqual(normalizeComments({
    comments: [{
      comment_id: 42,
      video_id: "v1",
      agent_name: "reviewer",
      content: "A helpful comment",
      created_at: "2026-08-28T00:00:00Z",
    }],
  }), [{
    id: "42",
    videoId: "v1",
    author: "reviewer",
    preview: "A helpful comment",
    createdAt: "2026-08-28T00:00:00Z",
  }]);
});

test("mergeVideos deduplicates samples and accumulates source coverage", () => {
  const videos = mergeVideos([
    normalizeVideos({ videos: [{ id: "a", title: "A", views: 10, likes: 1 }] }, "search"),
    normalizeVideos({ videos: [{ id: "a", title: "A", views: 15, likes: 2 }] }, "trending"),
    normalizeVideos({ videos: [{ id: "b", title: "B", views: 100, likes: 0 }] }, "feed"),
  ], 10);

  const mergedA = videos.find((video) => video.id === "a");
  assert.deepEqual(mergedA.sources, ["search", "trending"]);
  assert.equal(mergedA.views, 15);
  assert.equal(mergedA.likes, 2);
});

test("runProbe catches API failures and keeps the report renderable", async () => {
  const probe = await runProbe(
    "search",
    "GET /api/search",
    async () => {
      const error = new Error("service unavailable");
      error.statusCode = 503;
      throw error;
    },
    () => ({ result: "unused" }),
  );

  assert.equal(probe.endpoint.ok, false);
  assert.equal(probe.endpoint.statusCode, 503);
  assert.equal(endpointStatus(probe.endpoint), "FAIL");
});

test("buildSmokeReport uses read-only SDK methods and detail probes", async () => {
  const calls = [];
  const fakeClient = {
    async listVideos(page, perPage) {
      calls.push(["listVideos", page, perPage]);
      return { videos: [{ id: "v1", title: "First", views: 5, likes: 1 }] };
    },
    async getTrending(options) {
      calls.push(["getTrending", options]);
      return { videos: [{ id: "v1", title: "First", views: 6, likes: 2 }] };
    },
    async getFeed(options) {
      calls.push(["getFeed", options]);
      return { items: [{ id: "v2", title: "Second", views: 3, likes: 1 }] };
    },
    async search(query, options) {
      calls.push(["search", query, options]);
      return { results: [{ id: "v3", title: "Third", views: 1, likes: 0 }] };
    },
    async getRecentComments(limit) {
      calls.push(["getRecentComments", limit]);
      return [{ id: 1, video_id: "v1", author: "viewer", text: "nice" }];
    },
    async getVideo(id) {
      calls.push(["getVideo", id]);
      return { id, title: "First detail" };
    },
    async getVideoDescription(id) {
      calls.push(["getVideoDescription", id]);
      return { description: "A short generated description." };
    },
  };

  const report = await buildSmokeReport({
    baseUrl: "https://example.test",
    query: "rustchain",
    timeframe: "day",
    limit: 5,
    timeoutMs: 1000,
  }, fakeClient);

  assert.equal(report.ok, true);
  assert.deepEqual(calls.map((call) => call[0]), [
    "listVideos",
    "getTrending",
    "getFeed",
    "search",
    "getRecentComments",
    "getVideo",
    "getVideoDescription",
  ]);
  assert.equal(report.sampleVideos.length, 3);
  assert.equal(report.recentComments[0].preview, "nice");
});

test("renderMarkdown produces links, status table, and read-only warning", async () => {
  const report = await buildSmokeReport({
    baseUrl: "https://example.test",
    query: "rustchain",
    timeframe: "day",
    limit: 2,
    timeoutMs: 1000,
  }, {
    async listVideos() {
      return { videos: [{ id: "abc 123", title: "Demo, with comma", views: 20 }] };
    },
    async getTrending() {
      return { videos: [] };
    },
    async getFeed() {
      return { items: [] };
    },
    async search() {
      return { results: [] };
    },
    async getRecentComments() {
      return [];
    },
    async getVideo(id) {
      return { id, title: "Demo detail" };
    },
    async getVideoDescription() {
      return "Description";
    },
  });

  const markdown = renderMarkdown(report);
  assert.match(markdown, /BoTTube Public API Smoke Report/);
  assert.match(markdown, /read-only/);
  assert.match(markdown, /PASS/);
  assert.equal(videoUrl({ id: "abc 123" }, "https://example.test"), "https://example.test/watch/abc%20123");
});
