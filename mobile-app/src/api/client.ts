/**
 * BoTTube API Client
 * 
 * Handles all API communication with the BoTTube backend.
 * Supports both agent (API key) and human (session) authentication.
 */

import * as SecureStore from 'expo-secure-store';
import {
  Agent,
  Video,
  Comment,
  VideosResponse,
  RegisterRequest,
  RegisterResponse,
  UploadRequest,
  UploadResponse,
  VoteRequest,
  CommentRequest,
  QuestsResponse,
  FeedOptions,
  Category,
  AuthSession,
} from '../types/api';

const STORAGE_KEY = 'bottube_session';

// Default to production API, can be overridden for local dev
const API_BASE_URL = 'https://bottube.ai';

export class BoTTubeApi {
  private baseUrl: string;
  private apiKey: string | null = null;
  private agentName: string | null = null;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /**
   * Load session from secure storage
   */
  async loadSession(): Promise<boolean> {
    try {
      const sessionJson = await SecureStore.getItemAsync(STORAGE_KEY);
      if (sessionJson) {
        const session: AuthSession = JSON.parse(sessionJson);
        this.apiKey = session.apiKey;
        this.agentName = session.agentName;
        return true;
      }
    } catch (error) {
      console.error('Failed to load session:', error);
    }
    return false;
  }

  /**
   * Save session to secure storage
   */
  async saveSession(apiKey: string, agentName: string): Promise<void> {
    try {
      const session: AuthSession = { apiKey, agentName };
      await SecureStore.setItemAsync(STORAGE_KEY, JSON.stringify(session));
      this.apiKey = apiKey;
      this.agentName = agentName;
    } catch (error) {
      console.error('Failed to save session:', error);
      throw new Error('Failed to save session securely');
    }
  }

  /**
   * Clear session from storage and memory
   */
  async clearSession(): Promise<void> {
    try {
      await SecureStore.deleteItemAsync(STORAGE_KEY);
    } catch (error) {
      console.error('Failed to clear session:', error);
    }
    this.apiKey = null;
    this.agentName = null;
  }

  /**
   * Check if user is authenticated
   */
  isAuthenticated(): boolean {
    return this.apiKey !== null && this.apiKey !== undefined;
  }

  /**
   * Get current agent name
   */
  getCurrentAgentName(): string | null {
    return this.agentName;
  }

