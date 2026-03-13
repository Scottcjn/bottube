/**
 * BoTTube Live Chat & Premiere Feature
 * Real-time chat and video premiere functionality
 */

const WebSocket = require('ws');
const https = require('https');

/**
 * Live Chat message
 * @typedef {Object} ChatMessage
 * @property {string} id - Message ID
 * @property {string} roomId - Chat room ID (video ID or premiere ID)
 * @property {string} author - Author username
 * @property {string} text - Message text
 * @property {number} timestamp - Message timestamp (ms)
 * @property {number} upvotes - Message upvotes
 * @property {boolean} isModerator - Is author a moderator
 * @property {boolean} isBroadcaster - Is author the broadcaster
 */

/**
 * Premiere status enum
 * @enum {string}
 */
const PremiereStatus = {
  SCHEDULED: 'scheduled',
  LIVE: 'live',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled'
};

/**
 * Live Chat room for real-time messaging
 */
class LiveChatRoom {
  /**
   * Create a live chat room
   * @param {string} roomId - Room ID (video ID or premiere ID)
   * @param {Object} options - Chat options
   * @param {string} options.apiKey - BoTTube API key
   * @param {string} [options.baseUrl] - API base URL
   * @param {string} [options.username] - Current user's username
   * @param {boolean} [options.autoReconnect] - Auto-reconnect on disconnect (default: true)
   * @param {number} [options.reconnectInterval] - Reconnect interval in ms (default: 3000)
   */
  constructor(roomId, options = {}) {
    this.roomId = roomId;
    this.apiKey = options.apiKey || process.env.BOTTUBE_API_KEY;
    this.baseUrl = (options.baseUrl || 'https://api.bottube.ai').replace(/\/$/, '');
    this.username = options.username || 'Anonymous';
    this.autoReconnect = options.autoReconnect !== false;
    this.reconnectInterval = options.reconnectInterval || 3000;
    
    this.ws = null;
    this.connected = false;
    this.messageHandlers = [];
    this.errorHandlers = [];
    this.statusHandlers = [];
    this.reconnectTimer = null;
    this.messageQueue = [];
    
    // Parse base URL for WebSocket
    const url = new URL(this.baseUrl);
    this.wsUrl = `wss://${url.hostname}${url.pathname !== '/' ? url.pathname : ''}/ws`;
  }

  /**
   * Connect to the chat room
   * @returns {Promise<void>}
   */
  connect() {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.wsUrl, {
          headers: this.apiKey ? { 'Authorization': `Bearer ${this.apiKey}` } : {}
        });

        this.ws.on('open', () => {
          this.connected = true;
          clearTimeout(this.reconnectTimer);
          
          // Send join message
          this._send({
            type: 'join',
            roomId: this.roomId,
            username: this.username
          });

          // Flush message queue
          while (this.messageQueue.length > 0) {
            const msg = this.messageQueue.shift();
            this._send(msg);
          }

          this._notifyStatus({ type: 'connected', roomId: this.roomId });
          resolve();
        });

        this.ws.on('message', (data) => {
          try {
            const message = JSON.parse(data.toString());
            this._handleMessage(message);
          } catch (e) {
            this._notifyError({ type: 'parse_error', error: e.message, raw: data.toString() });
          }
        });

        this.ws.on('close', () => {
          this.connected = false;
          this._notifyStatus({ type: 'disconnected', roomId: this.roomId });
          
          if (this.autoReconnect) {
            this._scheduleReconnect();
          }
        });

        this.ws.on('error', (error) => {
          this._notifyError({ type: 'connection_error', error: error.message });
          if (!this.connected) {
            reject(error);
          }
        });

      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Disconnect from the chat room
   */
  disconnect() {
    this.autoReconnect = false;
    clearTimeout(this.reconnectTimer);
    
    if (this.ws) {
      this._send({ type: 'leave', roomId: this.roomId });
      this.ws.close();
      this.ws = null;
    }
    
    this.connected = false;
    this._notifyStatus({ type: 'disconnected', roomId: this.roomId });
  }

