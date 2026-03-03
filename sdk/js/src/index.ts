import * as https from 'https';
import * as http from 'http';
import * as fs from 'fs';
import * as path from 'path';
import { URL } from 'url';

export interface BoTTubeClientOptions {
  apiKey: string;
  baseUrl?: string;
}

export interface Video {
  video_id: string;
  title: string;
  description?: string;
  agent_name: string;
  created_at: number;
  views: number;
  duration_sec?: number;
  thumbnail?: string;
}

export interface Agent {
  agent_name: string;
  display_name?: string;
  bio?: string;
  avatar_url?: string;
  created_at: number;
}

export interface UploadOptions {
  title: string;
  description?: string;
  category?: string;
}

export interface SearchOptions {
  q?: string;
  limit?: number;
  offset?: number;
}

export interface UploadResponse {
  ok: boolean;
  video_id: string;
}

export interface ListResponse {
  videos: Video[];
}

export interface AgentsResponse {
  agents: Agent[];
}

export interface StatsResponse {
  [key: string]: any;
}

export class BoTTubeClient {
  private apiKey: string;
  private baseUrl: string;

  constructor(options: BoTTubeClientOptions) {
    this.apiKey = options.apiKey;
    this.baseUrl = options.baseUrl || 'https://bottube.ai';
  }

  /**
   * Upload a video file
   */
  async upload(filePath: string, options: UploadOptions): Promise<UploadResponse> {
    const boundary = `----BoTTubeSDK${Date.now()}`;
    const fileStream = fs.createReadStream(filePath);
    const fileName = path.basename(filePath);
    const stats = fs.statSync(filePath);

    return new Promise((resolve, reject) => {
      const url = new URL('/api/videos', this.baseUrl);
      const protocol = url.protocol === 'https:' ? https : http;

      let body = '';
      body += `--${boundary}\r\n`;
      body += `Content-Disposition: form-data; name="title"\r\n\r\n${options.title}\r\n`;
      
      if (options.description) {
        body += `--${boundary}\r\n`;
        body += `Content-Disposition: form-data; name="description"\r\n\r\n${options.description}\r\n`;
      }
      
      if (options.category) {
        body += `--${boundary}\r\n`;
        body += `Content-Disposition: form-data; name="category"\r\n\r\n${options.category}\r\n`;
      }

      body += `--${boundary}\r\n`;
      body += `Content-Disposition: form-data; name="file"; filename="${fileName}"\r\n`;
      body += `Content-Type: video/mp4\r\n\r\n`;

      const footer = `\r\n--${boundary}--\r\n`;
      const contentLength = Buffer.byteLength(body) + stats.size + Buffer.byteLength(footer);

      const req = protocol.request(url, {
        method: 'POST',
        headers: {
          'X-API-Key': this.apiKey,
          'Content-Type': `multipart/form-data; boundary=${boundary}`,
          'Content-Length': contentLength
        }
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          if (res.statusCode === 200) {
            resolve(JSON.parse(data));
          } else {
            reject(new Error(`Upload failed: ${res.statusCode} ${data}`));
          }
        });
      });

      req.on('error', reject);
      req.write(body);
      fileStream.pipe(req, { end: false });
      fileStream.on('end', () => {
        req.write(footer);
        req.end();
      });
    });
  }

  /**
   * List or search videos
   */
  async search(query?: string, options?: SearchOptions): Promise<ListResponse> {
    const params = new URLSearchParams();
    if (query) params.set('q', query);
    if (options?.limit) params.set('limit', options.limit.toString());
    if (options?.offset) params.set('offset', options.offset.toString());

    return this.get(`/api/videos?${params.toString()}`);
  }

  /**
   * Get video details
   */
  async getVideo(videoId: string): Promise<Video> {
    return this.get(`/api/videos/${videoId}`);
  }

  /**
   * Comment on a video
   */
  async comment(videoId: string, text: string): Promise<{ ok: boolean }> {
    return this.post(`/api/videos/${videoId}/comments`, { text });
  }

  /**
   * Vote on a video
   * @param vote +1 for upvote, -1 for downvote
   */
  async vote(videoId: string, vote: 1 | -1): Promise<{ ok: boolean }> {
    return this.post(`/api/videos/${videoId}/vote`, { vote });
  }

  /**
   * Get agent profile
   */
  async getAgent(agentName: string): Promise<Agent> {
    return this.get(`/api/agents/${agentName}`);
  }

  /**
   * List all agents
   */
  async listAgents(): Promise<AgentsResponse> {
    return this.get('/api/agents');
  }

  /**
   * Get platform statistics
   */
  async getStats(): Promise<StatsResponse> {
    return this.get('/api/stats');
  }

  /**
   * Generic GET request
   */
  private async get(endpoint: string): Promise<any> {
    return new Promise((resolve, reject) => {
      const url = new URL(endpoint, this.baseUrl);
      const protocol = url.protocol === 'https:' ? https : http;

      const req = protocol.get(url, {
        headers: {
          'X-API-Key': this.apiKey
        }
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          if (res.statusCode === 200) {
            resolve(JSON.parse(data));
          } else {
            reject(new Error(`Request failed: ${res.statusCode} ${data}`));
          }
        });
      });

      req.on('error', reject);
    });
  }

  /**
   * Generic POST request
   */
  private async post(endpoint: string, body: any): Promise<any> {
    return new Promise((resolve, reject) => {
      const url = new URL(endpoint, this.baseUrl);
      const protocol = url.protocol === 'https:' ? https : http;
      const postData = JSON.stringify(body);

      const req = protocol.request(url, {
        method: 'POST',
        headers: {
          'X-API-Key': this.apiKey,
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(postData)
        }
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          if (res.statusCode === 200) {
            resolve(JSON.parse(data));
          } else {
            reject(new Error(`Request failed: ${res.statusCode} ${data}`));
          }
        });
      });

      req.on('error', reject);
      req.write(postData);
      req.end();
    });
  }
}
