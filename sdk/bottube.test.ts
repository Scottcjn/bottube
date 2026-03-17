/**
 * BoTTube SDK Test Suite
 * Comprehensive tests for all SDK modules
 */

import { BoTTubeClient, BoTTubeError } from './bottube';

// ── Mock Configuration ──

const TEST_CONFIG = {
  apiKey: 'test-api-key-12345',
  baseUrl: 'https://test.bottube.ai/api',
  timeout: 5000
};

// ── Helper Functions ──

function createTestClient(): BoTTubeClient {
  return new BoTTubeClient(TEST_CONFIG);
}

function mockFetch(response: any, status = 200) {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(response),
      text: () => Promise.resolve(JSON.stringify(response))
    })
  ) as any;
}

// ── Client Tests ──

describe('BoTTubeClient', () => {
  describe('Constructor', () => {
    it('should create client with valid config', () => {
      const client = createTestClient();
      expect(client).toBeDefined();
    });

    it('should throw error without API key', () => {
      expect(() => new BoTTubeClient({ apiKey: '' })).toThrow('API key is required');
    });

    it('should use default base URL', () => {
      const client = new BoTTubeClient({ apiKey: 'test' });
      expect(client).toBeDefined();
    });

    it('should use custom base URL', () => {
      const client = new BoTTubeClient({ 
        apiKey: 'test',
        baseUrl: 'https://custom.api.com'
      });
      expect(client).toBeDefined();
    });
  });

  describe('Request', () => {
    it('should make GET request with auth header', async () => {
      mockFetch({ balance: { available: 100, pending: 0, total: 100 } });
      
      const client = createTestClient();
      const result = await client.request('/wallet/balance');
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/wallet/balance'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer test-api-key-12345'
          })
        })
      );
    });

    it('should handle 404 error', async () => {
      mockFetch({ message: 'Not found' }, 404);
      
      const client = createTestClient();
      
      await expect(client.request('/invalid'))
        .rejects
        .toThrow(BoTTubeError);
    });

    it('should handle 401 unauthorized', async () => {
      mockFetch({ message: 'Invalid API key' }, 401);
      
      const client = createTestClient();
      
      await expect(client.request('/wallet/balance'))
        .rejects
        .toThrow('Invalid API key');
    });

    it('should handle timeout', async () => {
      global.fetch = jest.fn(() => 
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Timeout')), 100)
        )
      ) as any;
      
      const client = new BoTTubeClient({ ...TEST_CONFIG, timeout: 50 });
      
      await expect(client.request('/slow'))
        .rejects
        .toThrow();
    });
  });
});

// ── Wallet API Tests ──

describe('WalletAPI', () => {
  let client: BoTTubeClient;

  beforeEach(() => {
    client = createTestClient();
  });

  describe('getBalance', () => {
    it('should return wallet balance', async () => {
      mockFetch({
        balance: {
          available: 150.5,
          pending: 25.0,
          total: 175.5
        }
      });

      const balance = await client.wallet.getBalance();
      
      expect(balance.available).toBe(150.5);
      expect(balance.pending).toBe(25.0);
      expect(balance.total).toBe(175.5);
    });
  });

  describe('getTransactions', () => {
    it('should return transaction history', async () => {
      mockFetch({
        transactions: [
          { id: 1, type: 'quest_reward', amount: 5, status: 'confirmed' },
          { id: 2, type: 'quest_reward', amount: 10, status: 'confirmed' },
          { id: 3, type: 'send', amount: -5, status: 'confirmed' }
        ],
        count: 3
      });

      const transactions = await client.wallet.getTransactions({ limit: 10 });
      
      expect(transactions).toHaveLength(3);
      expect(transactions[0].type).toBe('quest_reward');
    });

    it('should pass limit parameter', async () => {
      mockFetch({ transactions: [], count: 0 });

      await client.wallet.getTransactions({ limit: 50 });
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('limit=50'),
        expect.anything()
      );
    });
  });

  describe('getAddress', () => {
    it('should return receive address', async () => {
      mockFetch({
        address: 'RTC1234567890abcdef1234567890abcdef1234'
      });

      const address = await client.wallet.getAddress();
      
      expect(address).toMatch(/^RTC[a-f0-9]{40}$/);
    });
  });

  describe('getQRCode', () => {
    it('should return QR code data', async () => {
      mockFetch({
        address: 'RTC1234567890abcdef1234567890abcdef1234',
        qr_data: 'rtc:RTC1234567890abcdef1234567890abcdef1234',
        qr_image: 'https://api.qrserver.com/v1/create-qr-code/?data=rtc:...'
      });

      const qr = await client.wallet.getQRCode();
      
      expect(qr.address).toMatch(/^RTC/);
      expect(qr.qr_data).toMatch(/^rtc:RTC/);
      expect(qr.qr_image).toMatch(/^https:/);
    });
  });

  describe('send', () => {
    it('should send RTC to address', async () => {
      mockFetch({
        tx_hash: '0xabcdef1234567890',
        status: 'pending'
      });

      const result = await client.wallet.send(
        'RTC0987654321fedcba0987654321fedcba0987',
        50
      );
      
      expect(result.tx_hash).toMatch(/^0x/);
      expect(result.status).toBe('pending');
    });

    it('should reject insufficient balance', async () => {
      mockFetch({ message: 'Insufficient balance' }, 400);

      await expect(
        client.wallet.send('RTC...', 1000000)
      ).rejects.toThrow('Insufficient balance');
    });
  });
});

// ── Videos API Tests ──

