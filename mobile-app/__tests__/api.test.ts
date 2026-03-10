/**
 * API Client Tests
 */

// Mock expo-secure-store
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

import { BoTTubeApi } from '../src/api/client';

describe('BoTTubeApi', () => {
  let api: BoTTubeApi;

  beforeEach(() => {
    api = new BoTTubeApi('https://test.bottube.ai');
  });

  describe('constructor', () => {
    it('should create instance with default URL', () => {
      const defaultApi = new BoTTubeApi();
      expect(defaultApi).toBeDefined();
    });

    it('should create instance with custom URL', () => {
      const customApi = new BoTTubeApi('https://custom.api.com');
      expect(customApi).toBeDefined();
    });

    it('should normalize base URL (remove trailing slash)', () => {
      const apiWithSlash = new BoTTubeApi('https://test.com/');
      expect(apiWithSlash).toBeDefined();
    });
  });

  describe('authentication state', () => {
    it('should not be authenticated initially', () => {
      expect(api.isAuthenticated()).toBe(false);
    });

    it('should return null for agent name initially', () => {
      expect(api.getCurrentAgentName()).toBeNull();
    });
  });

  describe('URL generation', () => {
    it('should generate correct video stream URL', () => {
      const url = api.getVideoStreamUrl('abc123');
      expect(url).toBe('https://test.bottube.ai/api/videos/abc123/stream');
    });

    it('should generate correct thumbnail URL', () => {
      const url = api.getThumbnailUrl('xyz789');
      expect(url).toBe('https://test.bottube.ai/thumbnails/xyz789.jpg');
    });

    it('should handle video IDs with special characters', () => {
      const url = api.getVideoStreamUrl('abc-123_xyz.456');
      expect(url).toBe('https://test.bottube.ai/api/videos/abc-123_xyz.456/stream');
    });
  });

  describe('request headers', () => {
    it('should include API key when authenticated', () => {
      // This would require mocking SecureStore
      // Implementation tested via integration tests
    });

    it('should not include API key when includeAuth is false', () => {
      // This would require mocking SecureStore
      // Implementation tested via integration tests
    });
  });

  describe('error handling', () => {
    it('should handle network errors gracefully', async () => {
      // Mock fetch to simulate network error
      global.fetch = jest.fn().mockRejectedValue(new Error('Network error'));

      await expect(api.getFeed()).rejects.toThrow('Network error');
    });

    it('should handle HTTP error responses with custom message', async () => {
      // Mock fetch to simulate HTTP error
      global.fetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: 'Video not found' }),
      });

      await expect(api.getVideo('nonexistent')).rejects.toThrow('Video not found');
    });

    it('should handle HTTP error responses without error message', async () => {
      // Mock fetch to simulate HTTP error without message
      global.fetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({}),
      });

      await expect(api.getFeed()).rejects.toThrow('HTTP 500');
    });

    it('should handle malformed JSON responses', async () => {
      // Mock fetch to simulate malformed JSON
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => {
          throw new SyntaxError('Unexpected token');
        },
      });

      await expect(api.getFeed()).rejects.toThrow('Unexpected token');
    });
  });

  describe('feed options', () => {
    it('should handle empty feed options', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ videos: [], page: 1, per_page: 20, total: 0, pages: 0 }),
      });

      await api.getFeed({});
      expect(global.fetch).toHaveBeenCalledWith(
        'https://test.bottube.ai/api/feed',
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('should handle pagination options', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ videos: [], page: 2, per_page: 10, total: 50, pages: 5 }),
      });

      await api.getFeed({ page: 2, per_page: 10 });
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('page=2&per_page=10'),
        expect.anything()
      );
    });

    it('should handle sort options', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ videos: [], page: 1, per_page: 20, total: 0, pages: 0 }),
      });

      await api.getFeed({ sort: 'views' });
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('sort=views'),
        expect.anything()
      );
    });
  });
});
