const { BoTTubeClient } = require('@bottube/sdk');
const { Client, GatewayIntentBits, EmbedBuilder } = require('discord.js');
const cron = require('node-cron');
const config = require('../config.json');

// Mock Discord.js for testing
jest.mock('discord.js', () => ({
  Client: jest.fn().mockImplementation(() => ({
    login: jest.fn().mockResolvedValue(),
    on: jest.fn(),
    channels: {
      cache: {
        get: jest.fn().mockReturnValue({
          send: jest.fn().mockResolvedValue()
        })
      }
    },
    user: { tag: 'TestBot#1234' }
  })),
  GatewayIntentBits: {
    Guilds: 1,
    GuildMessages: 512
  },
  EmbedBuilder: jest.fn().mockImplementation(() => ({
    setTitle: jest.fn().mockReturnThis(),
    setDescription: jest.fn().mockReturnThis(),
    setURL: jest.fn().mockReturnThis(),
    addFields: jest.fn().mockReturnThis(),
    setColor: jest.fn().mockReturnThis(),
    setTimestamp: jest.fn().mockReturnThis(),
    setFooter: jest.fn().mockReturnThis()
  }))
}));

// Mock node-cron
jest.mock('node-cron', () => ({
  schedule: jest.fn()
}));

// Mock config
jest.mock('../config.json', () => ({
  discord: {
    token: 'test_discord_token',
    channelId: '123456789'
  },
  bottube: {
    apiKey: 'test_api_key',
    baseUrl: 'https://api.bottube.com'
  },
  schedule: '0 */6 * * *',
  maxVideos: 3
}));

const TrendingBot = require('../src/bot');

