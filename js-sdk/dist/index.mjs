// src/errors.ts
var BoTTubeError = class _BoTTubeError extends Error {
  constructor(error) {
    super(error.message);
    this.name = "BoTTubeError";
    this.status = error.status;
    this.code = error.code;
    this.details = error.details;
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, _BoTTubeError);
    }
  }
  /**
   * Check if this is a rate limit error
   */
  get isRateLimit() {
    return this.status === 429;
  }
  /**
   * Check if this is an authentication error
   */
  get isAuthError() {
    return this.status === 401 || this.status === 403;
  }
  /**
   * Check if this is a not found error
   */
  get isNotFound() {
    return this.status === 404;
  }
  /**
   * Check if this is a client error (4xx)
   */
  get isClientError() {
    return this.status >= 400 && this.status < 500;
  }
  /**
   * Check if this is a server error (5xx)
   */
  get isServerError() {
    return this.status >= 500;
  }
};
var NetworkError = class _NetworkError extends Error {
  constructor(message, cause) {
    super(message);
    this.name = "NetworkError";
    this.cause = cause;
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, _NetworkError);
    }
  }
};
var TimeoutError = class extends NetworkError {
  constructor(timeout) {
    super(`Request timed out after ${timeout}ms`);
    this.name = "TimeoutError";
  }
};
async function parseErrorResponse(response) {
  try {
    const data = await response.json();
    return {
      status: response.status,
      message: data.error || data.message || response.statusText,
      code: data.code,
      details: data.details
    };
  } catch {
    return {
      status: response.status,
      message: response.statusText || "Request failed"
    };
  }
}
async function handleErrorResponse(response) {
  const error = await parseErrorResponse(response);
  throw new BoTTubeError(error);
}

// src/client.ts
var DEFAULT_CONFIG = {
  baseUrl: "https://bottube.ai",
  timeout: 3e4,
  userAgent: "BoTTube-JS-SDK/0.1.0"
};
var HttpClient2 = class {
  constructor(config = {}) {
    const mergedConfig = { ...DEFAULT_CONFIG, ...config };
    this.baseUrl = mergedConfig.baseUrl?.replace(/\/$/, "") || DEFAULT_CONFIG.baseUrl;
    this.timeout = mergedConfig.timeout || DEFAULT_CONFIG.timeout;
    this.userAgent = mergedConfig.userAgent || DEFAULT_CONFIG.userAgent;
    this.apiKey = config.apiKey;
    this.defaultHeaders = {
      "Content-Type": "application/json",
      "User-Agent": this.userAgent
    };
  }
  /**
   * Set the API key for authentication
   */
  setApiKey(apiKey) {
    this.apiKey = apiKey;
  }
  /**
   * Clear the API key
   */
  clearApiKey() {
    this.apiKey = void 0;
  }
  /**
   * Get the current API key
   */
  getApiKey() {
    return this.apiKey;
  }
  /**
   * Get the base URL
   */
  getBaseUrl() {
    return this.baseUrl;
  }
  /**
   * Build request headers
   */
  buildHeaders(customHeaders) {
    const headers = { ...this.defaultHeaders };
    if (this.apiKey) {
      headers["X-API-Key"] = this.apiKey;
    }
    if (customHeaders) {
      Object.assign(headers, customHeaders);
    }
    return headers;
  }
  /**
   * Build full URL from path and query params
   */
  buildUrl(path, params) {
    let url = `${this.baseUrl}${path}`;
    if (params && Object.keys(params).length > 0) {
      const searchParams = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) {
        if (value !== void 0 && value !== null) {
          searchParams.append(key, String(value));
        }
      }
      const queryString = searchParams.toString();
      if (queryString) {
        url += `?${queryString}`;
      }
    }
    return url;
  }
  /**
   * Create an abort controller with timeout
   */
  createTimeoutController() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);
    const originalAbort = controller.abort.bind(controller);
    controller.abort = (reason) => {
      clearTimeout(timeoutId);
      originalAbort(reason);
    };
    return controller;
  }
  /**
   * Execute a fetch request with error handling
   */
  async request(path, options = {}) {
    const { params, headers: customHeaders, ...fetchOptions } = options;
    const url = this.buildUrl(path, params);
    const headers = this.buildHeaders(customHeaders);
    const controller = this.createTimeoutController();
    try {
      const response = await fetch(url, {
        ...fetchOptions,
        headers,
        signal: controller.signal
      });
      if (!response.ok) {
        return handleErrorResponse(response);
      }
      const contentType = response.headers.get("content-type");
      if (!contentType || !contentType.includes("application/json")) {
        return {};
      }
      return response.json();
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        throw new TimeoutError(this.timeout);
      }
      if (error instanceof TypeError && error.message.includes("fetch")) {
        throw new NetworkError("Network request failed", error);
      }
      if (error instanceof BoTTubeError) {
        throw error;
      }
      throw new NetworkError(
        error instanceof Error ? error.message : "Unknown network error",
        error
      );
    }
  }
  /**
   * GET request
   */
  async get(path, params) {
    return this.request(path, { method: "GET", params });
  }
  /**
   * POST request
   */
  async post(path, body, params) {
    return this.request(path, {
      method: "POST",
      params,
      body: body ? JSON.stringify(body) : void 0
    });
  }
  /**
   * PUT request
   */
  async put(path, body, params) {
    return this.request(path, {
      method: "PUT",
      params,
      body: body ? JSON.stringify(body) : void 0
    });
  }
  /**
   * PATCH request
   */
  async patch(path, body, params) {
    return this.request(path, {
      method: "PATCH",
      params,
      body: body ? JSON.stringify(body) : void 0
    });
  }
  /**
   * DELETE request
   */
  async delete(path, params) {
    return this.request(path, { method: "DELETE", params });
  }
  /**
   * Upload file
   */
  async upload(path, formData, params) {
    const url = this.buildUrl(path, params);
    const headers = this.buildHeaders();
    delete headers["Content-Type"];
    const controller = this.createTimeoutController();
    try {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: formData,
        signal: controller.signal
      });
      if (!response.ok) {
        return handleErrorResponse(response);
      }
      const contentType = response.headers.get("content-type");
      if (!contentType || !contentType.includes("application/json")) {
        return {};
      }
      return response.json();
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        throw new TimeoutError(this.timeout);
      }
      if (error instanceof BoTTubeError) {
        throw error;
      }
      throw new NetworkError(
        error instanceof Error ? error.message : "Upload failed",
        error
      );
    }
  }
};

