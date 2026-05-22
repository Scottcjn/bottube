import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildSnapshot,
  parseArgs,
  renderJson,
  renderMarkdown,
} from "../src/snapshot.js";

test("buildSnapshot normalizes public BoTTube counters", async () => {
  const snapshot = await buildSnapshot(async () => ({
    health: { ok: true, service: "bottube", version: "1.2.0", uptime_s: 42 },
    footerCounters: {
      stats: { agents: 12, humans: 3, videos: 99 },
      bottube: {
        github: { stars: 7, forks: 2 },
        downloads: { npm: 5, pypi: 6, clawhub: 1 },
      },
      clawrtc: {
        github: { stars: 8, forks: 4 },
        downloads: { npm: 15, pypi: 16, clawhub: 11 },
      },
      ts: 1779486062,
    },
    githubStats: { stars: 10, forks: 4, clones: 20 },
  }));

  assert.equal(snapshot.health.ok, true);
  assert.equal(snapshot.platform.agents, 12);
  assert.equal(snapshot.platform.videos, 99);
  assert.equal(snapshot.projects[0].name, "BoTTube");
  assert.equal(snapshot.projects[0].npmDownloads, 5);
  assert.equal(snapshot.github.stars, 10);
});

test("renderMarkdown includes the health and project table", async () => {
  const snapshot = await buildSnapshot(async () => ({
    health: { ok: true, service: "bottube", version: "1.2.0" },
    footerCounters: {
      stats: { agents: 12, humans: 3, videos: 99 },
      bottube: { github: { stars: 7, forks: 2 }, downloads: { npm: 5 } },
      ts: 1779486062,
    },
    githubStats: { stars: 10, forks: 4, clones: 20 },
  }));

  const markdown = renderMarkdown(snapshot);
  assert.match(markdown, /# BoTTube Platform Snapshot/);
  assert.match(markdown, /API OK: yes/);
  assert.match(markdown, /\| BoTTube \| 7 \| 2 \| 5 \| 0 \| 0 \|/);
  assert.match(markdown, /Stars: 10/);
});

test("renderJson emits parseable JSON", async () => {
  const snapshot = await buildSnapshot(async () => ({
    health: { ok: true },
    footerCounters: { stats: { agents: 1 }, ts: 1779486062 },
    githubStats: {},
  }));

  assert.equal(JSON.parse(renderJson(snapshot)).platform.agents, 1);
});

test("parseArgs rejects malformed timeout and format values", () => {
  assert.throws(() => parseArgs(["--timeout-ms", "2abc"]), /positive integer/);
  assert.throws(() => parseArgs(["--format", "xml"]), /markdown or json/);
});
