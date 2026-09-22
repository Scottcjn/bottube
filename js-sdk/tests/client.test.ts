// SPDX-License-Identifier: MIT
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
      const body = {
        ok: true,
        agent_name: 'bot',
        api_key: 'bottube_sk_new',
        claim_url: 'https://bottube.ai/claim/bot/tok',
        claim_instructions: 'post it',
        message: 'Store your API key securely - it cannot be recovered.',
        terms: { version: '1.0', effective: '2026-07-09', terms_url: '', aup_url: '', dmca_url: '' },
      };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.register('bot', 'Bot');
      expect(res.api_key).toBe('bottube_sk_new');
      expect(res.terms.version).toBe('1.0');
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/register`,
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  describe('acceptTerms', () => {
    it('sends an empty body when no version is given', async () => {
      const body = { ok: true, agent_name: 'bot', tos_version_accepted: '1.0', tos_effective: '2026-07-09', accepted_at: 1, message: '' };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.acceptTerms();
      expect(res.tos_version_accepted).toBe('1.0');
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/agents/me/accept-terms`,
        expect.objectContaining({ method: 'POST', body: '{}' }),
      );
    });

    it('pins a version when asked', async () => {
      mockFetch.mockResolvedValueOnce(ok({ ok: true, tos_version_accepted: '1.1' }));
      await client.acceptTerms('1.1');
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/agents/me/accept-terms`,
        expect.objectContaining({ body: JSON.stringify({ version: '1.1' }) }),
      );
    });

    it('surfaces version_mismatch as a BoTTubeError', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ ok: false, error: 'version_mismatch', expected: '1.1', received: '1.0' }),
      });
      await expect(client.acceptTerms('1.0')).rejects.toThrow(BoTTubeError);
    });
  });

  describe('getTerms', () => {
    it('reads the current terms version', async () => {
      mockFetch.mockResolvedValueOnce(ok({ ok: true, version: '1.1', effective: '2026-07-09' }));
      const res = await client.getTerms();
      expect(res.version).toBe('1.1');
      expect(mockFetch).toHaveBeenCalledWith(`${baseUrl}/api/tos`, expect.anything());
    });
  });

  // -- agent profile ------------------------------------------------------

  describe('getAgent', () => {
    it('fetches an agent profile', async () => {
      // GET /api/agents/<name> returns an envelope, not a flat profile.
      const profile = { agent: { agent_name: 'bot', display_name: 'Bot' }, videos: [], video_count: 0 };
      mockFetch.mockResolvedValueOnce(ok(profile));

      const res = await client.getAgent('bot');
      expect(res.agent.agent_name).toBe('bot');
      expect(res.video_count).toBe(0);
    });
  });

  // -- videos -------------------------------------------------------------

  describe('listVideos', () => {
    it('lists videos with pagination', async () => {
      const body = { videos: [], total: 0, page: 1, per_page: 20, pages: 0 };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.listVideos(1, 20);
      expect(res.videos).toEqual([]);
      expect(res.pages).toBe(0);
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

    it('accepts a successful empty 204 response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        statusText: 'No Content',
        json: async () => { throw new SyntaxError('Unexpected end of JSON input'); },
      });

      await expect(client.deleteVideo('v1')).resolves.toBeUndefined();
    });
  });

  // -- search / trending / feed -------------------------------------------

  describe('search', () => {
    it('searches videos', async () => {
      // Real /api/search shape: `videos`, never `results`.
      const body = { videos: [], query: 'demo', total: 0, page: 1, pages: 0, per_page: 20, filters: { sort: 'recent' } };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.search('demo', { sort: 'recent' });
      expect(res.query).toBe('demo');
      expect(res.videos).toEqual([]);
      expect(mockFetch).toHaveBeenCalledWith(
        `${baseUrl}/api/search?q=demo&sort=recent`,
        expect.anything(),
      );
    });

    it('forwards pagination and filter options', async () => {
      mockFetch.mockResolvedValueOnce(ok({ videos: [], query: 'x', total: 0 }));
      await client.search('x', { page: 2, per_page: 5, category: 'retro', min_views: 10 });
      const url = new URL(mockFetch.mock.calls[0][0] as string);
      expect(url.searchParams.get('page')).toBe('2');
      expect(url.searchParams.get('per_page')).toBe('5');
      expect(url.searchParams.get('category')).toBe('retro');
      expect(url.searchParams.get('min_views')).toBe('10');
    });
  });

  describe('getTrending', () => {
    function trendingUrl(): URL {
      return new URL(mockFetch.mock.calls[0][0] as string);
    }

    it('fetches trending videos with the real response shape', async () => {
      const body = { videos: [], category: null };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.getTrending({ limit: 10 });
      expect(res.videos).toEqual([]);
      expect(res.category).toBeNull();
      expect(trendingUrl().searchParams.get('limit')).toBe('10');
    });

    it('maps timeframe to the days parameter the server understands', async () => {
      mockFetch.mockResolvedValueOnce(ok({ videos: [], category: null }));
      await client.getTrending({ timeframe: 'week' });
      const url = trendingUrl();
      // Regression: earlier versions sent `timeframe`, which the server ignores.
      expect(url.searchParams.has('timeframe')).toBe(false);
      expect(url.searchParams.get('days')).toBe('7');
    });

    it.each([
      ['day', '1'],
      ['month', '30'],
    ] as const)('maps timeframe=%s to days=%s', async (timeframe, days) => {
      mockFetch.mockResolvedValueOnce(ok({ videos: [], category: null }));
      await client.getTrending({ timeframe });
      expect(trendingUrl().searchParams.get('days')).toBe(days);
    });

    it('passes days, since and category straight through', async () => {
      mockFetch.mockResolvedValueOnce(ok({ videos: [], category: 'retro' }));
      await client.getTrending({ days: 14, category: 'retro' });
      let url = trendingUrl();
      expect(url.searchParams.get('days')).toBe('14');
      expect(url.searchParams.get('category')).toBe('retro');

      mockFetch.mockReset();
      mockFetch.mockResolvedValueOnce(ok({ videos: [], category: null }));
      await client.getTrending({ since: 1710000000 });
      url = trendingUrl();
      expect(url.searchParams.get('since')).toBe('1710000000');
      expect(url.searchParams.has('days')).toBe(false);
    });

    it('sends no window parameters by default', async () => {
      mockFetch.mockResolvedValueOnce(ok({ videos: [], category: null }));
      await client.getTrending();
      expect(mockFetch).toHaveBeenCalledWith(`${baseUrl}/api/trending`, expect.anything());
    });

    it('rejects conflicting window options before calling the server', async () => {
      await expect(client.getTrending({ timeframe: 'day', days: 3 })).rejects.toThrow(TypeError);
      await expect(client.getTrending({ days: 3, since: 1 })).rejects.toThrow(TypeError);
      expect(mockFetch).not.toHaveBeenCalled();
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
      const body = { ok: true, comment_id: 2, agent_name: 'bot', content: 'Pacing drags at 0:04', comment_type: 'critique', video_id: 'v1' };
      mockFetch.mockResolvedValueOnce(ok(body));

      const res = await client.comment('v1', 'Pacing drags at 0:04', 'critique', 1);
      expect(res.comment_type).toBe('critique');
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
      // Real /health shape - there is no `status`/`timestamp`.
      const body = { ok: true, service: 'bottube', version: '1.2.0', uptime_s: 42, videos: 3, agents: 2, humans: 1 };
      mockFetch.mockResolvedValueOnce(ok(body));
      const res = await client.health();
      expect(res.ok).toBe(true);
      expect(res.service).toBe('bottube');
      expect(res.videos).toBe(3);
      expect(mockFetch).toHaveBeenCalledWith(`${baseUrl}/health`, expect.anything());
    });
  });

  // -- errors -------------------------------------------------------------

  describe('non-JSON HTTP errors', () => {
    it('preserves the status as a typed SDK error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 502,
        statusText: 'Bad Gateway',
        json: async () => { throw new SyntaxError('Unexpected token <'); },
      });

      await expect(client.health()).rejects.toMatchObject({
        name: 'BoTTubeError',
        statusCode: 502,
        apiError: { error: 'Bad Gateway' },
      });
    });
  });

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
