import type { HttpClient } from '../client';
import type { Video, PaginatedResponse, ListOptions, VoteRequest, CommentRequest, Comment } from '../types';

/**
 * Videos API client
 * Handles video-related operations
 */
export class VideosApi {
  private client: HttpClient;

  constructor(client: HttpClient) {
    this.client = client;
  }

  /**
   * List videos with pagination and filtering
   */
  async list(options: ListOptions = {}): Promise<PaginatedResponse<Video>> {
    return this.client.get('/api/videos', options);
  }

  /**
   * Get a single video by ID
   */
  async get(videoId: string): Promise<Video> {
    return this.client.get(`/api/videos/${videoId}`);
  }

  /**
   * Get video stream URL
   */
  async getStreamUrl(videoId: string): Promise<string> {
    return `${this.client.getBaseUrl()}/api/videos/${videoId}/stream`;
  }

  /**
   * Increment video view count
   */
  async recordView(videoId: string): Promise<void> {
    await this.client.post(`/api/videos/${videoId}/view`);
  }

  /**
   * Vote on a video (like/dislike)
   */
  async vote(videoId: string, vote: 1 | -1): Promise<void> {
    const body: VoteRequest = { vote };
    await this.client.post(`/api/videos/${videoId}/vote`, body);
  }

  /**
   * Like a video
   */
  async like(videoId: string): Promise<void> {
    await this.vote(videoId, 1);
  }

  /**
   * Dislike a video
   */
  async dislike(videoId: string): Promise<void> {
    await this.vote(videoId, -1);
  }

  /**
   * Add a comment to a video
   */
  async comment(videoId: string, content: string): Promise<Comment> {
    const body: CommentRequest = { content };
    return this.client.post(`/api/videos/${videoId}/comment`, body);
  }

  /**
   * Get comments for a video
   */
  async getComments(videoId: string, page = 1, perPage = 20): Promise<PaginatedResponse<Comment>> {
    return this.client.get(`/api/videos/${videoId}/comments`, { page, per_page: perPage });
  }

  /**
   * Delete a video (owner only)
   */
  async delete(videoId: string): Promise<void> {
    await this.client.delete(`/api/videos/${videoId}`);
  }

  /**
   * Get video analytics (owner only)
   */
  async getAnalytics(videoId: string): Promise<unknown> {
    return this.client.get(`/api/videos/${videoId}/analytics`);
  }

  /**
   * Get video tips
   */
  async getTips(videoId: string): Promise<unknown> {
    return this.client.get(`/api/videos/${videoId}/tips`);
  }

  /**
   * Send a tip for a video
   */
  async tip(videoId: string, amount: number, currency: string): Promise<void> {
    await this.client.post(`/api/videos/${videoId}/tip`, { amount, currency });
  }
}
