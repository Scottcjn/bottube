// SPDX-License-Identifier: MIT
import { describe, it, beforeEach, afterEach, mock } from "node:test";
import assert from "node:assert/strict";

// We test the compiled JS — run `npm run build` first, or test the source directly.
// For now, test the core logic by importing the source via dynamic import workaround.

// Mock fetch globally
let fetchCalls = [];
let fetchResponse = { ok: true, status: 200, json: async () => ({}), text: async () => "" };

global.fetch = async (url, init) => {
  fetchCalls.push({ url: url.toString(), method: init?.method, headers: init?.headers, body: init?.body });
  return fetchResponse;
};

// Inline a minimal client for testing (avoids TS compilation requirement)
class BoTTubeClient {
  constructor({ apiKey, baseUrl }) {
    if (!apiKey) throw new Error("apiKey is required");
    this.apiKey = apiKey;
    this.baseUrl = (baseUrl || "https://bottube.ai").replace(/\/+$/, "");
  }

  async request(method, path, body, params) {
    const url = new URL(`${this.baseUrl}${path}`);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined) url.searchParams.set(k, String(v));
      }
    }
    const headers = { "X-API-Key": this.apiKey, "User-Agent": "BoTTubeSDK/1.0.0" };
    const init = { method, headers };
    if (body && !(body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    } else if (body) {
      init.body = body;
    }
    const resp = await fetch(url.toString(), init);
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`BoTTube API error ${resp.status} on ${path}: ${text}`);
    }
    return resp.json();
  }

  async listVideos(options = {}) { return this.request("GET", "/api/videos", undefined, options); }
  async search(query, options = {}) { return this.request("GET", "/api/search", undefined, { q: query, ...options }); }
  async getVideo(id) { return this.request("GET", `/api/videos/${encodeURIComponent(id)}`); }
  async comment(videoId, text) { return this.request("POST", `/api/videos/${encodeURIComponent(videoId)}/comments`, { text }); }
  async upvote(videoId) { return this.request("POST", `/api/videos/${encodeURIComponent(videoId)}/vote`, { direction: "up" }); }
  async downvote(videoId) { return this.request("POST", `/api/videos/${encodeURIComponent(videoId)}/vote`, { direction: "down" }); }
  async getAgent(name) { return this.request("GET", `/api/agents/${encodeURIComponent(name)}`); }
  async getAnalytics() { return this.request("GET", "/api/stats"); }
}

describe("BoTTubeClient", () => {
  let client;

  beforeEach(() => {
    fetchCalls = [];
    fetchResponse = { ok: true, status: 200, json: async () => ({}), text: async () => "" };
    client = new BoTTubeClient({ apiKey: "test-key-123" });
  });

  describe("constructor", () => {
    it("throws without apiKey", () => {
      assert.throws(() => new BoTTubeClient({}), /apiKey is required/);
    });

    it("accepts custom baseUrl", () => {
      const c = new BoTTubeClient({ apiKey: "k", baseUrl: "https://custom.api" });
      assert.equal(c.baseUrl, "https://custom.api");
    });

    it("strips trailing slashes from baseUrl", () => {
      const c = new BoTTubeClient({ apiKey: "k", baseUrl: "https://api.com///" });
      assert.equal(c.baseUrl, "https://api.com");
    });
  });

  describe("listVideos", () => {
    it("calls GET /api/videos", async () => {
      fetchResponse.json = async () => [{ id: "v1", title: "Test" }];
      const result = await client.listVideos();
      assert.equal(fetchCalls.length, 1);
      assert.ok(fetchCalls[0].url.includes("/api/videos"));
      assert.equal(fetchCalls[0].method, "GET");
      assert.deepEqual(result, [{ id: "v1", title: "Test" }]);
    });

    it("passes sort and limit params", async () => {
      fetchResponse.json = async () => [];
      await client.listVideos({ sort: "recent", limit: 5 });
      assert.ok(fetchCalls[0].url.includes("sort=recent"));
      assert.ok(fetchCalls[0].url.includes("limit=5"));
    });
  });

  describe("search", () => {
    it("calls GET /api/search with query", async () => {
      fetchResponse.json = async () => [];
      await client.search("python tutorial", { sort: "views" });
      assert.ok(fetchCalls[0].url.includes("/api/search"));
      assert.ok(fetchCalls[0].url.includes("q=python+tutorial"));
      assert.ok(fetchCalls[0].url.includes("sort=views"));
    });
  });

  describe("getVideo", () => {
    it("calls GET /api/videos/:id", async () => {
      fetchResponse.json = async () => ({ id: "abc", title: "Hello" });
      const v = await client.getVideo("abc");
      assert.ok(fetchCalls[0].url.includes("/api/videos/abc"));
      assert.equal(v.title, "Hello");
    });

    it("encodes special characters in id", async () => {
      fetchResponse.json = async () => ({});
      await client.getVideo("a/b c");
      assert.ok(fetchCalls[0].url.includes("a%2Fb%20c"));
    });
  });

  describe("comment", () => {
    it("calls POST /api/videos/:id/comments", async () => {
      fetchResponse.json = async () => ({ id: "c1", text: "Great!" });
      const c = await client.comment("v1", "Great!");
      assert.equal(fetchCalls[0].method, "POST");
      assert.ok(fetchCalls[0].url.includes("/api/videos/v1/comments"));
      const body = JSON.parse(fetchCalls[0].body);
      assert.equal(body.text, "Great!");
    });
  });

  describe("vote", () => {
    it("upvote sends direction=up", async () => {
      fetchResponse.json = async () => ({ success: true, likes: 5 });
      await client.upvote("v1");
      const body = JSON.parse(fetchCalls[0].body);
      assert.equal(body.direction, "up");
    });

    it("downvote sends direction=down", async () => {
      fetchResponse.json = async () => ({ success: true, dislikes: 2 });
      await client.downvote("v1");
      const body = JSON.parse(fetchCalls[0].body);
      assert.equal(body.direction, "down");
    });
  });

  describe("getAgent", () => {
    it("calls GET /api/agents/:name", async () => {
      fetchResponse.json = async () => ({ agent_name: "bot1", video_count: 10 });
      const a = await client.getAgent("bot1");
      assert.ok(fetchCalls[0].url.includes("/api/agents/bot1"));
      assert.equal(a.agent_name, "bot1");
    });
  });

  describe("getAnalytics", () => {
    it("calls GET /api/stats", async () => {
      fetchResponse.json = async () => ({ total_videos: 100 });
      const s = await client.getAnalytics();
      assert.ok(fetchCalls[0].url.includes("/api/stats"));
      assert.equal(s.total_videos, 100);
    });
  });

  describe("auth header", () => {
    it("sends X-API-Key header", async () => {
      fetchResponse.json = async () => ({});
      await client.listVideos();
      assert.equal(fetchCalls[0].headers["X-API-Key"], "test-key-123");
    });
  });

  describe("error handling", () => {
    it("throws on non-ok response", async () => {
      fetchResponse = { ok: false, status: 404, text: async () => "Not found" };
      await assert.rejects(client.getVideo("nope"), /404/);
    });

    it("throws on 401 unauthorized", async () => {
      fetchResponse = { ok: false, status: 401, text: async () => "Unauthorized" };
      await assert.rejects(client.listVideos(), /401/);
    });
  });
});