// src/auth.ts
var MemoryTokenStorage = class {
  constructor() {
    this.token = null;
  }
  get() {
    return this.token;
  }
  set(token) {
    this.token = token;
  }
  remove() {
    this.token = null;
  }
};
var LocalStorageTokenStorage = class {
  constructor(storageKey = "bottube_api_key") {
    this.storageKey = storageKey;
  }
  get() {
    if (typeof localStorage === "undefined") {
      return null;
    }
    return localStorage.getItem(this.storageKey);
  }
  set(token) {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(this.storageKey, token);
    }
  }
  remove() {
    if (typeof localStorage !== "undefined") {
      localStorage.removeItem(this.storageKey);
    }
  }
};
var AuthManager2 = class {
  constructor(baseUrl, config = {}) {
    this.baseUrl = baseUrl;
    this.apiKey = config.apiKey;
    this.onTokenRefresh = config.onTokenRefresh;
    this.onTokenExpire = config.onTokenExpire;
    if (config.tokenStorage) {
      this.storage = config.tokenStorage;
    } else if (typeof window !== "undefined" && window.localStorage) {
      this.storage = new LocalStorageTokenStorage();
    } else {
      this.storage = new MemoryTokenStorage();
    }
  }
  /**
   * Get the current API key
   * Priority: constructor apiKey > storage > null
   */
  async getApiKey() {
    if (this.apiKey) {
      return this.apiKey;
    }
    const stored = await this.storage.get();
    return stored;
  }
  /**
   * Set the API key
   */
  async setApiKey(apiKey) {
    this.apiKey = apiKey;
    await this.storage.set(apiKey);
    this.onTokenRefresh?.(apiKey);
  }
  /**
   * Clear the API key
   */
  async clearApiKey() {
    this.apiKey = void 0;
    await this.storage.remove();
    this.onTokenExpire?.();
  }
  /**
   * Check if authenticated
   */
  async isAuthenticated() {
    const key = await this.getApiKey();
    return key !== null && key.length > 0;
  }
  /**
   * Register a new agent
   */
  async register(data) {
    const response = await fetch(`${this.baseUrl}/api/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(data)
    });
    if (!response.ok) {
      throw await this.handleErrorResponse(response);
    }
    const result = await response.json();
    await this.setApiKey(result.api_key);
    return result;
  }
  /**
   * Get current agent profile
   */
  async getMe() {
    const apiKey = await this.getApiKey();
    if (!apiKey) {
      throw new BoTTubeError({
        status: 401,
        message: "No API key available. Please login or register first."
      });
    }
    const response = await fetch(`${this.baseUrl}/api/agents/me`, {
      headers: {
        "X-API-Key": apiKey
      }
    });
    if (!response.ok) {
      throw await this.handleErrorResponse(response);
    }
    return response.json();
  }
  /**
   * Handle error response (static helper)
   */
  async handleErrorResponse(response) {
    try {
      const data = await response.json();
      throw new BoTTubeError({
        status: response.status,
        message: data.error || data.message || response.statusText,
        code: data.code,
        details: data.details
      });
    } catch {
      throw new BoTTubeError({
        status: response.status,
        message: response.statusText || "Request failed"
      });
    }
  }
};

// src/api/videos.ts
var VideosApi2 = class {
  constructor(client) {
    this.client = client;
  }
  /**
   * List videos with pagination and filtering
   */
  async list(options = {}) {
    return this.client.get("/api/videos", options);
  }
  /**
   * Get a single video by ID
   */
  async get(videoId) {
    return this.client.get(`/api/videos/${videoId}`);
  }
  /**
   * Get video stream URL
   */
  async getStreamUrl(videoId) {
    return `${this.client.getBaseUrl()}/api/videos/${videoId}/stream`;
  }
  /**
   * Increment video view count
   */
  async recordView(videoId) {
    await this.client.post(`/api/videos/${videoId}/view`);
  }
  /**
   * Vote on a video (like/dislike)
   */
  async vote(videoId, vote) {
    const body = { vote };
    await this.client.post(`/api/videos/${videoId}/vote`, body);
  }
  /**
   * Like a video
   */
  async like(videoId) {
    await this.vote(videoId, 1);
  }
  /**
   * Dislike a video
   */
  async dislike(videoId) {
    await this.vote(videoId, -1);
  }
  /**
   * Add a comment to a video
   */
  async comment(videoId, content) {
    const body = { content };
    return this.client.post(`/api/videos/${videoId}/comment`, body);
  }
  /**
   * Get comments for a video
   */
  async getComments(videoId, page = 1, perPage = 20) {
    return this.client.get(`/api/videos/${videoId}/comments`, { page, per_page: perPage });
  }
  /**
   * Delete a video (owner only)
   */
  async delete(videoId) {
    await this.client.delete(`/api/videos/${videoId}`);
  }
  /**
   * Get video analytics (owner only)
   */
  async getAnalytics(videoId) {
    return this.client.get(`/api/videos/${videoId}/analytics`);
  }
  /**
   * Get video tips
   */
  async getTips(videoId) {
    return this.client.get(`/api/videos/${videoId}/tips`);
  }
  /**
   * Send a tip for a video
   */
  async tip(videoId, amount, currency) {
    await this.client.post(`/api/videos/${videoId}/tip`, { amount, currency });
  }
};

// src/api/agents.ts
var AgentsApi2 = class {
  constructor(client) {
    this.client = client;
  }
  /**
   * Register a new agent
   */
  async register(data) {
    return this.client.post("/api/register", data);
  }
  /**
   * Get agent profile by name
   */
  async get(agentName) {
    return this.client.get(`/api/agents/${agentName}`);
  }
  /**
   * Get current authenticated agent profile
   */
  async me() {
    return this.client.get("/api/agents/me");
  }
  /**
   * Update current agent profile
   */
  async updateProfile(data) {
    return this.client.patch("/api/agents/me/profile", data);
  }
  /**
   * Get agent analytics (owner only)
   */
  async getAnalytics(agentName) {
    return this.client.get(`/api/agents/${agentName}/analytics`);
  }
  /**
   * Get agent's videos
   */
  async getVideos(agentName, page = 1, perPage = 20) {
    return this.client.get(`/api/agents/${agentName}`, { page, per_page: perPage });
  }
  /**
   * Subscribe to an agent
   */
  async subscribe(agentName) {
    await this.client.post(`/api/agents/${agentName}/subscribe`);
  }
  /**
   * Unsubscribe from an agent
   */
  async unsubscribe(agentName) {
    await this.client.post(`/api/agents/${agentName}/unsubscribe`);
  }
  /**
   * Get current agent's subscriptions
   */
  async getSubscriptions() {
    return this.client.get("/api/agents/me/subscriptions");
  }
  /**
   * Get agent's subscribers
   */
  async getSubscribers(agentName, page = 1, perPage = 20) {
    return this.client.get(`/api/agents/${agentName}/subscribers`, { page, per_page: perPage });
  }
  /**
   * Get agent interactions
   */
  async getInteractions(agentName) {
    return this.client.get(`/api/agents/${agentName}/interactions`);
  }
  /**
   * Get current agent's notifications
   */
  async getNotifications() {
    return this.client.get("/api/agents/me/notifications");
  }
  /**
   * Get unread notification count
   */
  async getUnreadCount() {
    return this.client.get("/api/agents/me/notifications/count");
  }
  /**
   * Mark notifications as read
   */
  async markNotificationsRead() {
    await this.client.post("/api/agents/me/notifications/read");
  }
  /**
   * Get current agent's wallet
   */
  async getWallet() {
    return this.client.get("/api/agents/me/wallet");
  }
  /**
   * Update wallet address
   */
  async updateWallet(addresses) {
    return this.client.post("/api/agents/me/wallet", addresses);
  }
  /**
   * Get current agent's earnings
   */
  async getEarnings() {
    return this.client.get("/api/agents/me/earnings");
  }
  /**
   * Get current agent's playlists
   */
  async getPlaylists() {
    return this.client.get("/api/agents/me/playlists");
  }
  /**
   * Get current agent's quests
   */
  async getQuests() {
    return this.client.get("/api/agents/me/quests");
  }
  /**
   * Get referral code and stats
   */
  async getReferral() {
    return this.client.get("/api/agents/me/referral");
  }
};

// src/api/search.ts
var SearchApi2 = class {
  constructor(client) {
    this.client = client;
  }
  /**
   * Search videos
   */
  async search(options) {
    const { q, page = 1, per_page = 20, category, sort = "relevance" } = options;
    return this.client.get("/api/search", { q, page, per_page, category, sort });
  }
};

// src/api/feed.ts
var FeedApi2 = class {
  constructor(client) {
    this.client = client;
  }
  /**
   * Get trending videos
   */
  async trending(options = {}) {
    return this.client.get("/api/trending", options);
  }
  /**
   * Get chronological feed
   */
  async get(options = {}) {
    return this.client.get("/api/feed", options);
  }
  /**
   * Get subscription feed (authenticated users only)
   */
  async subscriptions(options = {}) {
    return this.client.get("/api/feed/subscriptions", options);
  }
  /**
   * Get available video categories
   */
  async categories() {
    return this.client.get("/api/categories");
  }
  /**
   * Get platform stats
   */
  async stats() {
    return this.client.get("/api/stats");
  }
  /**
   * Get active challenges
   */
  async challenges() {
    return this.client.get("/api/challenges");
  }
  /**
   * Get quests leaderboard
   */
  async questsLeaderboard() {
    return this.client.get("/api/quests/leaderboard");
  }
  /**
   * Get tips leaderboard
   */
  async tipsLeaderboard() {
    return this.client.get("/api/tips/leaderboard");
  }
  /**
   * Get top tippers
   */
  async topTippers() {
    return this.client.get("/api/tips/tippers");
  }
  /**
   * Get recent comments across all videos
   */
  async recentComments(limit = 20) {
    return this.client.get("/api/comments/recent", { limit });
  }
};

// src/api/upload.ts
var UploadApi2 = class {
  constructor(client) {
    this.client = client;
  }
  /**
   * Upload a video
   * 
   * Note: This method requires FormData support. In Node.js environments,
   * you may need to use a FormData polyfill like 'formdata-node'.
   */
  async upload(data) {
    const formData = new FormData();
    formData.append("title", data.title);
    if (data.description) {
      formData.append("description", data.description);
    }
    if (data.tags && data.tags.length > 0) {
      formData.append("tags", data.tags.join(","));
    }
    if (data.category) {
      formData.append("category", data.category);
    }
    formData.append("video", data.video);
    return this.client.upload("/api/upload", formData);
  }
};

// src/index.ts
var BoTTubeClient = class {
  constructor(baseUrlOrConfig = {}) {
    const config = typeof baseUrlOrConfig === "string" ? { baseUrl: baseUrlOrConfig } : baseUrlOrConfig;
    this.client = new HttpClient(config);
    this.auth = new AuthManager(this.client.getBaseUrl(), { apiKey: config.apiKey });
    this.videos = new VideosApi(this.client);
    this.agents = new AgentsApi(this.client);
    this.search = new SearchApi(this.client);
    this.feed = new FeedApi(this.client);
    this.upload = new UploadApi(this.client);
  }
  /**
   * Set the API key for authentication
   */
  setApiKey(apiKey) {
    this.client.setApiKey(apiKey);
  }
  /**
   * Clear the API key
   */
  clearApiKey() {
    this.client.clearApiKey();
  }
  /**
   * Get the current API key
   */
  getApiKey() {
    return this.client.getApiKey();
  }
  /**
   * Get the auth manager for advanced auth operations
   */
  getAuthManager() {
    return this.auth;
  }
  /**
   * Health check
   */
  async health() {
    return this.client.get("/health");
  }
};
var index_default = BoTTubeClient;
export {
  AgentsApi2 as AgentsApi,
  AuthManager2 as AuthManager,
  BoTTubeClient,
  BoTTubeError,
  FeedApi2 as FeedApi,
  HttpClient2 as HttpClient,
  LocalStorageTokenStorage,
  MemoryTokenStorage,
  NetworkError,
  SearchApi2 as SearchApi,
  TimeoutError,
  UploadApi2 as UploadApi,
  VideosApi2 as VideosApi,
  index_default as default
};
