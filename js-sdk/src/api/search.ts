import type { HttpClient } from '../client';
import type { Video, PaginatedResponse, SearchOptions } from '../types';

/**
 * Search API client
 * Handles video search operations
 */
export class SearchApi {
  private client: HttpClient;

  constructor(client: HttpClient) {
    this.client = client;
  }

  /**
   * Search videos
   */
  async search(options: SearchOptions): Promise<PaginatedResponse<Video>> {
    const { q, page = 1, per_page = 20, category, sort = 'relevance' } = options;
    return this.client.get('/api/search', { q, page, per_page, category, sort });
  }
}
