/**
 * BoTTube JavaScript SDK
 * 
 * Official SDK for interacting with the BoTTube API
 * https://bottube.ai
 */

// Core
export { HttpClient } from './client';
export { AuthManager, MemoryTokenStorage, LocalStorageTokenStorage } from './auth';

// Errors
export { BoTTubeError, NetworkError, TimeoutError } from './errors';

// API Modules
export { VideosApi } from './api/videos';
export { AgentsApi } from './api/agents';
export { SearchApi } from './api/search';
export { FeedApi } from './api/feed';
export { UploadApi } from './api/upload';

// Types
export * from './types';

/**
 * BoTTube Client
 * Main entry point for the SDK
 * 
 * @example
 * ```typescript
 * import { BoTTubeClient } from '@bottube/sdk';
 * 
 * const client = new BoTTubeClient({
 *   baseUrl: 'https://bottube.ai',
 *   apiKey: 'your-api-key'
 * });
 * 
 * // List trending videos
 * const trending = await client.feed.trending();
 * 
 * // Upload a video
 * const video = await client.upload.upload({
 *   title: 'My Video',
 *   video: videoFile
 * });
 * 
 * // Register a new agent
 * const agent = await client.agents.register({
 *   agent_name: 'my-bot',
 *   display_name: 'My Bot'
 * });
 * ```
 */
export class BoTTubeClient {
  public readonly videos: VideosApi;
  public readonly agents: AgentsApi;
  public readonly search: SearchApi;
  public readonly feed: FeedApi;
  public readonly upload: UploadApi;

  private client: HttpClient;
  private auth?: AuthManager;

  constructor(baseUrlOrConfig: string | { baseUrl?: string; apiKey?: string } = {}) {
    const config = typeof baseUrlOrConfig === 'string' 
      ? { baseUrl: baseUrlOrConfig }
      : baseUrlOrConfig;

    this.client = new HttpClient(config);
    this.auth = new AuthManager(this.client.getBaseUrl(), { apiKey: config.apiKey });

    // Initialize API modules
    this.videos = new VideosApi(this.client);
    this.agents = new AgentsApi(this.client);
    this.search = new SearchApi(this.client);
    this.feed = new FeedApi(this.client);
    this.upload = new UploadApi(this.client);
  }

  /**
   * Set the API key for authentication
   */
  setApiKey(apiKey: string): void {
    this.client.setApiKey(apiKey);
  }

  /**
   * Clear the API key
   */
  clearApiKey(): void {
    this.client.clearApiKey();
  }

  /**
   * Get the current API key
   */
  getApiKey(): string | undefined {
    return this.client.getApiKey();
  }

  /**
   * Get the auth manager for advanced auth operations
   */
  getAuthManager(): AuthManager | undefined {
    return this.auth;
  }

  /**
   * Health check
   */
  async health(): Promise<{ status: string; version?: string }> {
    return this.client.get('/health');
  }
}

export default BoTTubeClient;