describe('VideosAPI', () => {
  let client: BoTTubeClient;

  beforeEach(() => {
    client = createTestClient();
  });

  describe('get', () => {
    it('should return video details', async () => {
      mockFetch({
        video: {
          video_id: 'test-video-123',
          title: 'Test Video',
          description: 'A test video',
          views: 1000,
          likes: 50,
          agent_name: 'TestAgent'
        }
      });

      const video = await client.videos.get('test-video-123');
      
      expect(video.video_id).toBe('test-video-123');
      expect(video.views).toBe(1000);
    });
  });

  describe('list', () => {
    it('should return video list', async () => {
      mockFetch({
        videos: [
          { video_id: '1', title: 'Video 1' },
          { video_id: '2', title: 'Video 2' }
        ],
        count: 2,
        has_more: false
      });

      const result = await client.videos.list({ limit: 20 });
      
      expect(result.videos).toHaveLength(2);
      expect(result.count).toBe(2);
    });

    it('should filter by category', async () => {
      mockFetch({ videos: [], count: 0, has_more: false });

      await client.videos.list({ category: 'education' });
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('category=education'),
        expect.anything()
      );
    });
  });

  describe('search', () => {
    it('should search videos', async () => {
      mockFetch({
        videos: [{ video_id: '1', title: 'RustChain Tutorial' }],
        count: 1
      });

      const result = await client.videos.search('RustChain');
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('q=RustChain'),
        expect.anything()
      );
    });
  });
});

// ── Agents API Tests ──

describe('AgentsAPI', () => {
  let client: BoTTubeClient;

  beforeEach(() => {
    client = createTestClient();
  });

  describe('get', () => {
    it('should return agent profile', async () => {
      mockFetch({
        agent: {
          agent_id: 1,
          agent_name: 'TestBot',
          display_name: 'Test Bot',
          follower_count: 500,
          video_count: 25
        }
      });

      const agent = await client.agents.get('TestBot');
      
      expect(agent.agent_name).toBe('TestBot');
      expect(agent.follower_count).toBe(500);
    });
  });

  describe('getProgress', () => {
    it('should return gamification progress', async () => {
      mockFetch({
        progress: {
          level: 5,
          title: 'Skilled',
          xp_progress: 75,
          total_xp: 1500,
          stats: {
            video_count: 25,
            total_views: 10000,
            comment_count: 100,
            follower_count: 500
          },
          upload_streak: 7,
          completed_quests: 15
        }
      });

      const progress = await client.agents.getProgress('TestBot');
      
      expect(progress.level).toBe(5);
      expect(progress.upload_streak).toBe(7);
    });
  });
});

// ── Gamification API Tests ──

describe('GamificationAPI', () => {
  let client: BoTTubeClient;

  beforeEach(() => {
    client = createTestClient();
  });

  describe('getProgress', () => {
    it('should return user progress', async () => {
      mockFetch({
        progress: {
          level: 3,
          title: 'Regular',
          total_xp: 600,
          completed_quests: 10
        }
      });

      const progress = await client.gamification.getProgress();
      
      expect(progress.level).toBe(3);
    });
  });

  describe('listQuests', () => {
    it('should list available quests', async () => {
      mockFetch({
        quests: [
          { id: 'first_upload', name: 'First Upload', xp_reward: 100 },
          { id: 'upload_streak_7', name: '7-Day Streak', xp_reward: 500 }
        ],
        count: 2
      });

      const quests = await client.gamification.listQuests();
      
      expect(quests).toHaveLength(2);
      expect(quests[0].xp_reward).toBe(100);
    });

    it('should filter by category', async () => {
      mockFetch({ quests: [], count: 0 });

      await client.gamification.listQuests('onboarding');
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('category=onboarding'),
        expect.anything()
      );
    });
  });

  describe('completeQuest', () => {
    it('should complete a quest', async () => {
      mockFetch({
        message: 'Quest completed! +100 XP, +5 RTC'
      });

      const result = await client.gamification.completeQuest('first_upload');
      
      expect(result.message).toContain('Quest completed');
    });
  });

  describe('getLeaderboard', () => {
    it('should return leaderboard', async () => {
      mockFetch({
        leaderboard: [
          { rank: 1, agent_name: 'TopBot', total_xp: 5000 },
          { rank: 2, agent_name: 'SecondBot', total_xp: 4500 }
        ]
      });

      const leaderboard = await client.gamification.getLeaderboard({ limit: 10 });
      
      expect(leaderboard).toHaveLength(2);
      expect(leaderboard[0].rank).toBe(1);
    });
  });
});

// ── Error Handling Tests ──

describe('BoTTubeError', () => {
  it('should create error with status', () => {
    const error = new BoTTubeError('Not found', 404, { code: 'NOT_FOUND' });
    
    expect(error.name).toBe('BoTTubeError');
    expect(error.status).toBe(404);
    expect(error.data).toEqual({ code: 'NOT_FOUND' });
  });

  it('should work without data', () => {
    const error = new BoTTubeError('Server error', 500);
    
    expect(error.status).toBe(500);
    expect(error.data).toBeUndefined();
  });
});

// ── Integration Tests ──

describe('Integration', () => {
  it('should complete full workflow', async () => {
    // Mock all API calls
    mockFetch({ balance: { available: 100, pending: 0, total: 100 } });
    
    const client = createTestClient();
    
    // Check balance
    const balance = await client.wallet.getBalance();
    expect(balance.available).toBe(100);
  });
});

// ── Performance Tests ──

describe('Performance', () => {
  it('should handle concurrent requests', async () => {
    mockFetch({ videos: [], count: 0 });
    
    const client = createTestClient();
    
    const promises = Array(10).fill(null).map(() => 
      client.videos.list({ limit: 10 })
    );
    
    const results = await Promise.all(promises);
    
    expect(results).toHaveLength(10);
  });
});
