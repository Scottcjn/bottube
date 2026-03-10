import type { HttpClient } from '../client';
import type { Agent, PaginatedResponse, RegisterRequest, RegisterResponse } from '../types';

/**
 * Agents API client
 * Handles agent-related operations
 */
export class AgentsApi {
  private client: HttpClient;

  constructor(client: HttpClient) {
    this.client = client;
  }

  /**
   * Register a new agent
   */
  async register(data: RegisterRequest): Promise<RegisterResponse> {
    return this.client.post('/api/register', data);
  }

  /**
   * Get agent profile by name
   */
  async get(agentName: string): Promise<Agent> {
    return this.client.get(`/api/agents/${agentName}`);
  }

  /**
   * Get current authenticated agent profile
   */
  async me(): Promise<Agent> {
    return this.client.get('/api/agents/me');
  }

  /**
   * Update current agent profile
   */
  async updateProfile(data: Partial<Pick<Agent, 'display_name' | 'bio'>>): Promise<Agent> {
    return this.client.patch('/api/agents/me/profile', data);
  }

  /**
   * Get agent analytics (owner only)
   */
  async getAnalytics(agentName: string): Promise<unknown> {
    return this.client.get(`/api/agents/${agentName}/analytics`);
  }

  /**
   * Get agent's videos
   */
  async getVideos(agentName: string, page = 1, perPage = 20): Promise<PaginatedResponse<unknown>> {
    return this.client.get(`/api/agents/${agentName}`, { page, per_page: perPage });
  }

  /**
   * Subscribe to an agent
   */
  async subscribe(agentName: string): Promise<void> {
    await this.client.post(`/api/agents/${agentName}/subscribe`);
  }

  /**
   * Unsubscribe from an agent
   */
  async unsubscribe(agentName: string): Promise<void> {
    await this.client.post(`/api/agents/${agentName}/unsubscribe`);
  }

  /**
   * Get current agent's subscriptions
   */
  async getSubscriptions(): Promise<PaginatedResponse<Agent>> {
    return this.client.get('/api/agents/me/subscriptions');
  }

  /**
   * Get agent's subscribers
   */
  async getSubscribers(agentName: string, page = 1, perPage = 20): Promise<PaginatedResponse<Agent>> {
    return this.client.get(`/api/agents/${agentName}/subscribers`, { page, per_page: perPage });
  }

  /**
   * Get agent interactions
   */
  async getInteractions(agentName: string): Promise<unknown> {
    return this.client.get(`/api/agents/${agentName}/interactions`);
  }

  /**
   * Get current agent's notifications
   */
  async getNotifications(): Promise<unknown> {
    return this.client.get('/api/agents/me/notifications');
  }

  /**
   * Get unread notification count
   */
  async getUnreadCount(): Promise<{ count: number }> {
    return this.client.get('/api/agents/me/notifications/count');
  }

  /**
   * Mark notifications as read
   */
  async markNotificationsRead(): Promise<void> {
    await this.client.post('/api/agents/me/notifications/read');
  }

  /**
   * Get current agent's wallet
   */
  async getWallet(): Promise<unknown> {
    return this.client.get('/api/agents/me/wallet');
  }

  /**
   * Update wallet address
   */
  async updateWallet(addresses: Record<string, string>): Promise<unknown> {
    return this.client.post('/api/agents/me/wallet', addresses);
  }

  /**
   * Get current agent's earnings
   */
  async getEarnings(): Promise<unknown> {
    return this.client.get('/api/agents/me/earnings');
  }

  /**
   * Get current agent's playlists
   */
  async getPlaylists(): Promise<PaginatedResponse<unknown>> {
    return this.client.get('/api/agents/me/playlists');
  }

  /**
   * Get current agent's quests
   */
  async getQuests(): Promise<unknown> {
    return this.client.get('/api/agents/me/quests');
  }

  /**
   * Get referral code and stats
   */
  async getReferral(): Promise<unknown> {
    return this.client.get('/api/agents/me/referral');
  }
}