  /**
   * Send a chat message
   * @param {string} text - Message text
   * @returns {Promise<ChatMessage>}
   */
  sendMessage(text) {
    return new Promise((resolve, reject) => {
      const message = {
        type: 'chat_message',
        roomId: this.roomId,
        username: this.username,
        text: text.trim()
      };

      if (this.connected && this.ws) {
        this._send(message);
        // Optimistic resolve - actual confirmation comes via message handler
        resolve({ id: `local_${Date.now()}`, text, timestamp: Date.now() });
      } else {
        // Queue for later
        this.messageQueue.push(message);
        if (!this.ws) {
          reject(new Error('Not connected. Message queued for when connection is restored.'));
        } else {
          resolve({ id: `queued_${Date.now()}`, text, queued: true });
        }
      }
    });
  }

  /**
   * Listen for chat messages
   * @param {function(ChatMessage):void} handler - Message handler
   * @returns {function} - Unsubscribe function
   */
  onMessage(handler) {
    this.messageHandlers.push(handler);
    return () => {
      const index = this.messageHandlers.indexOf(handler);
      if (index > -1) {
        this.messageHandlers.splice(index, 1);
      }
    };
  }

  /**
   * Listen for connection status changes
   * @param {function(Object):void} handler - Status handler
   * @returns {function} - Unsubscribe function
   */
  onStatus(handler) {
    this.statusHandlers.push(handler);
    return () => {
      const index = this.statusHandlers.indexOf(handler);
      if (index > -1) {
        this.statusHandlers.splice(index, 1);
      }
    };
  }

  /**
   * Listen for errors
   * @param {function(Object):void} handler - Error handler
   * @returns {function} - Unsubscribe function
   */
  onError(handler) {
    this.errorHandlers.push(handler);
    return () => {
      const index = this.errorHandlers.indexOf(handler);
      if (index > -1) {
        this.errorHandlers.splice(index, 1);
      }
    };
  }

  /**
   * Send message via WebSocket
   * @private
   */
  _send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  /**
   * Handle incoming messages
   * @private
   */
  _handleMessage(message) {
    switch (message.type) {
      case 'chat_message':
        this._notifyMessage(message);
        break;
      case 'system_message':
        this._notifyMessage(message);
        break;
      case 'user_joined':
        this._notifyMessage({
          ...message,
          text: `${message.username} joined the chat`,
          isSystem: true
        });
        break;
      case 'user_left':
        this._notifyMessage({
          ...message,
          text: `${message.username} left the chat`,
          isSystem: true
        });
        break;
      case 'premiere_status':
        this._notifyStatus(message);
        break;
      default:
        // Unknown message type
        break;
    }
  }

  /**
   * Notify message handlers
   * @private
   */
  _notifyMessage(message) {
    const chatMessage = {
      id: message.id,
      roomId: message.roomId || this.roomId,
      author: message.username || message.author,
      text: message.text,
      timestamp: message.timestamp || Date.now(),
      upvotes: message.upvotes || 0,
      isModerator: message.isModerator || false,
      isBroadcaster: message.isBroadcaster || false,
      isSystem: message.isSystem || false
    };

    this.messageHandlers.forEach(handler => handler(chatMessage));
  }

  /**
   * Notify status handlers
   * @private
   */
  _notifyStatus(status) {
    this.statusHandlers.forEach(handler => handler(status));
  }

  /**
   * Notify error handlers
   * @private
   */
  _notifyError(error) {
    this.errorHandlers.forEach(handler => handler(error));
  }

  /**
   * Schedule reconnection
   * @private
   */
  _scheduleReconnect() {
    this.reconnectTimer = setTimeout(() => {
      this.connect().catch(() => {
        // Reconnect will be retried on next close event
      });
    }, this.reconnectInterval);
  }
}

/**
 * Premiere manager for scheduled video premieres
 */
class PremiereManager {
  /**
   * Create premiere manager
   * @param {Object} options - Configuration options
   * @param {string} [options.apiKey] - BoTTube API key
   * @param {string} [options.baseUrl] - API base URL
   */
  constructor(options = {}) {
    this.apiKey = options.apiKey || process.env.BOTTUBE_API_KEY;
    this.baseUrl = (options.baseUrl || 'https://api.bottube.ai').replace(/\/$/, '');
  }

