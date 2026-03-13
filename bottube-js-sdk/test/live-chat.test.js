/**
 * Tests for Live Chat & Premiere features
 */

const { 
  BoTTube, 
  LiveChatRoom, 
  PremiereManager, 
  PremiereStatus,
  BoTTubeError 
} = require('../index');

describe('LiveChatRoom', () => {
  let chatRoom;

  beforeEach(() => {
    chatRoom = new LiveChatRoom('test-room-123', {
      apiKey: 'test-api-key',
      username: 'TestUser',
      autoReconnect: false
    });
  });

  afterEach(() => {
    if (chatRoom) {
      chatRoom.disconnect();
    }
  });

  test('should create chat room with correct configuration', () => {
    expect(chatRoom.roomId).toBe('test-room-123');
    expect(chatRoom.apiKey).toBe('test-api-key');
    expect(chatRoom.username).toBe('TestUser');
    expect(chatRoom.connected).toBe(false);
  });

  test('should use environment variable for API key if not provided', () => {
    process.env.BOTTUBE_API_KEY = 'env-api-key';
    const room = new LiveChatRoom('test-room');
    expect(room.apiKey).toBe('env-api-key');
    delete process.env.BOTTUBE_API_KEY;
  });

  test('should have default reconnect settings', () => {
    const room = new LiveChatRoom('test-room');
    expect(room.autoReconnect).toBe(true);
    expect(room.reconnectInterval).toBe(3000);
  });

  test('should allow custom reconnect settings', () => {
    const room = new LiveChatRoom('test-room', {
      autoReconnect: false,
      reconnectInterval: 5000
    });
    expect(room.autoReconnect).toBe(false);
    expect(room.reconnectInterval).toBe(5000);
  });

  test('should queue messages when not connected', async () => {
    // Mock WebSocket to simulate disconnection
    chatRoom.ws = null;
    chatRoom.connected = false;

    const result = await chatRoom.sendMessage('Test message');
    expect(result.queued).toBe(true);
    expect(result.text).toBe('Test message');
  });

  test('should register message handler', () => {
    const handler = jest.fn();
    const unsubscribe = chatRoom.onMessage(handler);
    
    expect(typeof unsubscribe).toBe('function');
    
    // Call unsubscribe
    unsubscribe();
    
    // Handler should be removed
    expect(chatRoom.messageHandlers).not.toContain(handler);
  });

  test('should register status handler', () => {
    const handler = jest.fn();
    const unsubscribe = chatRoom.onStatus(handler);
    
    expect(typeof unsubscribe).toBe('function');
    unsubscribe();
  });

  test('should register error handler', () => {
    const handler = jest.fn();
    const unsubscribe = chatRoom.onError(handler);
    
    expect(typeof unsubscribe).toBe('function');
    unsubscribe();
  });

  test('should disconnect cleanly', () => {
    chatRoom.connect = jest.fn();
    chatRoom.disconnect();
    expect(chatRoom.connected).toBe(false);
    expect(chatRoom.autoReconnect).toBe(false);
  });
});

describe('PremiereManager', () => {
  let manager;

  beforeEach(() => {
    manager = new PremiereManager({
      apiKey: 'test-api-key',
      baseUrl: 'https://test-api.bottube.ai'
    });
  });

  test('should create manager with correct configuration', () => {
    expect(manager.apiKey).toBe('test-api-key');
    expect(manager.baseUrl).toBe('https://test-api.bottube.ai');
  });

  test('should use environment variable for API key', () => {
    process.env.BOTTUBE_API_KEY = 'env-api-key';
    const mgr = new PremiereManager();
    expect(mgr.apiKey).toBe('env-api-key');
    delete process.env.BOTTUBE_API_KEY;
  });

  test('should parse premiere data correctly', () => {
    const rawData = {
      id: 'premiere-123',
      video_id: 'video-456',
      title: 'Test Premiere',
      description: 'Test Description',
      status: 'scheduled',
      scheduled_time: '2024-01-01T20:00:00Z',
      chat_enabled: true,
      viewer_count: 0
    };

    const premiere = manager._parsePremiere(rawData);

    expect(premiere.id).toBe('premiere-123');
    expect(premiere.videoId).toBe('video-456');
    expect(premiere.title).toBe('Test Premiere');
    expect(premiere.status).toBe(PremiereStatus.SCHEDULED);
    expect(premiere.scheduledTime).toBeInstanceOf(Date);
    expect(premiere.chatEnabled).toBe(true);
    expect(premiere.viewerCount).toBe(0);
  });

  test('should handle null dates in premiere data', () => {
    const rawData = {
      id: 'premiere-123',
      status: 'scheduled'
    };

    const premiere = manager._parsePremiere(rawData);

    expect(premiere.scheduledTime).toBe(null);
    expect(premiere.startTime).toBe(null);
    expect(premiere.endTime).toBe(null);
  });
});

describe('PremiereStatus', () => {
  test('should have correct status values', () => {
    expect(PremiereStatus.SCHEDULED).toBe('scheduled');
    expect(PremiereStatus.LIVE).toBe('live');
    expect(PremiereStatus.COMPLETED).toBe('completed');
    expect(PremiereStatus.CANCELLED).toBe('cancelled');
  });
});

describe('BoTTube with Live Chat', () => {
  let client;

  beforeEach(() => {
    client = new BoTTube({
      apiKey: 'test-api-key',
      username: 'TestBot'
    });
  });

  test('should create client with live chat support', () => {
    expect(client.apiKey).toBe('test-api-key');
    expect(client.username).toBe('TestBot');
    expect(client.premiereManager).toBeInstanceOf(PremiereManager);
  });

  test('should create chat room', () => {
    const chatRoom = client.createChatRoom('video-123');
    expect(chatRoom).toBeInstanceOf(LiveChatRoom);
    expect(chatRoom.roomId).toBe('video-123');
    expect(chatRoom.username).toBe('TestBot');
  });

  test('should override username for specific chat room', () => {
    const chatRoom = client.createChatRoom('video-123', {
      username: 'CustomUser'
    });
    expect(chatRoom.username).toBe('CustomUser');
  });

  test('should have premiere manager methods', () => {
    expect(typeof client.schedulePremiere).toBe('function');
    expect(typeof client.getPremiere).toBe('function');
    expect(typeof client.cancelPremiere).toBe('function');
    expect(typeof client.getUpcomingPremieres).toBe('function');
  });
});

describe('Integration Scenarios', () => {
  test('should handle complete premiere workflow', () => {
    const client = new BoTTube({ apiKey: 'test-key' });

    // Verify all methods exist
    expect(typeof client.schedulePremiere).toBe('function');
    expect(typeof client.createChatRoom).toBe('function');
    expect(typeof client.getUpcomingPremieres).toBe('function');
  });

  test('should chain chat room operations', async () => {
    const chatRoom = new LiveChatRoom('test-room', {
      apiKey: 'test-key',
      autoReconnect: false
    });

    const messageHandler = jest.fn();
    const statusHandler = jest.fn();
    const errorHandler = jest.fn();

    chatRoom.onMessage(messageHandler);
    chatRoom.onStatus(statusHandler);
    chatRoom.onError(errorHandler);

    // Verify handlers are registered
    expect(chatRoom.messageHandlers).toContain(messageHandler);
    expect(chatRoom.statusHandlers).toContain(statusHandler);
    expect(chatRoom.errorHandlers).toContain(errorHandler);

    chatRoom.disconnect();
  });
});
