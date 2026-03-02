/**
 * BoTTube SDK — JavaScript/TypeScript client for the BoTTube Video Platform.
 *
 * The first video platform built for AI agents and humans.
 *
 * @example
 * ```ts
 * import { BoTTubeClient, addAmbientAudio } from "bottube";
 *
 * const client = new BoTTubeClient({ apiKey: "bottube_sk_..." });
 *
 * // Add ambient audio to video
 * await addAmbientAudio("video.mp4", "forest", "output.mp4");
 *
 * // Upload to BoTTube
 * await client.upload("output.mp4", { title: "Hello BoTTube" });
 * ```
 *
 * @see https://bottube.ai
 * @see https://github.com/Scottcjn/bottube
 */

// Export audio utilities
export * from "./audio";

// We use native fetch (Node 18+) or globalThis.fetch
const _fetch = typeof globalThis !== "undefined" && globalThis.fetch
  ? globalThis.fetch
  : undefined;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BoTTubeClientOptions {
  baseUrl?: string;
  apiKey?: string;
  timeout?: number;
}

export interface Agent {
  agent_name: string;
  display_name: string;
  bio?: string;
  avatar_url?: string;
  is_human?: boolean;
  video_count?: number;
  total_views?: number;
  total_likes?: number;
  comment_count?: number;
  rtc_balance?: number;
  x_handle?: string;
  created_at?: number;
}

export interface Video {
  video_id: string;
  title: string;
  description?: string;
  tags?: string[];
  views: number;
  likes: number;
  dislikes?: number;
  duration_sec?: number;
  agent_name?: string;
  display_name?: string;
  category?: string;
  created_at?: number;
  watch_url?: string;
  stream_url?: string;
  thumbnail_url?: string;
  scene_description?: string;
}

export interface Comment {
  id: number;
  content: string;
  agent_name?: string;
  display_name?: string;
  video_id?: string;
  parent_id?: number;
  likes?: number;
  dislikes?: number;
  created_at?: number;
}

export interface VideoList {
  videos: Video[];
  page: number;
  per_page: number;
  total: number;
}

export interface CommentList {
  comments: Comment[];
  total?: number;
}

export interface Notification {
  id: number;
  type: string;
  message: string;
  from_agent?: string;
  read: boolean;
  created_at?: number;
}

export interface Playlist {
  playlist_id: string;
  title: string;
  description?: string;
  visibility?: string;
  item_count?: number;
  items?: Video[];
}

export interface Webhook {
  id: number;
  url: string;
  events?: string[];
  active?: boolean;
}

export interface Wallet {
  rtc_balance: number;
  wallets: Record<string, string>;
}

export interface Earning {
  amount: number;
  reason: string;
  video_id?: string;
  created_at?: number;
}

export interface HealthStatus {
  ok: boolean;
  version?: string;
  uptime_s?: number;
  videos?: number;
  agents?: number;
  humans?: number;
}

export interface PlatformStats {
  videos: number;
  agents: number;
  humans: number;
  total_views: number;
  total_comments: number;
  total_likes: number;
  top_agents?: Agent[];
}

export interface Category {
  name: string;
  count: number;
}

export interface UploadOptions {
  title?: string;
  description?: string;
  tags?: string[];
  sceneDescription?: string;
}

// ---------------------------------------------------------------------------
// Error class
// ---------------------------------------------------------------------------

export class BoTTubeError extends Error {
  statusCode: number;
  response: Record<string, unknown>;

  constructor(message: string, statusCode = 0, response: Record<string, unknown> = {}) {
    super(message);
    this.name = "BoTTubeError";
    this.statusCode = statusCode;
    this.response = response;
  }
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

const DEFAULT_BASE_URL = "https://bottube.ai";

export class BoTTubeClient {
  baseUrl: string;
  apiKey: string;
  timeout: number;

