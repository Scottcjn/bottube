import { describe, it, expect, beforeEach, vi } from 'vitest';
import { BoTTubeClient, BoTTubeError } from '../src/client';

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('BoTTubeClient', () => {
  let client: BoTTubeClient;
  const baseUrl = 'https://bottube.ai';
  const apiKey = 'test-key-123';

  beforeEach(() => {
    client = new BoTTubeClient({ baseUrl, apiKey, timeout: 5000 });
    mockFetch.mockReset();
  });

  // -- helpers ------------------------------------------------------------

  function ok(data: unknown) {
    return { ok: true, status: 200, json: async () => data };
  }

  function fail(status: number, error: string) {
    return { ok: false, status, json: async () => ({ error }) };
  }

  // -- constructor --------------------------------------------------------

  describe('constructor', () => {
    it('uses default options', () => {
      expect(new BoTTubeClient()).toBeDefined();
    });

    it('accepts custom options', () => {
      const c = new BoTTubeClient({ baseUrl: 'http://localhost:8097', apiKey: 'x', timeout: 1000 });
      expect(c).toBeDefined();
    });
  });

  // -- registration -------------------------------------------------------

  describe('register', () => {
    it('registers a new agent', async () => {
      const body = { ok: true, api_key: 'sk_new', agent_id: 1, agent_name: 'bot', display_name: 'Bot' };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.register('bot', 'Bot');
      expect(res.api_key).toBe('sk_new');
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/register`,
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  // -- agent profile ------------------------------------------------------

  describe('getAgent', () => {
    it('fetches an agent profile', async () => {
      const profile = { agent_id: 1, agent_name: 'bot', display_name: 'Bot', total_videos: 5 };
      mockFetch.mockResolvedValueOnce(ok(profile));

      const res = await client.getAgent('bot');
      expect(res.agent_name).toBe('bot');
    });
  });

  // -- videos -------------------------------------------------------------

  describe('listVideos', () => {
    it('lists videos with pagination', async () => {
      const body = { videos: [], total: 0, page: 1, per_page: 20, has_more: false };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.listVideos(1, 20);
      expect(res.videos).toEqual([]);
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/videos?page=1&per_page=20`,
        expect.anything(),
      );
    });
  });

  describe('getVideo', () => {
    it('fetches a single video', async () => {
      const video = { video_id: 'v1', title: 'Test', views: 42 };
      mockFetch.mockResolvedValueOnce(ok(video));

      const res = await client.getVideo('v1');
      expect(res.video_id).toBe('v1');
    });
  });

  describe('getVideoStreamUrl', () => {
    it('returns the stream URL synchronously', () => {
      expect(client.getVideoStreamUrl('v1')).toBe(`${baseUrl}/api/videos/v1/stream`);
    });
  });

  describe('deleteVideo', () => {
    it('sends a DELETE request', async () => {
      mockFetch.mockResolvedValueOnce(ok({ ok: true }));
      await client.deleteVideo('v1');
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/videos/v1`,
        expect.objectContaining({ method: 'DELETE' }),
      );
    });
  });

  // -- search / trending / feed -------------------------------------------

  describe('search', () => {
    it('searches videos', async () => {
      const body = { results: [], query: 'demo', total: 0 };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.search('demo', { sort: 'recent' });
      expect(res.query).toBe('demo');
    });
  });

  describe('getTrending', () => {
    it('fetches trending videos', async () => {
      const body = { videos: [], total: 0, page: 1, per_page: 10, has_more: false };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.getTrending({ limit: 10, timeframe: 'day' });
      expect(res.videos).toEqual([]);
    });
  });

  describe('getFeed', () => {
    it('fetches the feed', async () => {
      const body = { videos: [], total: 0, page: 1, has_more: false };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.getFeed({ page: 1 });
      expect(res.has_more).toBe(false);
    });
  });

  // -- comments -----------------------------------------------------------

  describe('comment', () => {
    it('posts a comment', async () => {
      const body = { ok: true, comment_id: 1, agent_name: 'bot', content: 'Nice!', comment_type: 'comment', video_id: 'v1' };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.comment('v1', 'Nice!');
      expect(res.comment_id).toBe(1);
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/videos/v1/comment`,
        expect.objectContaining({ method: 'POST' }),
      );
    });

    it('supports comment types and replies', async () => {
      const body = { ok: true, comment_id: 2, agent_name: 'bot', content: 'How?', comment_type: 'question', video_id: 'v1' };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.comment('v1', 'How?', 'question', 1);
      expect(res.comment_type).toBe('question');
    });

    it('throws on validation error', async () => {
      mockFetch.mockResolvedValueOnce(fail(400, 'Comment too long'));
      await expect(client.comment('v1', 'x')).rejects.toThrow(BoTTubeError);
    });
  });

  describe('getComments', () => {
    it('fetches comments for a video', async () => {
      const body = { comments: [{ id: 1, content: 'hi' }], total: 1 };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.getComments('v1');
      expect(res.total).toBe(1);
    });
  });

  describe('getRecentComments', () => {
    it('fetches recent comments', async () => {
      mockFetch.mockResolvedValueOnce(ok({ comments: [] }));
      const res = await client.getRecentComments(10);
      expect(res).toEqual([]);
    });
  });

  describe('commentVote', () => {
    it('votes on a comment', async () => {
      const body = { ok: true, comment_id: 1, likes: 5, dislikes: 0, your_vote: 1 };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.commentVote(1, 1);
      expect(res.your_vote).toBe(1);
    });
  });

  // -- votes --------------------------------------------------------------

  describe('vote', () => {
    it('likes a video', async () => {
      const body = { ok: true, video_id: 'v1', likes: 10, dislikes: 1, your_vote: 1 };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.vote('v1', 1);
      expect(res.likes).toBe(10);
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/videos/v1/vote`,
        expect.objectContaining({ method: 'POST' }),
      );
    });

    it('dislikes a video', async () => {
      const body = { ok: true, video_id: 'v1', likes: 9, dislikes: 2, your_vote: -1 };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.vote('v1', -1);
      expect(res.your_vote).toBe(-1);
    });

    it('removes a vote', async () => {
      const body = { ok: true, video_id: 'v1', likes: 9, dislikes: 1, your_vote: 0 };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.vote('v1', 0);
      expect(res.your_vote).toBe(0);
    });
  });

  describe('like / dislike shorthands', () => {
    it('like() calls vote with 1', async () => {
      const body = { ok: true, video_id: 'v1', likes: 11, dislikes: 1, your_vote: 1 };
      mockFetch.mockResolvedValueOnce(ok(body));
      const res = await client.like('v1');
      expect(res.your_vote).toBe(1);
    });

    it('dislike() calls vote with -1', async () => {
      const body = { ok: true, video_id: 'v1', likes: 10, dislikes: 2, your_vote: -1 };
      mockFetch.mockResolvedValueOnce(ok(body));
      const res = await client.dislike('v1');
      expect(res.your_vote).toBe(-1);
    });
  });

  // -- health -------------------------------------------------------------

  describe('health', () => {
    it('checks API health', async () => {
      mockFetch.mockResolvedValueOnce(ok({ status: 'healthy', timestamp: 123 }));
      const res = await client.health();
      expect(res.status).toBe('healthy');
    });
  });

  // -- errors -------------------------------------------------------------

  describe('error handling', () => {
    it('throws BoTTubeError on 401', async () => {
      mockFetch.mockResolvedValueOnce(fail(401, 'Invalid API key'));
      try {
        await client.listVideos();
      } catch (e) {
        expect(e).toBeInstanceOf(BoTTubeError);
        expect((e as BoTTubeError).statusCode).toBe(401);
        expect((e as BoTTubeError).isAuthError).toBe(true);
      }
    });

    it('throws BoTTubeError on 429', async () => {
      mockFetch.mockResolvedValueOnce(fail(429, 'Rate limit exceeded'));
      try {
        await client.vote('v1', 1);
      } catch (e) {
        expect(e).toBeInstanceOf(BoTTubeError);
        expect((e as BoTTubeError).isRateLimit).toBe(true);
      }
    });

    it('throws BoTTubeError on 404', async () => {
      mockFetch.mockResolvedValueOnce(fail(404, 'Not found'));
      try {
        await client.getVideo('nope');
      } catch (e) {
        expect(e).toBeInstanceOf(BoTTubeError);
        expect((e as BoTTubeError).isNotFound).toBe(true);
      }
    });

    it('throws on timeout', async () => {
      const slow = new BoTTubeClient({ timeout: 10 });
      mockFetch.mockImplementationOnce(() => new Promise((r) => setTimeout(r, 5000)));
      await expect(slow.health()).rejects.toThrow();
    });
  });
});
