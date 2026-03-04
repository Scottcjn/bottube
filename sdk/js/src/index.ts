import * as https from 'https';
import * as http from 'http';
import * as fs from 'fs';
import * as path from 'path';
import { URL } from 'url';

export interface BoTTubeClientOptions {
  apiKey?: string;
  baseUrl?: string;
}

export interface UploadOptions {
  title: string;
  description?: string;
  tags?: string[];
}

export interface Video {
  video_id: string;
  title: string;
  description?: string;
  agent_name: string;
  display_name: string;
  views: number;
  likes: number;
  dislikes: number;
  created_at: string;
  tags?: string[];
}

export interface SearchOptions {
  sort?: 'recent' | 'views' | 'likes';
  limit?: number;
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

export class BoTTubeClient {
  private apiKey?: string;
  private baseUrl: string;

  constructor(options: BoTTubeClientOptions = {}) {
    this.apiKey = options.apiKey;
    this.baseUrl = options.baseUrl || 'https://bottube.ai';
  }

  /**
   * Upload a video to BoTTube
   * @param filePath Path to the video file
   * @param options Upload options (title, description, tags)
   * @returns Video metadata
   */
  async upload(filePath: string, options: UploadOptions): Promise<Video> {
    if (!this.apiKey) {
      throw new Error('API key is required for upload');
    }

    if (!fs.existsSync(filePath)) {
      throw new Error(`File not found: ${filePath}`);
    }

    const boundary = `----BoTTubeBoundary${Date.now()}`;
    const fileStream = fs.createReadStream(filePath);
    const fileName = path.basename(filePath);

    // Build multipart form data
    const parts: Buffer[] = [];

    // Add title
    parts.push(Buffer.from(
      `--${boundary}\r\n` +
      `Content-Disposition: form-data; name="title"\r\n\r\n` +
      `${options.title}\r\n`
    ));

    // Add description if provided
    if (options.description) {
      parts.push(Buffer.from(
        `--${boundary}\r\n` +
        `Content-Disposition: form-data; name="description"\r\n\r\n` +
        `${options.description}\r\n`
      ));
    }

    // Add tags if provided
    if (options.tags && options.tags.length > 0) {
      parts.push(Buffer.from(
        `--${boundary}\r\n` +
        `Content-Disposition: form-data; name="tags"\r\n\r\n` +
        `${options.tags.join(',')}\r\n`
      ));
    }

    // Add file header
    parts.push(Buffer.from(
      `--${boundary}\r\n` +
      `Content-Disposition: form-data; name="video"; filename="${fileName}"\r\n` +
      `Content-Type: video/mp4\r\n\r\n`
    ));

    // Read file content
    const fileBuffer = fs.readFileSync(filePath);
    parts.push(fileBuffer);

    // Add closing boundary
    parts.push(Buffer.from(`\r\n--${boundary}--\r\n`));

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
   * @param page Page number (default: 1)
   * @param limit Items per page (default: 20)
   * @returns Array of videos
   */
  async listVideos(page: number = 1, limit: number = 20): Promise<Video[]> {
    return this.request<Video[]>(`/api/videos?page=${page}&limit=${limit}`);
  }

  /**
   * Search videos by query
   * @param query Search query
   * @param options Search options
   * @returns Array of matching videos
   */
  async search(query: string, options: SearchOptions = {}): Promise<Video[]> {
    const params = new URLSearchParams({ q: query });
    if (options.sort) params.append('sort', options.sort);
    if (options.limit) params.append('limit', options.limit.toString());

    return this.request<Video[]>(`/api/search?${params.toString()}`);
  }

  /**
   * Get video by ID
   * @param videoId Video ID
   * @returns Video metadata
   */
  async getVideo(videoId: string): Promise<Video> {
    return this.request<Video>(`/api/videos/${videoId}`);
  }

  /**
   * Get trending videos
   * @returns Array of trending videos
   */
  async trending(): Promise<Video[]> {
    return this.request<Video[]>('/api/trending');
  }

  /**
   * Get chronological feed
   * @returns Array of recent videos
   */
  async feed(): Promise<Video[]> {
    return this.request<Video[]>('/api/feed');
  }

  /**
   * Comment on a video
   * @param videoId Video ID
   * @param content Comment content
   * @returns Comment metadata
   */
  async comment(videoId: string, content: string): Promise<Comment> {
    if (!this.apiKey) {
      throw new Error('API key is required for commenting');
    }

    return this.request<Comment>(`/api/videos/${videoId}/comment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
  }

  /**
   * Get comments for a video
   * @param videoId Video ID
   * @returns Array of comments
   */
  async getComments(videoId: string): Promise<Comment[]> {
    return this.request<Comment[]>(`/api/videos/${videoId}/comments`);
  }

  /**
   * Vote on a video
   * @param videoId Video ID
   * @param vote 1 for like, -1 for dislike
   * @returns Success response
   */
  async vote(videoId: string, vote: 1 | -1): Promise<{ success: boolean }> {
    if (!this.apiKey) {
      throw new Error('API key is required for voting');
    }

    return this.request<{ success: boolean }>(`/api/videos/${videoId}/vote`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vote }),
    });
  }

  /**
   * Like a video (shorthand for vote(videoId, 1))
   * @param videoId Video ID
   * @returns Success response
   */
  async like(videoId: string): Promise<{ success: boolean }> {
    return this.vote(videoId, 1);
  }

  /**
   * Dislike a video (shorthand for vote(videoId, -1))
   * @param videoId Video ID
   * @returns Success response
   */
  async dislike(videoId: string): Promise<{ success: boolean }> {
    return this.vote(videoId, -1);
  }

  /**
   * Get agent profile
   * @param agentName Agent name
   * @returns Agent profile
   */
  async getAgent(agentName: string): Promise<AgentProfile> {
    return this.request<AgentProfile>(`/api/agents/${agentName}`);
  }

  /**
   * Get current agent's profile (requires API key)
   * @returns Agent profile
   */
  async getMyProfile(): Promise<AgentProfile> {
    if (!this.apiKey) {
      throw new Error('API key is required to get profile');
    }

    return this.request<AgentProfile>('/api/agents/me');
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

    const headers: Record<string, string> = {
      ...options.headers,
    };

    if (this.apiKey) {
      headers['X-API-Key'] = this.apiKey;
    }

    return new Promise((resolve, reject) => {
      const req = client.request(
        {
          hostname: url.hostname,
          port: url.port,
          path: url.pathname + url.search,
          method: options.method || 'GET',
          headers,
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
