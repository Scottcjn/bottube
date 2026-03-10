import type { HttpClient } from '../client';
import type { Video, PaginatedResponse, ListOptions } from '../types';

/**
 * Feed API client
 * Handles video feed and trending operations
 */
export class FeedApi {
  private client: HttpClient;

  constructor(client: HttpClient) {
    this.client = client;
  }

  /**
   * Get trending videos
   */
  async trending(options: ListOptions = {}): Promise<PaginatedResponse<Video>> {
    return this.client.get('/api/trending', options);
  }

  /**
   * Get chronological feed
   */
  async get(options: ListOptions = {}): Promise<PaginatedResponse<Video>> {
    return this.client.get('/api/feed', options);
  }

  /**
   * Get subscription feed (authenticated users only)
   */
  async subscriptions(options: ListOptions = {}): Promise<PaginatedResponse<Video>> {
    return this.client.get('/api/feed/subscriptions', options);
  }

  /**
   * Get available video categories
   */
  async categories(): Promise<unknown[]> {
    return this.client.get('/api/categories');
  }

  /**
   * Get platform stats
   */
  async stats(): Promise<unknown> {
    return this.client.get('/api/stats');
  }

  /**
   * Get active challenges
   */
  async challenges(): Promise<unknown> {
    return this.client.get('/api/challenges');
  }

  /**
   * Get quests leaderboard
   */
  async questsLeaderboard(): Promise<unknown> {
    return this.client.get('/api/quests/leaderboard');
  }

  /**
   * Get tips leaderboard
   */
  async tipsLeaderboard(): Promise<unknown> {
    return this.client.get('/api/tips/leaderboard');
  }

  /**
   * Get top tippers
   */
  async topTippers(): Promise<unknown> {
    return this.client.get('/api/tips/tippers');
  }

  /**
   * Get recent comments across all videos
   */
  async recentComments(limit = 20): Promise<unknown> {
    return this.client.get('/api/comments/recent', { limit });
  }
}
