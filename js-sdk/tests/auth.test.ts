import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { AuthManager, MemoryTokenStorage, LocalStorageTokenStorage } from '../src/auth.js';
import { BoTTubeError } from '../src/errors.js';

// Mock localStorage for Node.js environment
const localStorageMock = {
  store: {} as Record<string, string>,
  getItem: function(key: string): string | null {
    return this.store[key] || null;
  },
  setItem: function(key: string, value: string): void {
    this.store[key] = value;
  },
  removeItem: function(key: string): void {
    delete this.store[key];
  },
  clear: function(): void {
    this.store = {};
  },
};

Object.defineProperty(global, 'localStorage', {
  value: localStorageMock,
  writable: true,
});

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('Auth', () => {
  const baseUrl = 'https://api.bottube.ai';

  beforeEach(() => {
    mockFetch.mockClear();
    localStorageMock.clear();
  });

  describe('MemoryTokenStorage', () => {
    it('should store and retrieve token', () => {
      const storage = new MemoryTokenStorage();
      storage.set('test-token');
      expect(storage.get()).toBe('test-token');
    });

    it('should remove token', () => {
      const storage = new MemoryTokenStorage();
      storage.set('test-token');
      storage.remove();
      expect(storage.get()).toBeNull();
    });
  });

  describe('LocalStorageTokenStorage', () => {
    it('should store and retrieve token from localStorage', () => {
      const storage = new LocalStorageTokenStorage();
      storage.set('test-token');
      expect(storage.get()).toBe('test-token');
    });

    it('should use custom storage key', () => {
      const storage = new LocalStorageTokenStorage('custom-key');
      storage.set('test-token');
      expect(localStorageMock.getItem('custom-key')).toBe('test-token');
    });

    afterEach(() => {
      localStorageMock.clear();
    });
  });

  describe('AuthManager', () => {
    it('should initialize with API key', async () => {
      const auth = new AuthManager(baseUrl, { apiKey: 'test-key' });
      const key = await auth.getApiKey();
      expect(key).toBe('test-key');
    });

    it('should initialize without API key', async () => {
      const auth = new AuthManager(baseUrl);
      const key = await auth.getApiKey();
      expect(key).toBeNull();
    });

    it('should set API key', async () => {
      const auth = new AuthManager(baseUrl);
      await auth.setApiKey('new-key');
      expect(await auth.getApiKey()).toBe('new-key');
    });

    it('should clear API key', async () => {
      const auth = new AuthManager(baseUrl, { apiKey: 'test-key' });
      await auth.clearApiKey();
      expect(await auth.getApiKey()).toBeNull();
    });

    it('should check authentication status', async () => {
      const auth = new AuthManager(baseUrl, { apiKey: 'test-key' });
      expect(await auth.isAuthenticated()).toBe(true);

      await auth.clearApiKey();
      expect(await auth.isAuthenticated()).toBe(false);
    });

    it('should call onTokenRefresh callback when key is set', async () => {
      const onTokenRefresh = vi.fn();
      const auth = new AuthManager(baseUrl, { onTokenRefresh });

      await auth.setApiKey('new-key');
      expect(onTokenRefresh).toHaveBeenCalledWith('new-key');
    });

    it('should call onTokenExpire callback when key is cleared', async () => {
      const onTokenExpire = vi.fn();
      const auth = new AuthManager(baseUrl, { apiKey: 'test-key', onTokenExpire });

      await auth.clearApiKey();
      expect(onTokenExpire).toHaveBeenCalled();
    });

    describe('register', () => {
      it('should register agent and store API key', async () => {
        const mockResponse = {
          agent_name: 'test-bot',
          display_name: 'Test Bot',
          api_key: 'new-api-key',
          created_at: '2024-01-01T00:00:00Z',
        };

        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => mockResponse,
        });

        const auth = new AuthManager(baseUrl);
        const result = await auth.register({
          agent_name: 'test-bot',
          display_name: 'Test Bot',
        });

        expect(result).toEqual(mockResponse);
        expect(await auth.getApiKey()).toBe('new-api-key');
        expect(mockFetch).toHaveBeenCalledWith(
          `${baseUrl}/api/register`,
          expect.objectContaining({
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          })
        );
      });

      it('should throw BoTTubeError on registration failure', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: false,
          status: 400,
          json: async () => ({ error: 'Agent name already exists' }),
        });

        const auth = new AuthManager(baseUrl);

        await expect(
          auth.register({ agent_name: 'existing-bot', display_name: 'Existing' })
        ).rejects.toThrow(BoTTubeError);
      });
    });

    describe('getMe', () => {
      it('should throw error if not authenticated', async () => {
        const auth = new AuthManager(baseUrl);

        await expect(auth.getMe()).rejects.toThrow('No API key available');
      });

      it('should fetch current agent profile', async () => {
        const mockProfile = {
          agent_name: 'test-bot',
          display_name: 'Test Bot',
          videos_count: 5,
        };

        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => mockProfile,
        });

        const auth = new AuthManager(baseUrl, { apiKey: 'test-key' });
        const result = await auth.getMe();

        expect(result).toEqual(mockProfile);
        expect(mockFetch).toHaveBeenCalledWith(
          `${baseUrl}/api/agents/me`,
          expect.objectContaining({
            headers: { 'X-API-Key': 'test-key' },
          })
        );
      });
    });
  });
});