describe('Discord Trending Bot', () => {
  let bot;
  let mockBoTTubeClient;
  let mockDiscordClient;

  beforeEach(() => {
    jest.clearAllMocks();

    mockBoTTubeClient = {
      getTrendingVideos: jest.fn(),
      getVideo: jest.fn()
    };

    mockDiscordClient = new Client();

    bot = new TrendingBot();
    bot.bottubeClient = mockBoTTubeClient;
    bot.discordClient = mockDiscordClient;
  });

  describe('Configuration Loading', () => {
    test('should load config correctly', () => {
      expect(bot.config.discord.token).toBe('test_discord_token');
      expect(bot.config.bottube.apiKey).toBe('test_api_key');
      expect(bot.config.maxVideos).toBe(3);
    });

    test('should validate required config fields', () => {
      const invalidConfig = { discord: {} };
      expect(() => {
        bot.validateConfig(invalidConfig);
      }).toThrow('Missing required Discord token');
    });
  });

  describe('BoTTube API Integration', () => {
    test('should fetch trending videos successfully', async () => {
      const mockVideos = [
        {
          id: 'vid1',
          title: 'Test Video 1',
          description: 'First test video',
          agent_id: 'agent1',
          views: 1500,
          created_at: '2024-01-15T10:00:00Z'
        },
        {
          id: 'vid2',
          title: 'Test Video 2',
          description: 'Second test video',
          agent_id: 'agent2',
          views: 2300,
          created_at: '2024-01-15T11:00:00Z'
        }
      ];

      mockBoTTubeClient.getTrendingVideos.mockResolvedValue({
        success: true,
        data: mockVideos
      });

      const result = await bot.fetchTrendingVideos();

      expect(mockBoTTubeClient.getTrendingVideos).toHaveBeenCalledWith({ limit: 3 });
      expect(result).toEqual(mockVideos);
    });

    test('should handle API errors gracefully', async () => {
      mockBoTTubeClient.getTrendingVideos.mockRejectedValue(
        new Error('API Error: Rate limit exceeded')
      );

      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();

      const result = await bot.fetchTrendingVideos();

      expect(result).toEqual([]);
      expect(consoleSpy).toHaveBeenCalledWith(
        'Failed to fetch trending videos:',
        expect.any(Error)
      );

      consoleSpy.mockRestore();
    });

    test('should handle empty API response', async () => {
      mockBoTTubeClient.getTrendingVideos.mockResolvedValue({
        success: true,
        data: []
      });

      const result = await bot.fetchTrendingVideos();

      expect(result).toEqual([]);
    });
  });

  describe('Discord Message Formatting', () => {
    test('should create properly formatted embed for video', () => {
      const video = {
        id: 'test_vid_123',
        title: 'Amazing AI Video',
        description: 'This is a test video description that might be quite long',
        agent_id: 'creative_agent',
        views: 4250,
        created_at: '2024-01-15T14:30:00Z'
      };

      const embed = bot.createVideoEmbed(video);
      const mockEmbed = new EmbedBuilder();

      expect(mockEmbed.setTitle).toHaveBeenCalledWith('Amazing AI Video');
      expect(mockEmbed.setURL).toHaveBeenCalledWith('https://bottube.com/watch/test_vid_123');
      expect(mockEmbed.setDescription).toHaveBeenCalledWith('This is a test video description that might be quite long');
      expect(mockEmbed.addFields).toHaveBeenCalledWith([
        { name: '👁️ Views', value: '4,250', inline: true },
        { name: '🤖 Agent', value: 'creative_agent', inline: true },
        { name: '📅 Posted', value: expect.any(String), inline: true }
      ]);
      expect(mockEmbed.setColor).toHaveBeenCalledWith(0x00AE86);
    });

    test('should truncate long descriptions', () => {
      const video = {
        id: 'test_vid',
        title: 'Test Video',
        description: 'A'.repeat(300),
        agent_id: 'test_agent',
        views: 100,
        created_at: '2024-01-15T12:00:00Z'
      };

      bot.createVideoEmbed(video);
      const mockEmbed = new EmbedBuilder();

      expect(mockEmbed.setDescription).toHaveBeenCalledWith(
        expect.stringMatching(/^A{247}\.\.\./)
      );
    });

    test('should format view counts with commas', () => {
      expect(bot.formatViewCount(1234)).toBe('1,234');
      expect(bot.formatViewCount(1234567)).toBe('1,234,567');
      expect(bot.formatViewCount(42)).toBe('42');
    });

    test('should format relative timestamps', () => {
      const now = new Date('2024-01-15T16:00:00Z');
      const twoHoursAgo = new Date('2024-01-15T14:00:00Z');

      jest.spyOn(Date, 'now').mockReturnValue(now.getTime());

      const result = bot.formatRelativeTime(twoHoursAgo.toISOString());
      expect(result).toBe('2 hours ago');

      Date.now.mockRestore();
    });
  });

  describe('Error Handling', () => {
    test('should handle Discord API errors', async () => {
      const mockChannel = {
        send: jest.fn().mockRejectedValue(new Error('Missing permissions'))
      };

      mockDiscordClient.channels = {
        cache: {
          get: jest.fn().mockReturnValue(mockChannel)
        }
      };

      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();

      await bot.postTrendingVideos();

      expect(consoleSpy).toHaveBeenCalledWith(
        'Failed to post trending videos:',
        expect.any(Error)
      );

      consoleSpy.mockRestore();
    });

    test('should handle missing Discord channel', async () => {
      mockDiscordClient.channels = {
        cache: {
          get: jest.fn().mockReturnValue(null)
        }
      };

      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();

      await bot.postTrendingVideos();

      expect(consoleSpy).toHaveBeenCalledWith(
        'Discord channel not found:',
        config.discord.channelId
      );

      consoleSpy.mockRestore();
    });

    test('should handle network timeouts', async () => {
      mockBoTTubeClient.getTrendingVideos.mockImplementation(() => {
        return new Promise((_, reject) => {
          setTimeout(() => reject(new Error('Request timeout')), 100);
        });
      });

      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();

      const result = await bot.fetchTrendingVideos();

      expect(result).toEqual([]);
      expect(consoleSpy).toHaveBeenCalled();

      consoleSpy.mockRestore();
    });
  });

  describe('Scheduling Logic', () => {
    test('should schedule cron job correctly', () => {
      bot.startScheduler();

      expect(cron.schedule).toHaveBeenCalledWith(
        config.schedule,
        expect.any(Function),
        { scheduled: true }
      );
    });

    test('should execute scheduled task', async () => {
      const mockVideos = [{
        id: 'scheduled_vid',
        title: 'Scheduled Video',
        description: 'Posted by scheduler',
        agent_id: 'scheduler_agent',
        views: 500,
        created_at: '2024-01-15T12:00:00Z'
      }];

      mockBoTTubeClient.getTrendingVideos.mockResolvedValue({
        success: true,
        data: mockVideos
      });

      const mockChannel = {
        send: jest.fn().mockResolvedValue()
      };

      mockDiscordClient.channels = {
        cache: {
          get: jest.fn().mockReturnValue(mockChannel)
        }
      };

      bot.startScheduler();

      // Get the scheduled function
      const scheduledFn = cron.schedule.mock.calls[0][1];
      await scheduledFn();

      expect(mockBoTTubeClient.getTrendingVideos).toHaveBeenCalled();
      expect(mockChannel.send).toHaveBeenCalled();
    });
  });

  describe('Bot Initialization', () => {
    test('should initialize Discord client correctly', () => {
      const bot = new TrendingBot();

      expect(Client).toHaveBeenCalledWith({
        intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages]
      });
    });

    test('should initialize BoTTube client with correct config', () => {
      const bot = new TrendingBot();

      expect(bot.bottubeClient).toBeDefined();
    });

    test('should set up Discord event handlers', () => {
      const bot = new TrendingBot();

      expect(mockDiscordClient.on).toHaveBeenCalledWith('ready', expect.any(Function));
      expect(mockDiscordClient.on).toHaveBeenCalledWith('error', expect.any(Function));
    });
  });

  describe('Integration Tests', () => {
    test('should complete full workflow successfully', async () => {
      const mockVideos = [
        {
          id: 'integration_vid',
          title: 'Integration Test Video',
          description: 'End-to-end test',
          agent_id: 'test_agent',
          views: 1000,
          created_at: '2024-01-15T15:00:00Z'
        }
      ];

      mockBoTTubeClient.getTrendingVideos.mockResolvedValue({
        success: true,
        data: mockVideos
      });

      const mockChannel = {
        send: jest.fn().mockResolvedValue({ id: 'message_123' })
      };

      mockDiscordClient.channels = {
        cache: {
          get: jest.fn().mockReturnValue(mockChannel)
        }
      };

      await bot.postTrendingVideos();

      expect(mockBoTTubeClient.getTrendingVideos).toHaveBeenCalled();
      expect(mockChannel.send).toHaveBeenCalledWith({
        embeds: expect.arrayContaining([expect.any(Object)])
      });
    });
  });
});
