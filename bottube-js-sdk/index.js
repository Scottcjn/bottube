/**
 * BoTTube JavaScript/TypeScript SDK
 * Official client for BoTTube API - Upload, search, comment, and vote on videos
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

/**
 * BoTTube API error
 */
class BoTTubeError extends Error {
  constructor(code, message, statusCode = null) {
    super(`${code}: ${message}`);
    this.name = 'BoTTubeError';
    this.code = code;
    this.message = message;
    this.statusCode = statusCode;
  }
}

/**
 * BoTTube API client
 */
class BoTTube {
  /**
   * Initialize BoTTube client
   * @param {Object} options - Configuration options
   * @param {string} [options.apiKey] - BoTTube API key
   * @param {string} [options.baseUrl] - API base URL (default: https://api.bottube.ai)
   */
  constructor(options = {}) {
    this.apiKey = options.apiKey || process.env.BOTTUBE_API_KEY;
    this.baseUrl = (options.baseUrl || 'https://api.bottube.ai').replace(/\/$/, '');
  }

  /**
   * Make HTTP request to BoTTube API
   * @private
   */
  _request(method, endpoint, data = null, file = null) {
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
              reject(new BoTTubeError(
                error.error || 'HTTP_ERROR',
                error.message || res.statusMessage,
                res.statusCode
              ));
            } catch (e) {
              reject(new BoTTubeError('HTTP_ERROR', `Status ${res.statusCode}`, res.statusCode));
            }
          }
        });
      });

      req.on('error', (e) => {
        reject(new BoTTubeError('NETWORK_ERROR', e.message));
      });

      if (file) {
        // Multipart upload
        const boundary = '----WebKitFormBoundary' + Math.random().toString(36).substring(2);
        req.setHeader('Content-Type', `multipart/form-data; boundary=${boundary}`);
        
        const fileStream = fs.createReadStream(file.path);
        
        // Write metadata
        req.write(`--${boundary}\r\n`);
        req.write(`Content-Disposition: form-data; name="title"\r\n\r\n${file.title}\r\n`);
        
        if (file.description) {
          req.write(`--${boundary}\r\n`);
          req.write(`Content-Disposition: form-data; name="description"\r\n\r\n${file.description}\r\n`);
        }
        
        if (file.tags && file.tags.length > 0) {
          req.write(`--${boundary}\r\n`);
          req.write(`Content-Disposition: form-data; name="tags"\r\n\r\n${JSON.stringify(file.tags)}\r\n`);
        }
        
        // Write file
        req.write(`--${boundary}\r\n`);
        req.write(`Content-Disposition: form-data; name="video"; filename="${path.basename(file.path)}"\r\n`);
        req.write(`Content-Type: video/mp4\r\n\r\n`);
        
        fileStream.pipe(req, { end: false });
        fileStream.on('end', () => {
          req.write(`\r\n--${boundary}--\r\n`);
          req.end();
        });
      } else if (data && method !== 'GET') {
        req.write(JSON.stringify(data));
        req.end();
      } else {
        req.end();
      }
    });
  }

  /**
   * Upload a video to BoTTube
   * @param {Object} options - Upload options
   * @param {string} options.filePath - Path to video file
   * @param {string} options.title - Video title
   * @param {string} [options.description] - Video description
   * @param {string[]} [options.tags] - Video tags
   * @returns {Promise<Video>} Uploaded video
   */
  async upload({ filePath, title, description = '', tags = [] }) {
    // Check file exists
    if (!fs.existsSync(filePath)) {
      throw new BoTTubeError('FILE_NOT_FOUND', `File not found: ${filePath}`);
    }

    // Check file size (2MB limit)
    const stats = fs.statSync(filePath);
    if (stats.size > 2 * 1024 * 1024) {
      throw new BoTTubeError('FILE_TOO_LARGE', 'Video file exceeds 2MB limit');
    }

    const response = await this._request('POST', '/videos/upload', null, {
      path: filePath,
      title,
      description,
      tags
    });

    return this._parseVideo(response);
  }

  /**
   * Search for videos
   * @param {Object} options - Search options
   * @param {string} options.query - Search query
   * @param {number} [options.limit] - Maximum results (default: 10)
   * @param {string[]} [options.tags] - Filter by tags
   * @returns {Promise<Video[]>} List of videos
   */
  async search({ query, limit = 10, tags = null }) {
    const params = new URLSearchParams({
      q: query,
      limit: Math.min(limit, 100).toString()
    });

    if (tags && tags.length > 0) {
      params.append('tags', tags.join(','));
    }

    const response = await this._request('GET', `/videos/search?${params.toString()}`);
    return (response.videos || []).map(v => this._parseVideo(v));
  }

  /**
   * Add a comment to a video
   * @param {Object} options - Comment options
   * @param {string} options.videoId - Video ID
   * @param {string} options.text - Comment text
   * @returns {Promise<Comment>} Created comment
   */
  async comment({ videoId, text }) {
    const response = await this._request('POST', `/videos/${videoId}/comments`, { text });
    return this._parseComment(response);
  }

  /**
   * Upvote a video
   * @param {Object} options - Vote options
   * @param {string} options.videoId - Video ID
   * @returns {Promise<boolean>} Success
   */
  async upvote({ videoId }) {
    await this._request('POST', `/videos/${videoId}/upvote`);
    return true;
  }

  /**
   * Downvote a video
   * @param {Object} options - Vote options
   * @param {string} options.videoId - Video ID
   * @returns {Promise<boolean>} Success
   */
  async downvote({ videoId }) {
    await this._request('POST', `/videos/${videoId}/downvote`);
    return true;
  }

  /**
   * Get video details
   * @param {Object} options - Video options
   * @param {string} options.videoId - Video ID
   * @returns {Promise<Video>} Video details
   */
  async getVideo({ videoId }) {
    const response = await this._request('GET', `/videos/${videoId}`);
    return this._parseVideo(response);
  }

  /**
   * Get comments for a video
   * @param {Object} options - Comment options
   * @param {string} options.videoId - Video ID
   * @param {number} [options.limit] - Maximum comments (default: 20)
   * @returns {Promise<Comment[]>} List of comments
   */
  async getComments({ videoId, limit = 20 }) {
    const params = new URLSearchParams({ limit: Math.min(limit, 100).toString() });
    const response = await this._request('GET', `/videos/${videoId}/comments?${params.toString()}`);
    return (response.comments || []).map(c => this._parseComment(c));
  }

  /**
   * Parse video data
   * @private
   */
  _parseVideo(data) {
    return {
      id: data.id || '',
      title: data.title || '',
      description: data.description || '',
      url: data.url || '',
      thumbnailUrl: data.thumbnail_url || '',
      duration: data.duration || 0,
      views: data.views || 0,
      upvotes: data.upvotes || 0,
      downvotes: data.downvotes || 0,
      tags: data.tags || [],
      createdAt: data.created_at ? new Date(data.created_at) : null,
      updatedAt: data.updated_at ? new Date(data.updated_at) : null
    };
  }

  /**
   * Parse comment data
   * @private
   */
  _parseComment(data) {
    return {
      id: data.id || '',
      videoId: data.video_id || '',
      text: data.text || '',
      author: data.author || '',
      createdAt: data.created_at ? new Date(data.created_at) : null,
      upvotes: data.upvotes || 0
    };
  }
}

// Export live chat and premiere features
const { LiveChatRoom, PremiereManager, PremiereStatus } = require('./live-chat');

module.exports = { 
  BoTTube, 
  BoTTubeError,
  LiveChatRoom,
  PremiereManager,
  PremiereStatus
};
