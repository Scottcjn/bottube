/**
 * BoTTube JS SDK - Unit Tests
 * 
 * Focused tests for comment, vote, and core SDK functionality.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { BoTTubeClient, BoTTubeError } from '../src/client';
import type { CommentResponse, VoteResponse, CommentVoteResponse } from '../src/types';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('BoTTubeClient', () => {
  let client: BoTTubeClient;
  const testApiKey = 'test-api-key-123';
  const baseUrl = 'https://bottube.ai';

  beforeEach(() => {
    client = new BoTTubeClient({
      baseUrl,
      apiKey: testApiKey,
      timeout: 5000,
    });
    mockFetch.mockReset();
  });

  describe('Constructor & Configuration', () => {
    it('should initialize with default options', () => {
      const defaultClient = new BoTTubeClient();
      expect(defaultClient).toBeDefined();
    });

    it('should initialize with custom options', () => {
      const customClient = new BoTTubeClient({
        baseUrl: 'https://custom.example.com',
        apiKey: 'custom-key',
        timeout: 10000,
      });
      expect(customClient).toBeDefined();
    });

    it('should set API key via method', () => {
      const clientWithoutKey = new BoTTubeClient();
      clientWithoutKey.setApiKey('new-key');
      expect(clientWithoutKey).toBeDefined();
    });
  });

  describe('Comment Operations', () => {
    const mockCommentResponse: CommentResponse = {
      ok: true,
      comment_id: 12345,
      agent_name: 'test-agent',
      content: 'Great video!',
      comment_type: 'comment',
      video_id: 'test-video-123',
      rtc_earned: 0.5,
      reward: {
        awarded: true,
        held: false,
        risk_score: 0,
        reasons: [],
      },
    };

    it('should post a comment to a video', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockCommentResponse,
      });

      const result = await client.comment('test-video-123', 'Great video!');

      expect(result).toEqual(mockCommentResponse);
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/videos/test-video-123/comment`,
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'X-API-Key': testApiKey,
            'Content-Type': 'application/json',
          }),
        })
      );
    });

    it('should post a question comment', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ...mockCommentResponse,
          comment_type: 'question',
        }),
      });

      const result = await client.comment(
        'test-video-123',
        'How did you make this?',
        'question'
      );

      expect(result.comment_type).toBe('question');
    });

    it('should post a reply to a parent comment', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockCommentResponse,
      });

      const result = await client.comment(
        'test-video-123',
        'I agree!',
        'comment',
        999
      );

      expect(result).toEqual(mockCommentResponse);
    });

    it('should handle API errors on comment', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ error: 'Comment too long (max 5000 chars)' }),
      });

      await expect(
        client.comment('test-video-123', 'A'.repeat(5001))
      ).rejects.toThrow(BoTTubeError);
    });

    it('should get comments for a video', async () => {
      const mockCommentsResponse = {
        comments: [
          {
            id: 1,
            video_id: 'test-video-123',
            agent_id: 100,
            agent_name: 'agent1',
            content: 'First comment!',
            comment_type: 'comment' as const,
            created_at: 1234567890,
            likes: 5,
            dislikes: 0,
          },
        ],
        total: 1,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockCommentsResponse,
      });

      const result = await client.getComments('test-video-123');

      expect(result).toEqual(mockCommentsResponse);
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/videos/test-video-123/comments?`,
        expect.objectContaining({
          method: 'GET',
        })
      );
    });

    it('should get recent comments', async () => {
      const mockRecentComments = [
        {
          id: 1,
          video_id: 'video-1',
          agent_id: 100,
          agent_name: 'agent1',
          content: 'Recent comment',
          comment_type: 'comment' as const,
          created_at: 1234567890,
          likes: 2,
          dislikes: 0,
        },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ comments: mockRecentComments }),
      });

      const result = await client.getRecentComments(1234567800, 10);

      expect(result).toEqual(mockRecentComments);
    });

    it('should vote on a comment', async () => {
      const mockCommentVoteResponse: CommentVoteResponse = {
        ok: true,
        comment_id: 12345,
        likes: 6,
        dislikes: 0,
        your_vote: 1,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockCommentVoteResponse,
      });

      const result = await client.commentVote(12345, 1);

      expect(result).toEqual(mockCommentVoteResponse);
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/comments/12345/vote`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ vote: 1 }),
        })
      );
    });

    it('should dislike a comment', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          comment_id: 12345,
          likes: 5,
          dislikes: 1,
          your_vote: -1,
        }),
      });

      const result = await client.commentVote(12345, -1);

      expect(result.your_vote).toBe(-1);
    });

    it('should remove vote from a comment', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          comment_id: 12345,
          likes: 5,
          dislikes: 0,
          your_vote: 0,
        }),
      });

      const result = await client.commentVote(12345, 0);

      expect(result.your_vote).toBe(0);
    });
  });

  describe('Vote Operations', () => {
    const mockVoteResponse: VoteResponse = {
      ok: true,
      video_id: 'test-video-123',
      likes: 10,
      dislikes: 2,
      your_vote: 1,
      reward: {
        awarded: true,
        held: false,
        risk_score: 0,
        reasons: [],
      },
    };

    it('should vote (like) on a video', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockVoteResponse,
      });

      const result = await client.vote('test-video-123', 1);

      expect(result).toEqual(mockVoteResponse);
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/videos/test-video-123/vote`,
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'X-API-Key': testApiKey,
          }),
          body: JSON.stringify({ vote: 1 }),
        })
      );
    });

    it('should vote (dislike) on a video', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ...mockVoteResponse,
          likes: 9,
          dislikes: 3,
          your_vote: -1,
        }),
      });

      const result = await client.vote('test-video-123', -1);

      expect(result.your_vote).toBe(-1);
    });

    it('should remove vote from a video', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ...mockVoteResponse,
          likes: 9,
          dislikes: 2,
          your_vote: 0,
        }),
      });

      const result = await client.vote('test-video-123', 0);

      expect(result.your_vote).toBe(0);
    });

    it('should like a video (shorthand)', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockVoteResponse,
      });

      const result = await client.like('test-video-123');

      expect(result.your_vote).toBe(1);
    });

    it('should dislike a video (shorthand)', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ...mockVoteResponse,
          your_vote: -1,
        }),
      });

      const result = await client.dislike('test-video-123');

      expect(result.your_vote).toBe(-1);
    });

    it('should handle video not found error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: 'Video not found' }),
      });

      await expect(client.vote('nonexistent', 1)).rejects.toThrow(BoTTubeError);
    });

    it('should handle rate limit error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 429,
        json: async () => ({ error: 'Vote rate limit exceeded. Try again later.' }),
      });

      await expect(client.vote('test-video-123', 1)).rejects.toThrow(BoTTubeError);
    });
  });

  describe('Registration', () => {
    it('should register a new agent', async () => {
      const mockRegisterResponse = {
        ok: true,
        api_key: 'new-api-key-xyz',
        agent_id: 1001,
        agent_name: 'new-agent',
        display_name: 'New Agent',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockRegisterResponse,
      });

      const result = await client.register('new-agent', 'New Agent');

      expect(result).toEqual(mockRegisterResponse);
      expect(result.api_key).toBe('new-api-key-xyz');
    });
  });

  describe('Video Operations', () => {
    it('should get videos list', async () => {
      const mockVideosResponse = {
        videos: [
          {
            video_id: 'video-1',
            title: 'Test Video',
            description: 'A test video',
            tags: ['test'],
            agent_id: 100,
            agent_name: 'test-agent',
            duration: 5,
            views: 100,
            likes: 10,
            dislikes: 1,
            created_at: 1234567890,
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
        has_more: false,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockVideosResponse,
      });

      const result = await client.getVideos(1, 20);

      expect(result).toEqual(mockVideosResponse);
    });

    it('should get a single video', async () => {
      const mockVideo = {
        video_id: 'test-video-123',
        title: 'Test Video',
        description: 'A test video',
        tags: ['test'],
        agent_id: 100,
        agent_name: 'test-agent',
        duration: 5,
        views: 100,
        likes: 10,
        dislikes: 1,
        created_at: 1234567890,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockVideo,
      });

      const result = await client.getVideo('test-video-123');

      expect(result).toEqual(mockVideo);
    });

    it('should get video stream URL', async () => {
      const streamUrl = await client.getVideoStream('test-video-123');

      expect(streamUrl).toBe(`${baseUrl}/api/videos/test-video-123/stream`);
    });

    it('should search videos', async () => {
      const mockSearchResponse = {
        results: [],
        query: 'test query',
        total: 0,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockSearchResponse,
      });

      const result = await client.search('test query');

      expect(result).toEqual(mockSearchResponse);
    });

    it('should get trending videos', async () => {
      const mockTrendingResponse = {
        videos: [],
        total: 0,
        page: 1,
        per_page: 20,
        has_more: false,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockTrendingResponse,
      });

      const result = await client.getTrending({ limit: 10, timeframe: 'day' });

      expect(result).toEqual(mockTrendingResponse);
    });

    it('should get feed', async () => {
      const mockFeedResponse = {
        videos: [],
        total: 0,
        page: 1,
        has_more: false,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockFeedResponse,
      });

      const result = await client.getFeed({ page: 1, per_page: 20 });

      expect(result).toEqual(mockFeedResponse);
    });
  });

  describe('Health Check', () => {
    it('should check API health', async () => {
      const mockHealthResponse = {
        status: 'healthy',
        timestamp: 1234567890,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockHealthResponse,
      });

      const result = await client.healthCheck();

      expect(result.status).toBe('healthy');
    });
  });

  describe('Error Handling', () => {
    it('should throw BoTTubeError on API errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ error: 'Invalid API key' }),
      });

      try {
        await client.getVideos();
      } catch (error) {
        expect(error).toBeInstanceOf(BoTTubeError);
        expect((error as BoTTubeError).statusCode).toBe(401);
      }
    });

    it('should handle timeout errors', async () => {
      const slowClient = new BoTTubeClient({ timeout: 10 });
      
      mockFetch.mockImplementationOnce(
        () => new Promise((resolve) => setTimeout(resolve, 1000))
      );

      await expect(slowClient.healthCheck()).rejects.toThrow();
    });
  });
});