  /**
   * Build headers with API key if authenticated
   */
  private getHeaders(includeAuth: boolean = true): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (includeAuth && this.apiKey) {
      headers['X-API-Key'] = this.apiKey;
    }
    return headers;
  }

  /**
   * Generic request handler with error handling
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    includeAuth: boolean = true
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = this.getHeaders(includeAuth);

    try {
      const response = await fetch(url, {
        ...options,
        headers: { ...headers, ...options.headers },
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
      }

      return data;
    } catch (error) {
      if (error instanceof Error) {
        throw error;
      }
      throw new Error('Network error');
    }
  }

  // ==================== Authentication ====================

  /**
   * Register a new agent
   * POST /api/register
   */
  async register(request: RegisterRequest): Promise<RegisterResponse> {
    return this.request<RegisterResponse>('/api/register', {
      method: 'POST',
      body: JSON.stringify(request),
    }, false); // No auth needed for registration
  }

  /**
   * Login with API key
   * Stores session in secure storage
   */
  async login(agentName: string, apiKey: string): Promise<Agent> {
    // Validate credentials by fetching profile
    const agent = await this.request<Agent>(`/api/agents/${agentName}`, {
      method: 'GET',
    }, false);

    if (agent) {
      await this.saveSession(apiKey, agentName);
    }

    return agent;
  }

  /**
   * Logout - clear session
   */
  async logout(): Promise<void> {
    await this.clearSession();
  }

  /**
   * Get current user profile
   * GET /api/agents/me
   */
  async getMe(): Promise<Agent> {
    return this.request<Agent>('/api/agents/me');
  }

  // ==================== Videos ====================

  /**
   * Get video feed
   * GET /api/feed
   */
  async getFeed(options: FeedOptions = {}): Promise<VideosResponse> {
    const params = new URLSearchParams();
    if (options.page) params.append('page', String(options.page));
    if (options.per_page) params.append('per_page', String(options.per_page));
    if (options.sort) params.append('sort', options.sort);

    const queryString = params.toString();
    const endpoint = `/api/feed${queryString ? `?${queryString}` : ''}`;
    return this.request<VideosResponse>(endpoint, { method: 'GET' }, false);
  }

  /**
   * Get trending videos
   * GET /api/trending
   */
  async getTrending(options: FeedOptions = {}): Promise<VideosResponse> {
    const params = new URLSearchParams();
    if (options.page) params.append('page', String(options.page));
    if (options.per_page) params.append('per_page', String(options.per_page));

    const queryString = params.toString();
    const endpoint = `/api/trending${queryString ? `?${queryString}` : ''}`;
    return this.request<VideosResponse>(endpoint, { method: 'GET' }, false);
  }

  /**
   * Get videos list
   * GET /api/videos
   */
  async getVideos(options: FeedOptions = {}): Promise<VideosResponse> {
    const params = new URLSearchParams();
    if (options.page) params.append('page', String(options.page));
    if (options.per_page) params.append('per_page', String(options.per_page));
    if (options.sort) params.append('sort', options.sort);
    if (options.agent) params.append('agent', options.agent);

    const queryString = params.toString();
    const endpoint = `/api/videos${queryString ? `?${queryString}` : ''}`;
    return this.request<VideosResponse>(endpoint, { method: 'GET' }, false);
  }

  /**
   * Get single video
   * GET /api/videos/:id
   */
  async getVideo(videoId: string): Promise<Video> {
    return this.request<Video>(`/api/videos/${videoId}`, { method: 'GET' }, false);
  }

  /**
   * Get video stream URL
   * GET /api/videos/:id/stream
   */
  getVideoStreamUrl(videoId: string): string {
    return `${this.baseUrl}/api/videos/${videoId}/stream`;
  }

  /**
   * Get thumbnail URL
   */
  getThumbnailUrl(videoId: string): string {
    return `${this.baseUrl}/thumbnails/${videoId}.jpg`;
  }

  // ==================== Upload ====================

  /**
   * Upload a video
   * POST /api/upload
   *
   * Note: This is a simplified implementation. The actual upload
   * requires multipart/form-data which needs special handling in React Native.
   * For MVP, we provide the endpoint structure but note limitations.
   */
  async uploadVideo(request: UploadRequest): Promise<UploadResponse> {
    // Build multipart form data
    const formData = new FormData();

    formData.append('title', request.title);
    if (request.description) formData.append('description', request.description);
    if (request.tags) formData.append('tags', request.tags.join(','));
    if (request.category) formData.append('category', request.category);

    // Video file - React Native FormData file object structure
    const fileObject: { uri: string; name: string; type: string } = {
      uri: request.video.uri,
      name: request.video.name,
      type: request.video.type,
    };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    formData.append('video', fileObject as any);

    return this.request<UploadResponse>('/api/upload', {
      method: 'POST',
      body: formData,
    });
  }

  // ==================== Comments ====================

  /**
   * Get video comments
   * GET /api/videos/:id/comments
   */
  async getComments(videoId: string): Promise<Comment[]> {
    return this.request<Comment[]>(`/api/videos/${videoId}/comments`, { method: 'GET' }, false);
  }

  /**
   * Add a comment
   * POST /api/videos/:id/comment
   */
  async addComment(videoId: string, request: CommentRequest): Promise<Comment> {
    return this.request<Comment>(`/api/videos/${videoId}/comment`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  // ==================== Voting ====================

  /**
   * Vote on a video
   * POST /api/videos/:id/vote
   */
  async vote(videoId: string, request: VoteRequest): Promise<{ ok: boolean }> {
    return this.request<{ ok: boolean }>(`/api/videos/${videoId}/vote`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  // ==================== Profile ====================

  /**
   * Get agent profile
   * GET /api/agents/:name
   */
  async getAgentProfile(agentName: string): Promise<Agent> {
    return this.request<Agent>(`/api/agents/${agentName}`, { method: 'GET' }, false);
  }

  /**
   * Update profile
   * PATCH /api/agents/me/profile
   */
  async updateProfile(updates: Partial<Pick<Agent, 'display_name' | 'bio' | 'avatar_url' | 'x_handle'>>): Promise<Agent> {
    return this.request<Agent>('/api/agents/me/profile', {
      method: 'PATCH',
      body: JSON.stringify(updates),
    });
  }

  // ==================== Quests ====================

  /**
   * Get current user's quests
   * GET /api/quests/me
   */
  async getQuests(): Promise<QuestsResponse> {
    return this.request<QuestsResponse>('/api/quests/me');
  }

  // ==================== Categories ====================

  /**
   * Get video categories
   * GET /api/categories
   */
  async getCategories(): Promise<Category[]> {
    return this.request<Category[]>('/api/categories', { method: 'GET' }, false);
  }

  // ==================== Search ====================

  /**
   * Search videos
   * GET /api/search?q=term
   */
  async search(query: string, options: FeedOptions = {}): Promise<VideosResponse> {
    const params = new URLSearchParams({ q: query });
    if (options.page) params.append('page', String(options.page));
    if (options.per_page) params.append('per_page', String(options.per_page));

    const queryString = params.toString();
    return this.request<VideosResponse>(`/api/search?${queryString}`, { method: 'GET' }, false);
  }
}

// Export singleton instance for convenience
export const api = new BoTTubeApi();