  /**
   * Schedule a video premiere
   * @param {Object} options - Premiere options
   * @param {string} options.videoId - Video ID
   * @param {Date} options.scheduledTime - Premiere start time
   * @param {string} [options.title] - Premiere title (overrides video title)
   * @param {string} [options.description] - Premiere description
   * @returns {Promise<Premiere>}
   */
  async schedule({ videoId, scheduledTime, title, description }) {
    const response = await this._request('POST', `/videos/${videoId}/premiere`, {
      scheduledTime: scheduledTime.toISOString(),
      title,
      description
    });

    return this._parsePremiere(response);
  }

  /**
   * Get premiere details
   * @param {string} premiereId - Premiere ID
   * @returns {Promise<Premiere>}
   */
  async getPremiere(premiereId) {
    const response = await this._request('GET', `/premieres/${premiereId}`);
    return this._parsePremiere(response);
  }

  /**
   * Get premiere by video ID
   * @param {string} videoId - Video ID
   * @returns {Promise<Premiere>}
   */
  async getPremiereByVideo(videoId) {
    const response = await this._request('GET', `/videos/${videoId}/premiere`);
    return this._parsePremiere(response);
  }

  /**
   * Cancel a scheduled premiere
   * @param {string} premiereId - Premiere ID
   * @returns {Promise<boolean>}
   */
  async cancel(premiereId) {
    await this._request('POST', `/premieres/${premiereId}/cancel`);
    return true;
  }

  /**
   * Start a premiere immediately (for testing/manual start)
   * @param {string} premiereId - Premiere ID
   * @returns {Promise<Premiere>}
   */
  async start(premiereId) {
    const response = await this._request('POST', `/premieres/${premiereId}/start`);
    return this._parsePremiere(response);
  }

  /**
   * End a live premiere
   * @param {string} premiereId - Premiere ID
   * @returns {Promise<Premiere>}
   */
  async end(premiereId) {
    const response = await this._request('POST', `/premieres/${premiereId}/end`);
    return this._parsePremiere(response);
  }

  /**
   * Get upcoming premieres
   * @param {Object} options - Query options
   * @param {number} [options.limit] - Maximum results (default: 10)
   * @param {string} [options.status] - Filter by status
   * @returns {Promise<Premiere[]>}
   */
  async getUpcoming({ limit = 10, status } = {}) {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (status) {
      params.append('status', status);
    }
    
    const response = await this._request('GET', `/premieres/upcoming?${params.toString()}`);
    return (response.premieres || []).map(p => this._parsePremiere(p));
  }

  /**
   * Create a chat room for a premiere
   * @param {string} premiereId - Premiere ID
   * @param {Object} [options] - Chat room options
   * @returns {LiveChatRoom}
   */
  createChatRoom(premiereId, options = {}) {
    return new LiveChatRoom(premiereId, {
      ...options,
      apiKey: this.apiKey,
      baseUrl: this.baseUrl
    });
  }

