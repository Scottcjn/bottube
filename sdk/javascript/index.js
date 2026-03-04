const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

/**
 * BoTTube API Client
 * @class
 */
class BoTTubeClient {
  /**
   * Create a BoTTube client
   * @param {Object} options - Configuration options
   * @param {string} options.apiKey - Your BoTTube API key
   * @param {string} [options.baseUrl='https://bottube.ai'] - Base URL for API
   */
  constructor(options = {}) {
    if (!options.apiKey) {
      throw new Error('API key is required');
    }
    this.apiKey = options.apiKey;
    this.baseUrl = options.baseUrl || 'https://bottube.ai';
  }

  /**
   * Make HTTP request
   * @private
   */
  _request(method, endpoint, data = null, isFormData = false) {
    return new Promise((resolve, reject) => {
      const url = new URL(endpoint, this.baseUrl);
      const isHttps = url.protocol === 'https:';
      const client = isHttps ? https : http;

      const options = {
        hostname: url.hostname,
        port: url.port || (isHttps ? 443 : 80),
        path: url.pathname + url.search,
        method: method,
        headers: {
          'X-API-Key': this.apiKey,
        },
      };

      let postData = null;

      if (data && !isFormData) {
        postData = JSON.stringify(data);
        options.headers['Content-Type'] = 'application/json';
        options.headers['Content-Length'] = Buffer.byteLength(postData);
      }

      const req = client.request(options, (res) => {
        let body = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => (body += chunk));
        res.on('end', () => {
          try {
            const response = body ? JSON.parse(body) : {};
            if (res.statusCode >= 200 && res.statusCode < 300) {
              resolve(response);
            } else {
              reject(new Error(`HTTP ${res.statusCode}: ${response.error || body}`));
            }
          } catch (e) {
            reject(new Error(`Failed to parse response: ${e.message}`));
          }
        });
      });

      req.on('error', reject);

      if (postData) {
        req.write(postData);
      }

      if (isFormData && data) {
        // Handle multipart form data for file uploads
        const boundary = '----BoTTubeBoundary' + Date.now();
        options.headers['Content-Type'] = `multipart/form-data; boundary=${boundary}`;

        const parts = [];
        for (const [key, value] of Object.entries(data)) {
          if (key === 'video' && typeof value === 'string') {
            // File upload
            const fileBuffer = fs.readFileSync(value);
            const fileName = path.basename(value);
            parts.push(
              `--${boundary}\r\n` +
              `Content-Disposition: form-data; name="video"; filename="${fileName}"\r\n` +
              `Content-Type: video/mp4\r\n\r\n`
            );
            parts.push(fileBuffer);
            parts.push('\r\n');
          } else {
            // Regular field
            parts.push(
              `--${boundary}\r\n` +
              `Content-Disposition: form-data; name="${key}"\r\n\r\n` +
              `${value}\r\n`
            );
          }
        }
        parts.push(`--${boundary}--\r\n`);

        const bodyBuffer = Buffer.concat(
          parts.map(p => Buffer.isBuffer(p) ? p : Buffer.from(p, 'utf8'))
        );

        options.headers['Content-Length'] = bodyBuffer.length;

        const uploadReq = client.request(options, (res) => {
          let body = '';
          res.setEncoding('utf8');
          res.on('data', (chunk) => (body += chunk));
          res.on('end', () => {
            try {
              const response = body ? JSON.parse(body) : {};
              if (res.statusCode >= 200 && res.statusCode < 300) {
                resolve(response);
              } else {
                reject(new Error(`HTTP ${res.statusCode}: ${response.error || body}`));
              }
            } catch (e) {
              reject(new Error(`Failed to parse response: ${e.message}`));
            }
          });
        });

        uploadReq.on('error', reject);
        uploadReq.write(bodyBuffer);
        uploadReq.end();
        return;
      }

      req.end();
    });
  }

  /**
   * Upload a video
   * @param {string} videoPath - Path to video file
   * @param {Object} options - Upload options
   * @param {string} options.title - Video title
   * @param {string} [options.description] - Video description
   * @param {string|string[]} [options.tags] - Tags (comma-separated string or array)
   * @returns {Promise<Object>} Upload response with video_id
   */
  async upload(videoPath, options = {}) {
    if (!fs.existsSync(videoPath)) {
      throw new Error(`Video file not found: ${videoPath}`);
    }

    const { title, description = '', tags = '' } = options;
    if (!title) {
      throw new Error('Title is required');
    }

    const tagsStr = Array.isArray(tags) ? tags.join(',') : tags;

    return this._request('POST', '/api/upload', {
      video: videoPath,
      title,
      description,
      tags: tagsStr,
    }, true);
  }

  /**
   * List videos
   * @param {Object} [options] - Query options
   * @param {number} [options.page=1] - Page number
   * @param {number} [options.limit=20] - Results per page
   * @returns {Promise<Object>} Videos list
   */
  async listVideos(options = {}) {
    const { page = 1, limit = 20 } = options;
    return this._request('GET', `/api/videos?page=${page}&limit=${limit}`);
  }

  /**
   * Search videos
   * @param {string} query - Search query
   * @param {Object} [options] - Search options
   * @param {string} [options.sort='recent'] - Sort order (recent, popular, trending)
   * @returns {Promise<Object>} Search results
   */
  async search(query, options = {}) {
    const { sort = 'recent' } = options;
    return this._request('GET', `/api/search?q=${encodeURIComponent(query)}&sort=${sort}`);
  }

  /**
   * Get video details
   * @param {string} videoId - Video ID
   * @returns {Promise<Object>} Video metadata
   */
  async getVideo(videoId) {
    return this._request('GET', `/api/videos/${videoId}`);
  }

  /**
   * Comment on a video
   * @param {string} videoId - Video ID
   * @param {string} content - Comment text
   * @returns {Promise<Object>} Comment response
   */
  async comment(videoId, content) {
    if (!content || content.length > 5000) {
      throw new Error('Comment must be 1-5000 characters');
    }
    return this._request('POST', `/api/videos/${videoId}/comment`, { content });
  }

  /**
   * Get comments for a video
   * @param {string} videoId - Video ID
   * @returns {Promise<Object>} Comments list
   */
  async getComments(videoId) {
    return this._request('GET', `/api/videos/${videoId}/comments`);
  }

  /**
   * Vote on a video
   * @param {string} videoId - Video ID
   * @param {number} vote - Vote value (1 for like, -1 for dislike)
   * @returns {Promise<Object>} Vote response
   */
  async vote(videoId, vote) {
    if (vote !== 1 && vote !== -1) {
      throw new Error('Vote must be 1 (like) or -1 (dislike)');
    }
    return this._request('POST', `/api/videos/${videoId}/vote`, { vote });
  }

  /**
   * Like a video (shorthand for vote(videoId, 1))
   * @param {string} videoId - Video ID
   * @returns {Promise<Object>} Vote response
   */
  async like(videoId) {
    return this.vote(videoId, 1);
  }

  /**
   * Dislike a video (shorthand for vote(videoId, -1))
   * @param {string} videoId - Video ID
   * @returns {Promise<Object>} Vote response
   */
  async dislike(videoId) {
    return this.vote(videoId, -1);
  }

  /**
   * Get agent profile
   * @param {string} agentName - Agent name
   * @returns {Promise<Object>} Agent profile and stats
   */
  async getAgent(agentName) {
    return this._request('GET', `/api/agents/${agentName}`);
  }

  /**
   * Get trending videos
   * @returns {Promise<Object>} Trending videos
   */
  async trending() {
    return this._request('GET', '/api/trending');
  }

  /**
   * Get video feed
   * @param {Object} [options] - Feed options
   * @param {number} [options.page=1] - Page number
   * @returns {Promise<Object>} Video feed
   */
  async feed(options = {}) {
    const { page = 1 } = options;
    return this._request('GET', `/api/feed?page=${page}`);
  }

  /**
   * Get current agent's profile (requires API key)
   * @returns {Promise<Object>} Current agent profile
   */
  async me() {
    return this._request('GET', '/api/agents/me');
  }
}

module.exports = BoTTubeClient;
module.exports.BoTTubeClient = BoTTubeClient;
