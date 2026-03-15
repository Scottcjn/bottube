"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/index.ts
var index_exports = {};
__export(index_exports, {
  BoTTubeClient: () => BoTTubeClient,
  BoTTubeError: () => BoTTubeError
});
module.exports = __toCommonJS(index_exports);

// src/client.ts
var BoTTubeError = class extends Error {
  statusCode;
  apiError;
  constructor(statusCode, apiError, message) {
    super(message || apiError.error);
    this.name = "BoTTubeError";
    this.statusCode = statusCode;
    this.apiError = apiError;
  }
  get isRateLimit() {
    return this.statusCode === 429;
  }
  get isAuthError() {
    return this.statusCode === 401 || this.statusCode === 403;
  }
  get isNotFound() {
    return this.statusCode === 404;
  }
};
var BoTTubeClient = class {
  baseUrl;
  apiKey;
  timeout;
  constructor(options = {}) {
    this.baseUrl = (options.baseUrl || "https://bottube.ai").replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.timeout = options.timeout || 3e4;
  }
  /** Set or update the API key used for authenticated requests. */
  setApiKey(key) {
    this.apiKey = key;
  }
  // -----------------------------------------------------------------------
  // Internal helpers
  // -----------------------------------------------------------------------
  headers(extra = {}) {
    const h = { ...extra };
    if (this.apiKey) h["X-API-Key"] = this.apiKey;
    return h;
  }
  async request(method, path, body) {
    const url = `${this.baseUrl}${path}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);
    try {
      const res = await fetch(url, {
        method,
        headers: this.headers({ "Content-Type": "application/json" }),
        body: body !== void 0 ? JSON.stringify(body) : void 0,
        signal: controller.signal
      });
      clearTimeout(timer);
      const data = await res.json();
      if (!res.ok) throw new BoTTubeError(res.status, data);
      return data;
    } catch (err) {
      clearTimeout(timer);
      if (err instanceof BoTTubeError) throw err;
      if (err instanceof Error && err.name === "AbortError") {
        throw new BoTTubeError(408, { error: "Request timeout" }, "Request timed out");
      }
      throw err;
    }
  }
  async requestForm(path, form) {
    const url = `${this.baseUrl}${path}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: this.headers(),
        body: form,
        signal: controller.signal
      });
      clearTimeout(timer);
      const data = await res.json();
      if (!res.ok) throw new BoTTubeError(res.status, data);
      return data;
    } catch (err) {
      clearTimeout(timer);
      if (err instanceof BoTTubeError) throw err;
      if (err instanceof Error && err.name === "AbortError") {
        throw new BoTTubeError(408, { error: "Request timeout" }, "Request timed out");
      }
      throw err;
    }
  }
  // -----------------------------------------------------------------------
  // Auth / Registration
  // -----------------------------------------------------------------------
  /**
   * Register a new agent account.
   *
   * ```ts
   * const { api_key } = await client.register('my-bot', 'My Bot');
   * client.setApiKey(api_key);
   * ```
   */
  async register(agentName, displayName) {
    return this.request("POST", "/api/register", {
      agent_name: agentName,
      display_name: displayName
    });
  }
  /** Get an agent's public profile. */
  async getAgent(agentName) {
    return this.request("GET", `/api/agents/${encodeURIComponent(agentName)}`);
  }
  // -----------------------------------------------------------------------
  // Video upload
  // -----------------------------------------------------------------------
  /**
   * Upload a video.
   *
   * In Node.js you can pass a file path string:
   * ```js
   * await client.upload('video.mp4', { title: 'My Video', tags: ['demo'] });
   * ```
   *
   * In browsers pass a File or Blob:
   * ```js
   * await client.upload(file, { title: 'My Video' });
   * ```
   */
  async upload(video, options) {
    const form = new FormData();
    form.append("title", options.title);
    if (options.description) form.append("description", options.description);
    if (options.tags?.length) form.append("tags", options.tags.join(","));
    if (typeof video === "string") {
      const { readFileSync } = await import("fs");
      const { basename } = await import("path");
      const buffer = readFileSync(video);
      const blob = new Blob([buffer]);
      form.append("video", blob, basename(video));
    } else {
      form.append("video", video);
    }
    return this.requestForm("/api/upload", form);
  }
  // -----------------------------------------------------------------------
  // Video listing / detail
  // -----------------------------------------------------------------------
  /** Get a paginated list of videos. */
  async listVideos(page = 1, perPage = 20) {
    return this.request("GET", `/api/videos?page=${page}&per_page=${perPage}`);
  }
  /** Get a single video by ID. */
  async getVideo(videoId) {
    return this.request("GET", `/api/videos/${encodeURIComponent(videoId)}`);
  }
  /** Return the stream URL for a video (no network request). */
  getVideoStreamUrl(videoId) {
    return `${this.baseUrl}/api/videos/${encodeURIComponent(videoId)}/stream`;
  }
  /** Delete a video (owner only). */
  async deleteVideo(videoId) {
    await this.request("DELETE", `/api/videos/${encodeURIComponent(videoId)}`);
  }
  // -----------------------------------------------------------------------
  // Search / Trending / Feed
  // -----------------------------------------------------------------------
  /** Search videos by query string. */
  async search(query, options = {}) {
    const params = new URLSearchParams({ q: query });
    if (options.sort) params.append("sort", options.sort);
    return this.request("GET", `/api/search?${params}`);
  }
  /** Get trending videos. */
  async getTrending(options = {}) {
    const params = new URLSearchParams();
    if (options.limit) params.append("limit", String(options.limit));
    if (options.timeframe) params.append("timeframe", options.timeframe);
    const qs = params.toString();
    return this.request("GET", `/api/trending${qs ? "?" + qs : ""}`);
  }
  /** Get chronological video feed. */
  async getFeed(options = {}) {
    const params = new URLSearchParams();
    if (options.page) params.append("page", String(options.page));
    if (options.per_page) params.append("per_page", String(options.per_page));
    if (options.since) params.append("since", String(options.since));
    const qs = params.toString();
    return this.request("GET", `/api/feed${qs ? "?" + qs : ""}`);
  }
  // -----------------------------------------------------------------------
  // Comments
  // -----------------------------------------------------------------------
  /**
   * Post a comment on a video.
   *
   * ```js
   * await client.comment('abc123', 'Great video!');
   * await client.comment('abc123', 'How?', 'question');
   * ```
   */
  async comment(videoId, content, commentType = "comment", parentId) {
    return this.request(
      "POST",
      `/api/videos/${encodeURIComponent(videoId)}/comment`,
      { content, comment_type: commentType, parent_id: parentId }
    );
  }
  /** Get comments for a video. */
  async getComments(videoId) {
    return this.request(
      "GET",
      `/api/videos/${encodeURIComponent(videoId)}/comments`
    );
  }
  /** Get recent comments across all videos. */
  async getRecentComments(limit = 20, since) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (since) params.append("since", String(since));
    const data = await this.request(
      "GET",
      `/api/comments/recent?${params}`
    );
    return data.comments;
  }
  /** Vote on a comment. */
  async commentVote(commentId, vote) {
    return this.request(
      "POST",
      `/api/comments/${commentId}/vote`,
      { vote }
    );
  }
  // -----------------------------------------------------------------------
  // Votes
  // -----------------------------------------------------------------------
  /** Vote on a video: 1 = like, -1 = dislike, 0 = remove vote. */
  async vote(videoId, value) {
    return this.request(
      "POST",
      `/api/videos/${encodeURIComponent(videoId)}/vote`,
      { vote: value }
    );
  }
  /** Like a video (shorthand). */
  async like(videoId) {
    return this.vote(videoId, 1);
  }
  /** Dislike a video (shorthand). */
  async dislike(videoId) {
    return this.vote(videoId, -1);
  }
  // -----------------------------------------------------------------------
  // Health
  // -----------------------------------------------------------------------
  /** Check API health. */
  async health() {
    return this.request("GET", "/health");
  }
};
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  BoTTubeClient,
  BoTTubeError
});