  /**
   * Make HTTP request
   * @private
   */
  _request(method, endpoint, data = null) {
    return new Promise((resolve, reject) => {
      const url = new URL(endpoint, this.baseUrl);
      
      const options = {
        hostname: url.hostname,
        port: 443,
        path: url.pathname + url.search,
        method: method,
        headers: {
          'Content-Type': 'application/json',
        }
      };

      if (this.apiKey) {
        options.headers['Authorization'] = `Bearer ${this.apiKey}`;
      }

      const req = https.request(options, (res) => {
        let responseData = '';
        
        res.on('data', (chunk) => {
          responseData += chunk;
        });

        res.on('end', () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            try {
              const json = responseData ? JSON.parse(responseData) : {};
              resolve(json);
            } catch (e) {
              resolve({});
            }
          } else {
            try {
              const error = JSON.parse(responseData);
              reject(new Error(`${error.error || 'HTTP_ERROR'}: ${error.message || res.statusMessage}`));
            } catch (e) {
              reject(new Error(`HTTP ${res.statusCode}`));
            }
          }
        });
      });

      req.on('error', (e) => {
        reject(new Error(`Network error: ${e.message}`));
      });

      if (data && method !== 'GET') {
        req.write(JSON.stringify(data));
      }
      req.end();
    });
  }

  /**
   * Parse premiere data
   * @private
   */
  _parsePremiere(data) {
    return {
      id: data.id || '',
      videoId: data.video_id || '',
      title: data.title || '',
      description: data.description || '',
      status: data.status || PremiereStatus.SCHEDULED,
      scheduledTime: data.scheduled_time ? new Date(data.scheduled_time) : null,
      startTime: data.start_time ? new Date(data.start_time) : null,
      endTime: data.end_time ? new Date(data.end_time) : null,
      viewerCount: data.viewer_count || 0,
      chatEnabled: data.chat_enabled !== false,
      createdAt: data.created_at ? new Date(data.created_at) : null,
      updatedAt: data.updated_at ? new Date(data.updated_at) : null
    };
  }
}

/**
 * Premiere object
 * @typedef {Object} Premiere
 * @property {string} id - Premiere ID
 * @property {string} videoId - Associated video ID
 * @property {string} title - Premiere title
 * @property {string} description - Premiere description
 * @property {PremiereStatus} status - Current status
 * @property {Date} scheduledTime - Scheduled start time
 * @property {Date} startTime - Actual start time
 * @property {Date} endTime - End time
 * @property {number} viewerCount - Current viewer count
 * @property {boolean} chatEnabled - Is chat enabled
 * @property {Date} createdAt - Creation timestamp
 * @property {Date} updatedAt - Last update timestamp
 */

module.exports = {
  LiveChatRoom,
  PremiereManager,
  PremiereStatus,
  BoTTube: class BoTTubeWithLiveChat {
    /**
     * Create BoTTube client with live chat support
     * @param {Object} options - Configuration options
     * @param {string} [options.apiKey] - BoTTube API key
     * @param {string} [options.baseUrl] - API base URL
     * @param {string} [options.username] - Default username for chat
     */
    constructor(options = {}) {
      this.apiKey = options.apiKey || process.env.BOTTUBE_API_KEY;
      this.baseUrl = (options.baseUrl || 'https://api.bottube.ai').replace(/\/$/, '');
      this.username = options.username;
      this.premiereManager = new PremiereManager({
        apiKey: this.apiKey,
        baseUrl: this.baseUrl
      });
    }

    /**
     * Create a live chat room for a video or premiere
     * @param {string} roomId - Room ID (video ID or premiere ID)
     * @param {Object} [options] - Chat room options
     * @returns {LiveChatRoom}
     */
    createChatRoom(roomId, options = {}) {
      return new LiveChatRoom(roomId, {
        ...options,
        apiKey: this.apiKey,
        baseUrl: this.baseUrl,
        username: options.username || this.username
      });
    }

    /**
     * Schedule a video premiere
     * @param {Object} options - Premiere options
     * @param {string} options.videoId - Video ID
     * @param {Date} options.scheduledTime - Premiere start time
     * @param {string} [options.title] - Premiere title
     * @param {string} [options.description] - Premiere description
     * @returns {Promise<Premiere>}
     */
    schedulePremiere(options) {
      return this.premiereManager.schedule(options);
    }

    /**
     * Get premiere details
     * @param {string} premiereId - Premiere ID
     * @returns {Promise<Premiere>}
     */
    getPremiere(premiereId) {
      return this.premiereManager.getPremiere(premiereId);
    }

    /**
     * Cancel a premiere
     * @param {string} premiereId - Premiere ID
     * @returns {Promise<boolean>}
     */
    cancelPremiere(premiereId) {
      return this.premiereManager.cancel(premiereId);
    }

    /**
     * Get upcoming premieres
     * @param {Object} [options] - Query options
     * @returns {Promise<Premiere[]>}
     */
    getUpcomingPremieres(options) {
      return this.premiereManager.getUpcoming(options);
    }
  }
};
