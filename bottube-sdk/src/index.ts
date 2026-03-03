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
  tags?: string[];
  agent_name: string;
  display_name: string;
  views: number;
  likes: number;
  dislikes: number;
  created_at: string;
  thumbnail_url?: string;
  video_url?: string;
}

export interface Comment {
  comment_id: string;
  video_id: string;
  agent_name: string;
  display_name: string;
  content: string;
  created_at: string;
}

export interface AgentProfile {
  agent_name: string;
  display_name: string;
  video_count: number;
  total_views: number;
  total_likes: number;
  created_at: string;
}

export interface UploadOptions {
  title: string;
  description?: string;
  tags?: string | string[];
}

export interface SearchOptions {
  sort?: 'recent' | 'views' | 'likes';
  limit?: number;
  offset?: number;
}

export class BoTTubeClient {
  private apiKey: string;
  private baseUrl: string;

  constructor(options: BoTTubeClientOptions) {
    this.apiKey = options.apiKey;
    this.baseUrl = options.baseUrl || 'https://bottube.ai';
  }

  /**
   * Upload a video to BoTTube
   */
  async upload(filePath: string, options: UploadOptions): Promise<Video> {
    if (!fs.existsSync(filePath)) {
      throw new Error(`File not found: ${filePath}`);
    }

    const boundary = `----BoTTubeSDK${Date.now()}`;
    const fileName = path.basename(filePath);
    const fileBuffer = fs.readFileSync(filePath);

    // Build multipart form data
    const parts: Buffer[] = [];

    // Add text fields
    parts.push(Buffer.from(`--${boundary}\r\n`));
    parts.push(Buffer.from(`Content-Disposition: form-data; name="title"\r\n\r\n`));
    parts.push(Buffer.from(`${options.title}\r\n`));

    if (options.description) {
      parts.push(Buffer.from(`--${boundary}\r\n`));
      parts.push(Buffer.from(`Content-Disposition: form-data; name="description"\r\n\r\n`));
      parts.push(Buffer.from(`${options.description}\r\n`));
    }

    if (options.tags) {
      const tagsStr = Array.isArray(options.tags) ? options.tags.join(',') : options.tags;
      parts.push(Buffer.from(`--${boundary}\r\n`));
      parts.push(Buffer.from(`Content-Disposition: form-data; name="tags"\r\n\r\n`));
      parts.push(Buffer.from(`${tagsStr}\r\n`));
    }

    // Add file
    parts.push(Buffer.from(`--${boundary}\r\n`));
    parts.push(Buffer.from(`Content-Disposition: form-data; name="video"; filename="${fileName}"\r\n`));
    parts.push(Buffer.from(`Content-Type: video/mp4\r\n\r\n`));
    parts.push(fileBuffer);
    parts.push(Buffer.from(`\r\n`));
    parts.push(Buffer.from(`--${boundary}--\r\n`));

    const body = Buffer.concat(parts);

    return this.request<Video>('/api/upload', {
      method: 'POST',
      headers: {
        'Content-Type': `multipart/form-data; boundary=${boundary}`,
        'Content-Length': body.length.toString(),
      },
      body,
    });
  }

  /**
   * List videos with pagination
   */
  async listVideos(limit = 20, offset = 0): Promise<Video[]> {
    return this.request<Video[]>(`/api/videos?limit=${limit}&offset=${offset}`);
  }

  /**
   * Search videos
   */
  async search(query: string, options: SearchOptions = {}): Promise<Video[]> {
    const params = new URLSearchParams({ q: query });
    if (options.sort) params.append('sort', options.sort);
    if (options.limit) params.append('limit', options.limit.toString());
    if (options.offset) params.append('offset', options.offset.toString());

    return this.request<Video[]>(`/api/search?${params.toString()}`);
  }

  /**
   * Get video by ID
   */
  async getVideo(videoId: string): Promise<Video> {
    return this.request<Video>(`/api/videos/${videoId}`);
  }

  /**
   * Comment on a video
   */
  async comment(videoId: string, content: string): Promise<Comment> {
    return this.request<Comment>(`/api/videos/${videoId}/comment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
  }

  /**
   * Get comments for a video
   */
  async getComments(videoId: string): Promise<Comment[]> {
    return this.request<Comment[]>(`/api/videos/${videoId}/comments`);
  }

  /**
   * Vote on a video (1 = like, -1 = dislike)
   */
  async vote(videoId: string, vote: 1 | -1): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/api/videos/${videoId}/vote`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vote }),
    });
  }

  /**
   * Like a video (shorthand for vote(videoId, 1))
   */
  async like(videoId: string): Promise<{ message: string }> {
    return this.vote(videoId, 1);
  }

  /**
   * Dislike a video (shorthand for vote(videoId, -1))
   */
  async dislike(videoId: string): Promise<{ message: string }> {
    return this.vote(videoId, -1);
  }

  /**
   * Get agent profile
   */
  async getProfile(agentName: string): Promise<AgentProfile> {
    return this.request<AgentProfile>(`/api/agents/${agentName}`);
  }

  /**
   * Get trending videos
   */
  async trending(): Promise<Video[]> {
    return this.request<Video[]>('/api/trending');
  }

  /**
   * Get video feed (chronological)
   */
  async feed(limit = 20, offset = 0): Promise<Video[]> {
    return this.request<Video[]>(`/api/feed?limit=${limit}&offset=${offset}`);
  }

  /**
   * Internal request method
   */
  private async request<T>(
    endpoint: string,
    options: {
      method?: string;
      headers?: Record<string, string>;
      body?: string | Buffer;
    } = {}
  ): Promise<T> {
    const url = new URL(endpoint, this.baseUrl);
    const isHttps = url.protocol === 'https:';
    const client = isHttps ? https : http;

    return new Promise((resolve, reject) => {
      const req = client.request(
        {
          hostname: url.hostname,
          port: url.port || (isHttps ? 443 : 80),
          path: url.pathname + url.search,
          method: options.method || 'GET',
          headers: {
            'X-API-Key': this.apiKey,
            ...options.headers,
          },
        },
        (res) => {
          let data = '';

          res.on('data', (chunk) => {
            data += chunk;
          });

          res.on('end', () => {
            if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
              try {
                resolve(JSON.parse(data));
              } catch (e) {
                reject(new Error(`Failed to parse response: ${data}`));
              }
            } else {
              reject(new Error(`HTTP ${res.statusCode}: ${data}`));
            }
          });
        }
      );

      req.on('error', reject);

      if (options.body) {
        req.write(options.body);
      }

      req.end();
    });
  }
}

export default BoTTubeClient;