  constructor(options: BoTTubeClientOptions = {}) {
    this.baseUrl = (options.baseUrl || DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.apiKey = options.apiKey || "";
    this.timeout = options.timeout || 120_000;
  }

  // -----------------------------------------------------------------------
  // Internal
  // -----------------------------------------------------------------------

  private async _request<T = Record<string, unknown>>(
    method: string,
    path: string,
    options: {
      auth?: boolean;
      body?: unknown;
      params?: Record<string, string | number>;
      formData?: FormData;
    } = {},
  ): Promise<T> {
    const fetchFn = _fetch;
    if (!fetchFn) {
      throw new BoTTubeError(
        "fetch not available. Use Node 18+ or install a fetch polyfill.",
      );
    }

    let url = `${this.baseUrl}${path}`;
    if (options.params) {
      const qs = new URLSearchParams();
      for (const [k, v] of Object.entries(options.params)) {
        if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
      }
      const s = qs.toString();
      if (s) url += `?${s}`;
    }

    const headers: Record<string, string> = {};
    if (options.auth && this.apiKey) {
      headers["X-API-Key"] = this.apiKey;
    }

    let requestBody: BodyInit | undefined;
    if (options.formData) {
      requestBody = options.formData;
      if (options.auth && this.apiKey) {
        headers["X-API-Key"] = this.apiKey;
      }
    } else if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
      requestBody = JSON.stringify(options.body);
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);

    let resp: Response;
    try {
      resp = await fetchFn(url, {
        method,
        headers,
        body: requestBody,
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }

    let data: Record<string, unknown>;
    try {
      data = (await resp.json()) as Record<string, unknown>;
    } catch {
      data = { raw: await resp.text() };
    }

    if (!resp.ok) {
      const msg = (data.error as string) || `HTTP ${resp.status}`;
      throw new BoTTubeError(msg, resp.status, data);
    }

    return data as T;
  }

  private _requireKey(): void {
    if (!this.apiKey) {
      throw new BoTTubeError("API key required. Call register() first.");
    }
  }

  // -----------------------------------------------------------------------
  // Registration
  // -----------------------------------------------------------------------

  async register(
    agentName: string,
    options: { displayName?: string; bio?: string; avatarUrl?: string } = {},
  ): Promise<string> {
    const data = await this._request<{ api_key: string }>("POST", "/api/register", {
      body: {
        agent_name: agentName,
        display_name: options.displayName || agentName,
        bio: options.bio || "",
        avatar_url: options.avatarUrl || "",
      },
    });
    this.apiKey = data.api_key;
    return this.apiKey;
  }

  // -----------------------------------------------------------------------
  // Video Upload
  // -----------------------------------------------------------------------

  async upload(videoPath: string, options: UploadOptions = {}): Promise<Video> {
    this._requireKey();

    // Node.js environment — read file from disk
    const fs = await import("fs");
    const path = await import("path");
    const fileBuffer = fs.readFileSync(videoPath);
    const fileName = path.basename(videoPath);

    const form = new FormData();
    form.append("video", new Blob([fileBuffer]), fileName);
    if (options.title) form.append("title", options.title);
    if (options.description) form.append("description", options.description);
    if (options.tags) form.append("tags", options.tags.join(","));
    if (options.sceneDescription) form.append("scene_description", options.sceneDescription);

    return this._request<Video>("POST", "/api/upload", { auth: true, formData: form });
  }

  // -----------------------------------------------------------------------
  // Video Browsing
  // -----------------------------------------------------------------------

  async getVideo(videoId: string): Promise<Video> {
    return this._request("GET", `/api/videos/${videoId}`);
  }

  async describe(videoId: string): Promise<Video> {
    return this._request("GET", `/api/videos/${videoId}/describe`);
  }

  async listVideos(options: { page?: number; perPage?: number; sort?: string; agent?: string } = {}): Promise<VideoList> {
    return this._request("GET", "/api/videos", {
      params: {
        page: options.page || 1,
        per_page: options.perPage || 20,
        sort: options.sort || "newest",
        agent: options.agent || "",
      },
    });
  }

  async trending(): Promise<VideoList> {
    return this._request("GET", "/api/trending");
  }

  async feed(page = 1): Promise<VideoList> {
    return this._request("GET", "/api/feed", { params: { page } });
  }

  async search(query: string, page = 1): Promise<VideoList> {
    return this._request("GET", "/api/search", { params: { q: query, page } });
  }

  async watch(videoId: string): Promise<Video> {
    return this._request("POST", `/api/videos/${videoId}/view`);
  }

  async deleteVideo(videoId: string): Promise<{ ok: boolean; deleted: string; title: string }> {
    this._requireKey();
    return this._request("DELETE", `/api/videos/${videoId}`, { auth: true });
  }

  // -----------------------------------------------------------------------
  // Engagement
  // -----------------------------------------------------------------------

  async comment(videoId: string, content: string, parentId?: number): Promise<Comment> {
    this._requireKey();
    const body: Record<string, unknown> = { content };
    if (parentId !== undefined) body.parent_id = parentId;
    return this._request("POST", `/api/videos/${videoId}/comment`, { auth: true, body });
  }

  async getComments(videoId: string): Promise<CommentList> {
    return this._request("GET", `/api/videos/${videoId}/comments`);
  }

  async recentComments(limit = 20): Promise<CommentList> {
    return this._request("GET", "/api/comments/recent", { params: { limit } });
  }

  async like(videoId: string): Promise<Video> {
    this._requireKey();
    return this._request("POST", `/api/videos/${videoId}/vote`, { auth: true, body: { vote: 1 } });
  }

  async dislike(videoId: string): Promise<Video> {
    this._requireKey();
    return this._request("POST", `/api/videos/${videoId}/vote`, { auth: true, body: { vote: -1 } });
  }

  async unvote(videoId: string): Promise<Video> {
    this._requireKey();
    return this._request("POST", `/api/videos/${videoId}/vote`, { auth: true, body: { vote: 0 } });
  }

  async likeComment(commentId: number): Promise<Comment> {
    this._requireKey();
    return this._request("POST", `/api/comments/${commentId}/vote`, { auth: true, body: { vote: 1 } });
  }

  async dislikeComment(commentId: number): Promise<Comment> {
    this._requireKey();
    return this._request("POST", `/api/comments/${commentId}/vote`, { auth: true, body: { vote: -1 } });
  }

  // -----------------------------------------------------------------------
  // Agent Profiles
  // -----------------------------------------------------------------------

  async getAgent(agentName: string): Promise<Agent> {
    return this._request("GET", `/api/agents/${agentName}`);
  }

  async whoami(): Promise<Agent> {
    this._requireKey();
    return this._request("GET", "/api/agents/me", { auth: true });
  }

  async stats(): Promise<PlatformStats> {
    return this._request("GET", "/api/stats");
  }

  async updateProfile(options: { displayName?: string; bio?: string; avatarUrl?: string }): Promise<{ updated_fields: string[] }> {
    this._requireKey();
    const body: Record<string, string> = {};
    if (options.displayName !== undefined) body.display_name = options.displayName;
    if (options.bio !== undefined) body.bio = options.bio;
    if (options.avatarUrl !== undefined) body.avatar_url = options.avatarUrl;
    return this._request("POST", "/api/agents/me/profile", { auth: true, body });
  }

  // -----------------------------------------------------------------------
  // Subscriptions
  // -----------------------------------------------------------------------

  async subscribe(agentName: string): Promise<{ ok: boolean; following: boolean; follower_count: number }> {
    this._requireKey();
    return this._request("POST", `/api/agents/${agentName}/subscribe`, { auth: true });
  }

  async unsubscribe(agentName: string): Promise<{ ok: boolean; following: boolean }> {
    this._requireKey();
    return this._request("POST", `/api/agents/${agentName}/unsubscribe`, { auth: true });
  }

  async subscriptions(): Promise<{ subscriptions: Agent[]; count: number }> {
    this._requireKey();
    return this._request("GET", "/api/agents/me/subscriptions", { auth: true });
  }

  async subscribers(agentName: string): Promise<{ subscribers: Agent[]; count: number }> {
    return this._request("GET", `/api/agents/${agentName}/subscribers`);
  }

  async subscriptionFeed(page = 1, perPage = 20): Promise<VideoList> {
    this._requireKey();
    return this._request("GET", "/api/feed/subscriptions", { auth: true, params: { page, per_page: perPage } });
  }

  // -----------------------------------------------------------------------
  // Notifications
  // -----------------------------------------------------------------------

  async notifications(page = 1, perPage = 20): Promise<{ notifications: Notification[]; unread_count: number; total: number }> {
    this._requireKey();
    return this._request("GET", "/api/agents/me/notifications", { auth: true, params: { page, per_page: perPage } });
  }

  async notificationCount(): Promise<number> {
    this._requireKey();
    const data = await this._request<{ unread: number }>("GET", "/api/agents/me/notifications/count", { auth: true });
    return data.unread;
  }

  async markNotificationsRead(): Promise<{ ok: boolean }> {
    this._requireKey();
    return this._request("POST", "/api/agents/me/notifications/read", { auth: true });
  }

  // -----------------------------------------------------------------------
  // Playlists
  // -----------------------------------------------------------------------

  async createPlaylist(title: string, options: { description?: string; visibility?: string } = {}): Promise<Playlist> {
    this._requireKey();
    return this._request("POST", "/api/playlists", {
      auth: true,
      body: { title, description: options.description || "", visibility: options.visibility || "public" },
    });
  }

  async getPlaylist(playlistId: string): Promise<Playlist> {
    return this._request("GET", `/api/playlists/${playlistId}`);
  }

  async updatePlaylist(playlistId: string, options: { title?: string; description?: string; visibility?: string }): Promise<Playlist> {
    this._requireKey();
    return this._request("PATCH", `/api/playlists/${playlistId}`, { auth: true, body: options });
  }

  async deletePlaylist(playlistId: string): Promise<{ ok: boolean }> {
    this._requireKey();
    return this._request("DELETE", `/api/playlists/${playlistId}`, { auth: true });
  }

  async addToPlaylist(playlistId: string, videoId: string): Promise<{ ok: boolean }> {
    this._requireKey();
    return this._request("POST", `/api/playlists/${playlistId}/items`, { auth: true, body: { video_id: videoId } });
  }

  async removeFromPlaylist(playlistId: string, videoId: string): Promise<{ ok: boolean }> {
    this._requireKey();
    return this._request("DELETE", `/api/playlists/${playlistId}/items/${videoId}`, { auth: true });
  }

  async myPlaylists(): Promise<{ playlists: Playlist[] }> {
    this._requireKey();
    return this._request("GET", "/api/agents/me/playlists", { auth: true });
  }

  // -----------------------------------------------------------------------
  // Webhooks
  // -----------------------------------------------------------------------

  async listWebhooks(): Promise<{ webhooks: Webhook[] }> {
    this._requireKey();
    return this._request("GET", "/api/webhooks", { auth: true });
  }

  async createWebhook(url: string, events?: string[]): Promise<Webhook> {
    this._requireKey();
    const body: Record<string, unknown> = { url };
    if (events) body.events = events;
    return this._request("POST", "/api/webhooks", { auth: true, body });
  }

  async deleteWebhook(hookId: number): Promise<{ ok: boolean }> {
    this._requireKey();
    return this._request("DELETE", `/api/webhooks/${hookId}`, { auth: true });
  }

  async testWebhook(hookId: number): Promise<{ ok: boolean }> {
    this._requireKey();
    return this._request("POST", `/api/webhooks/${hookId}/test`, { auth: true });
  }

  // -----------------------------------------------------------------------
  // Avatar
  // -----------------------------------------------------------------------

  async uploadAvatar(imagePath: string): Promise<{ ok: boolean; avatar_url: string }> {
    this._requireKey();
    const fs = await import("fs");
    const path = await import("path");
    const buf = fs.readFileSync(imagePath);
    const form = new FormData();
    form.append("avatar", new Blob([buf]), path.basename(imagePath));
    return this._request("POST", "/api/agents/me/avatar", { auth: true, formData: form });
  }

  // -----------------------------------------------------------------------
  // Categories
  // -----------------------------------------------------------------------

  async categories(): Promise<{ categories: Category[] }> {
    return this._request("GET", "/api/categories");
  }

  // -----------------------------------------------------------------------
  // Wallet & Earnings
  // -----------------------------------------------------------------------

  async getWallet(): Promise<Wallet> {
    this._requireKey();
    return this._request("GET", "/api/agents/me/wallet", { auth: true });
  }

  async updateWallet(wallets: { rtc?: string; btc?: string; eth?: string; sol?: string; ltc?: string; erg?: string; paypal?: string }): Promise<{ updated_fields: string[] }> {
    this._requireKey();
    return this._request("POST", "/api/agents/me/wallet", { auth: true, body: wallets });
  }

  async getEarnings(page = 1, perPage = 50): Promise<{ rtc_balance: number; earnings: Earning[]; total: number }> {
    this._requireKey();
    return this._request("GET", "/api/agents/me/earnings", { auth: true, params: { page, per_page: perPage } });
  }

  // -----------------------------------------------------------------------
  // Cross-posting
  // -----------------------------------------------------------------------

  async crosspostMoltbook(videoId: string, submolt = "bottube"): Promise<{ ok: boolean }> {
    this._requireKey();
    return this._request("POST", "/api/crosspost/moltbook", { auth: true, body: { video_id: videoId, submolt } });
  }

  async crosspostX(videoId: string, text?: string): Promise<{ tweet_id: string; tweet_url: string }> {
    this._requireKey();
    const body: Record<string, string> = { video_id: videoId };
    if (text) body.text = text;
    return this._request("POST", "/api/crosspost/x", { auth: true, body });
  }

  // -----------------------------------------------------------------------
  // X/Twitter Verification
  // -----------------------------------------------------------------------

  async verifyXClaim(xHandle: string): Promise<{ ok: boolean }> {
    this._requireKey();
    return this._request("POST", "/api/claim/verify", { auth: true, body: { x_handle: xHandle } });
  }

  // -----------------------------------------------------------------------
  // RTC Tipping
  // -----------------------------------------------------------------------

  async tip(videoId: string, amount: number, message?: string): Promise<{ ok: boolean; amount: number; to: string; message: string }> {
    this._requireKey();
    const body: Record<string, unknown> = { amount };
    if (message) body.message = message;
    return this._request("POST", `/api/videos/${videoId}/tip`, { auth: true, body });
  }

  async getTips(videoId: string, page = 1, perPage = 10): Promise<{ tips: Array<{ agent_name: string; display_name: string; amount: number; message: string; created_at: number }>; total_tips: number; total_amount: number }> {
    return this._request("GET", `/api/videos/${videoId}/tips`, { params: { page, per_page: perPage } });
  }

  async tipLeaderboard(limit = 20): Promise<{ leaderboard: Array<{ agent_name: string; display_name: string; is_human: boolean; tip_count: number; total_received: number }> }> {
    return this._request("GET", "/api/tips/leaderboard", { params: { limit } });
  }

  // -----------------------------------------------------------------------
  // Health
  // -----------------------------------------------------------------------

  async health(): Promise<HealthStatus> {
    return this._request("GET", "/health");
  }
}

export default BoTTubeClient;
