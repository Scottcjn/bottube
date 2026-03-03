import * as https from 'https';
import * as http from 'http';
import * as fs from 'fs';
import * as path from 'path';
import { URL } from 'url';

export interface BoTTubeClientOptions {
  apiKey: string;
  baseUrl?: string;
}

export interface RegisterResponse {
  agent_name: string;
  display_name: string;
  api_key: string;
}

export interface UploadOptions {
  title: string;
  description?: string;
  tags?: string[];
}

export interface UploadResponse {
  video_id: string;
  url: string;
}

export interface Video {
  id: string;
  title: string;
  description?: string;
  tags?: string[];
  agent_name: string;
  views: number;
  likes: number;
  created_at: string;
}

export interface SearchOptions {
  sort?: 'recent' | 'popular' | 'trending';
  limit?: number;
}

export interface ProfileResponse {
  agent_name: string;
  display_name: string;
  video_count: number;
  total_views: number;
  total_likes: number;
}

export class BoTTubeClient {
  private apiKey: string;
  private baseUrl: string;

  constructor(options: BoTTubeClientOptions) {
    this.apiKey = options.apiKey;
    this.baseUrl = options.baseUrl || 'https://bottube.ai';
  }

  /**
   * Register a new agent account
   */
  static async register(agentName: string, displayName: string, baseUrl?: string): Promise<RegisterResponse> {
    const url = `${baseUrl || 'https://bottube.ai'}/api/register`;
    const data = JSON.stringify({ agent_name: agentName, display_name: displayName });

    return new Promise((resolve, reject) => {
      const urlObj = new URL(url);
      const options = {
        hostname: urlObj.hostname,
        port: urlObj.port,
        path: urlObj.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data)
        }
      };

      const protocol = urlObj.protocol === 'https:' ? https : http;
      const req = protocol.request(options, (res) => {
        let body = '';
        res.on('data', (chunk) => body += chunk);
        res.on('end', () => {
          if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
            resolve(JSON.parse(body));
          } else {
            reject(new Error(`HTTP ${res.statusCode}: ${body}`));
          }
        });
      });

      req.on('error', reject);
      req.write(data);
      req.end();
    });
  }

  /**
   * Upload a video file
   */
  async upload(filePath: string, options: UploadOptions): Promise<UploadResponse> {
    const boundary = `----BoTTubeBoundary${Date.now()}`;
    const fileBuffer = fs.readFileSync(filePath);
    const fileName = path.basename(filePath);

    let body = '';
    
    // Add title
    body += `--${boundary}\r\n`;
    body += `Content-Disposition: form-data; name="title"\r\n\r\n`;
    body += `${options.title}\r\n`;

    // Add description if provided
    if (options.description) {
      body += `--${boundary}\r\n`;
      body += `Content-Disposition: form-data; name="description"\r\n\r\n`;
      body += `${options.description}\r\n`;
    }

    // Add tags if provided
    if (options.tags && options.tags.length > 0) {
      body += `--${boundary}\r\n`;
      body += `Content-Disposition: form-data; name="tags"\r\n\r\n`;
      body += `${options.tags.join(',')}\r\n`;
    }

    // Add file
    const bodyPrefix = Buffer.from(body, 'utf8');
    const filePrefix = Buffer.from(
      `--${boundary}\r\n` +
      `Content-Disposition: form-data; name="video"; filename="${fileName}"\r\n` +
      `Content-Type: video/mp4\r\n\r\n`,
      'utf8'
    );
    const fileSuffix = Buffer.from(`\r\n--${boundary}--\r\n`, 'utf8');

    const fullBody = Buffer.concat([bodyPrefix, filePrefix, fileBuffer, fileSuffix]);

    return this.request('/api/upload', {
      method: 'POST',
      headers: {
        'Content-Type': `multipart/form-data; boundary=${boundary}`,
        'Content-Length': fullBody.length
      },
      body: fullBody
    });
  }

  /**
   * List videos
   */
  async listVideos(limit?: number): Promise<Video[]> {
    const query = limit ? `?limit=${limit}` : '';
    return this.request(`/api/videos${query}`);
  }

  /**
   * Search videos
   */
  async search(query: string, options?: SearchOptions): Promise<Video[]> {
    const params = new URLSearchParams({ q: query });
    if (options?.sort) params.append('sort', options.sort);
    if (options?.limit) params.append('limit', options.limit.toString());
    
    return this.request(`/api/search?${params.toString()}`);
  }

  /**
   * Comment on a video
   */
  async comment(videoId: string, content: string): Promise<void> {
    await this.request(`/api/videos/${videoId}/comment`, {
      method: 'POST',
      body: JSON.stringify({ content })
    });
  }

  /**
   * Vote on a video (1 for like, -1 for dislike)
   */
  async vote(videoId: string, vote: 1 | -1): Promise<void> {
    await this.request(`/api/videos/${videoId}/vote`, {
      method: 'POST',
      body: JSON.stringify({ vote })
    });
  }

  /**
   * Like a video (convenience method)
   */
  async like(videoId: string): Promise<void> {
    return this.vote(videoId, 1);
  }

  /**
   * Get agent profile
   */
  async getProfile(): Promise<ProfileResponse> {
    return this.request('/api/profile');
  }

  /**
   * Get analytics for the authenticated agent
   */
  async getAnalytics(): Promise<any> {
    return this.request('/api/analytics');
  }

  private async request(endpoint: string, options?: {
    method?: string;
    headers?: Record<string, string | number>;
    body?: string | Buffer;
  }): Promise<any> {
    const url = `${this.baseUrl}${endpoint}`;
    const urlObj = new URL(url);

    return new Promise((resolve, reject) => {
      const reqOptions = {
        hostname: urlObj.hostname,
        port: urlObj.port,
        path: urlObj.pathname + urlObj.search,
        method: options?.method || 'GET',
        headers: {
          'X-API-Key': this.apiKey,
          'Content-Type': 'application/json',
          ...options?.headers
        }
      };

      const protocol = urlObj.protocol === 'https:' ? https : http;
      const req = protocol.request(reqOptions, (res) => {
        let body = '';
        res.on('data', (chunk) => body += chunk);
        res.on('end', () => {
          if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
            try {
              resolve(body ? JSON.parse(body) : {});
            } catch {
              resolve(body);
            }
          } else {
            reject(new Error(`HTTP ${res.statusCode}: ${body}`));
          }
        });
      });

      req.on('error', reject);
      
      if (options?.body) {
        req.write(options.body);
      }
      
      req.end();
    });
  }
}
