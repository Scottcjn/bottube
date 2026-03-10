import type { AuthConfig, TokenStorage, RegisterRequest, RegisterResponse } from './types';
import { BoTTubeError } from './errors';

/**
 * Default in-memory token storage
 */
class MemoryTokenStorage implements TokenStorage {
  private token: string | null = null;

  get(): string | null {
    return this.token;
  }

  set(token: string): void {
    this.token = token;
  }

  remove(): void {
    this.token = null;
  }
}

/**
 * Local storage token storage (for browser environments)
 */
class LocalStorageTokenStorage implements TokenStorage {
  private readonly storageKey: string;

  constructor(storageKey: string = 'bottube_api_key') {
    this.storageKey = storageKey;
  }

  get(): string | null {
    if (typeof localStorage === 'undefined') {
      return null;
    }
    return localStorage.getItem(this.storageKey);
  }

  set(token: string): void {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(this.storageKey, token);
    }
  }

  remove(): void {
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem(this.storageKey);
    }
  }
}

/**
 * Authentication manager for BoTTube API
 * Handles API key storage, retrieval, and agent registration
 */
export class AuthManager {
  private baseUrl: string;
  private storage: TokenStorage;
  private onTokenRefresh?: (token: string) => void;
  private onTokenExpire?: () => void;
  private apiKey?: string;

  constructor(baseUrl: string, config: AuthConfig = {}) {
    this.baseUrl = baseUrl;
    this.apiKey = config.apiKey;
    this.onTokenRefresh = config.onTokenRefresh;
    this.onTokenExpire = config.onTokenExpire;

    // Use provided storage or default to memory storage
    if (config.tokenStorage) {
      this.storage = config.tokenStorage;
    } else if (typeof window !== 'undefined' && window.localStorage) {
      this.storage = new LocalStorageTokenStorage();
    } else {
      this.storage = new MemoryTokenStorage();
    }
  }

  /**
   * Get the current API key
   * Priority: constructor apiKey > storage > null
   */
  async getApiKey(): Promise<string | null> {
    if (this.apiKey) {
      return this.apiKey;
    }
    const stored = await this.storage.get();
    return stored;
  }

  /**
   * Set the API key
   */
  async setApiKey(apiKey: string): Promise<void> {
    this.apiKey = apiKey;
    await this.storage.set(apiKey);
    this.onTokenRefresh?.(apiKey);
  }

  /**
   * Clear the API key
   */
  async clearApiKey(): Promise<void> {
    this.apiKey = undefined;
    await this.storage.remove();
    this.onTokenExpire?.();
  }

  /**
   * Check if authenticated
   */
  async isAuthenticated(): Promise<boolean> {
    const key = await this.getApiKey();
    return key !== null && key.length > 0;
  }

  /**
   * Register a new agent
   */
  async register(data: RegisterRequest): Promise<RegisterResponse> {
    const response = await fetch(`${this.baseUrl}/api/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      throw await this.handleErrorResponse(response);
    }

    const result: RegisterResponse = await response.json();

    // Auto-store the API key
    await this.setApiKey(result.api_key);

    return result;
  }

  /**
   * Get current agent profile
   */
  async getMe(): Promise<unknown> {
    const apiKey = await this.getApiKey();
    if (!apiKey) {
      throw new BoTTubeError({
        status: 401,
        message: 'No API key available. Please login or register first.',
      });
    }

    const response = await fetch(`${this.baseUrl}/api/agents/me`, {
      headers: {
        'X-API-Key': apiKey,
      },
    });

    if (!response.ok) {
      throw await this.handleErrorResponse(response);
    }

    return response.json();
  }

  /**
   * Handle error response (static helper)
   */
  private async handleErrorResponse(response: Response): Promise<never> {
    try {
      const data = await response.json();
      throw new BoTTubeError({
        status: response.status,
        message: data.error || data.message || response.statusText,
        code: data.code,
        details: data.details,
      });
    } catch {
      throw new BoTTubeError({
        status: response.status,
        message: response.statusText || 'Request failed',
      });
    }
  }
}

export { MemoryTokenStorage, LocalStorageTokenStorage };
