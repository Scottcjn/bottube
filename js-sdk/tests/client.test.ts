import { describe, it, expect, beforeEach, vi } from 'vitest';
import { HttpClient } from '../src/client.js';
import { BoTTubeError, TimeoutError, NetworkError } from '../src/errors.js';

// Mock fetch globally with proper Response-like objects
const mockFetch = vi.fn();
global.fetch = mockFetch as typeof fetch;

// Helper to create mock response
function createMockResponse(data: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => data,
    headers: {
      get: (name: string) => name === 'content-type' ? 'application/json' : null,
    },
  };
}

describe('HttpClient', () => {
  const baseUrl = 'https://api.bottube.ai';

  beforeEach(() => {
    mockFetch.mockClear();
  });

  describe('constructor', () => {
    it('should initialize with default config', () => {
      const client = new HttpClient();
      expect(client.getBaseUrl()).toBe('https://bottube.ai');
    });

    it('should initialize with custom baseUrl', () => {
      const client = new HttpClient({ baseUrl: 'https://custom.api.com' });
      expect(client.getBaseUrl()).toBe('https://custom.api.com');
    });

    it('should initialize with API key', () => {
      const client = new HttpClient({ apiKey: 'test-key' });
      expect(client.getApiKey()).toBe('test-key');
    });

    it('should initialize with custom timeout', () => {
      const client = new HttpClient({ timeout: 60000 });
      // Timeout is used internally, just verify it doesn't throw
      expect(client).toBeDefined();
    });

    it('should remove trailing slash from baseUrl', () => {
      const client = new HttpClient({ baseUrl: 'https://api.example.com/' });
      expect(client.getBaseUrl()).toBe('https://api.example.com');
    });
  });

  describe('API key management', () => {
    it('should set API key', () => {
      const client = new HttpClient();
      client.setApiKey('new-key');
      expect(client.getApiKey()).toBe('new-key');
    });

    it('should clear API key', () => {
      const client = new HttpClient({ apiKey: 'test-key' });
      client.clearApiKey();
      expect(client.getApiKey()).toBeUndefined();
    });
  });

  describe('GET request', () => {
    it('should make GET request', async () => {
      const mockData = { items: [1, 2, 3] };
      mockFetch.mockResolvedValueOnce(createMockResponse(mockData));

      const client = new HttpClient({ baseUrl });
      const result = await client.get('/api/videos');

      expect(result).toEqual(mockData);
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/videos`,
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('should include query params', async () => {
      mockFetch.mockResolvedValueOnce(createMockResponse({ data: [] }));

      const client = new HttpClient({ baseUrl });
      await client.get('/api/videos', { page: 2, per_page: 10 });

      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/videos?page=2&per_page=10`,
        expect.anything()
      );
    });

    it('should include API key header', async () => {
      mockFetch.mockResolvedValueOnce(createMockResponse({ data: [] }));

      const client = new HttpClient({ baseUrl, apiKey: 'test-key' });
      await client.get('/api/agents/me');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-API-Key': 'test-key',
          }),
        })
      );
    });
  });

  describe('POST request', () => {
    it('should make POST request with body', async () => {
      const mockResult = { id: 1, title: 'New Video' };
      mockFetch.mockResolvedValueOnce(createMockResponse(mockResult));

      const client = new HttpClient({ baseUrl });
      const result = await client.post('/api/upload', { title: 'Test' });

      expect(result).toEqual(mockResult);
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/upload`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ title: 'Test' }),
        })
      );
    });
  });

  describe('PATCH request', () => {
    it('should make PATCH request with body', async () => {
      mockFetch.mockResolvedValueOnce(createMockResponse({ updated: true }));

      const client = new HttpClient({ baseUrl });
      await client.patch('/api/agents/me/profile', { bio: 'New bio' });

      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/agents/me/profile`,
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ bio: 'New bio' }),
        })
      );
    });
  });

  describe('DELETE request', () => {
    it('should make DELETE request', async () => {
      mockFetch.mockResolvedValueOnce(createMockResponse({ deleted: true }));

      const client = new HttpClient({ baseUrl });
      await client.delete('/api/videos/123');

      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/videos/123`,
        expect.objectContaining({ method: 'DELETE' })
      );
    });
  });

  describe('error handling', () => {
    it('should throw BoTTubeError on API error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: 'Video not found' }),
        headers: {
          get: () => null,
        },
      });

      const client = new HttpClient({ baseUrl });

      await expect(client.get('/api/videos/nonexistent')).rejects.toThrow(BoTTubeError);
    });

    it('should throw TimeoutError on timeout', async () => {
      const abortError = new Error('The operation was aborted.');
      abortError.name = 'AbortError';
      
      mockFetch.mockImplementationOnce(() => {
        return Promise.reject(abortError);
      });

      const client = new HttpClient({ baseUrl, timeout: 50 });

      await expect(client.get('/api/videos')).rejects.toThrow(TimeoutError);
    });

    it('should throw NetworkError on network failure', async () => {
      mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));

      const client = new HttpClient({ baseUrl });

      await expect(client.get('/api/videos')).rejects.toThrow(NetworkError);
    });
  });

  describe('headers', () => {
    it('should include Content-Type header', async () => {
      mockFetch.mockResolvedValueOnce(createMockResponse({ data: [] }));

      const client = new HttpClient({ baseUrl });
      await client.get('/api/videos');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );
    });

    it('should include custom User-Agent', async () => {
      mockFetch.mockResolvedValueOnce(createMockResponse({ data: [] }));

      const client = new HttpClient({ baseUrl, userAgent: 'CustomAgent/1.0' });
      await client.get('/api/videos');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'User-Agent': 'CustomAgent/1.0',
          }),
        })
      );
    });
  });
});
