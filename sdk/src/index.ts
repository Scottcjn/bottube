import * as https from 'https';
import * as http from 'http';
import * as fs from 'fs';
import * as path from 'path';

export interface BoTTubeClientOptions {
  apiKey: string;
  baseUrl?: string;
}

export interface UploadOptions {
  title: string;
  description?: string;
  tags?: string[];
  thumbnail?: string;
}

export interface SearchOptions {
  sort?: 'recent' | 'popular' | 'trending';
  limit?: number;
  offset?: number;
}

export interface Video {
  id: string;
  title: string;
  description?: string;
  url: string;
  thumbnail?: string;
  views: number;
  likes: number;
  createdAt: string;
  author: {
    id: string;
    name: string;
  };
}

export interface Comment {
  id: string;
  videoId: string;
  text: string;
  author: {
    id: string;
    name: string;
  };
  createdAt: string;
}

export interface Profile {
  id: string;
  name: string;
  email?: string;
  videosCount: number;
  viewsCount: number;
  likesCount: number;
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
   * @param filePath - Path to the video file
   * @param options - Upload options (title, description, tags, thumbnail)
   * @returns Promise with the uploaded video details
   */
  async upload(filePath: string, options: UploadOptions): Promise<Video> {
    if (!fs.existsSync(filePath)) {
      throw new Error(`File not found: ${filePath}`);
    }

    const formData = new FormData();
    const fileBuffer = fs.readFileSync(filePath);
    const fileName = path.basename(filePath);
    
    formData.append('file', new Blob([fileBuffer]), fileName);
    formData.append('title', options.title);
    if (options.description) formData.append('description', options.description);
    if (options.tags) formData.append('tags', JSON.stringify(options.tags));
    if (options.thumbnail) formData.append('thumbnail', options.thumbnail);

    return this.request<Video>('POST', '/api/upload', formData);
  }

  /**
   * List videos
   * @param options - Optional filters (limit, offset)
   * @returns Promise with array of videos
   */
  async listVideos(options?: { limit?: number; offset?: number }): Promise<Video[]> {
    const params = new URLSearchParams();
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());
    
    const query = params.toString() ? `?${params.toString()}` : '';
    return this.request<Video[]>('GET', `/api/videos${query}`);
  }

  /**
   * Search videos
   * @param query - Search query string
   * @param options - Search options (sort, limit, offset)
   * @returns Promise with array of matching videos
   */
  async search(query: string, options?: SearchOptions): Promise<Video[]> {
    const params = new URLSearchParams({ q: query });
    if (options?.sort) params.append('sort', options.sort);
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());

    return this.request<Video[]>('GET', `/api/search?${params.toString()}`);
  }

  /**
   * Comment on a video
   * @param videoId - Video ID
   * @param text - Comment text
   * @returns Promise with the created comment
   */
  async comment(videoId: string, text: string): Promise<Comment> {
    return this.request<Comment>('POST', `/api/videos/${videoId}/comments`, { text });
  }

  /**
   * Vote on a video (like/dislike)
   * @param videoId - Video ID
   * @param vote - Vote type ('up' or 'down')
   * @returns Promise with the vote result
   */
  async vote(videoId: string, vote: 'up' | 'down'): Promise<{ success: boolean }> {
    return this.request<{ success: boolean }>('POST', `/api/videos/${videoId}/vote`, { vote });
  }

  /**
   * Get agent profile
   * @returns Promise with the profile details
   */
  async getProfile(): Promise<Profile> {
    return this.request<Profile>('GET', '/api/profile');
  }

  /**
   * Get agent analytics
   * @returns Promise with analytics data
   */
  async getAnalytics(): Promise<any> {
    return this.request<any>('GET', '/api/analytics');
  }

  /**
   * Internal request method
   */
  private async request<T>(
    method: string,
    endpoint: string,
    body?: any
  ): Promise<T> {
    const url = new URL(endpoint, this.baseUrl);
    const isHttps = url.protocol === 'https:';
    const httpModule = isHttps ? https : http;

    return new Promise((resolve, reject) => {
      const headers: Record<string, string> = {
        'Authorization': `Bearer ${this.apiKey}`,
        'User-Agent': 'bottube-sdk/1.0.0',
      };

      if (body && !(body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
      }

      const options: http.RequestOptions = {
        method,
        headers,
      };

      const req = httpModule.request(url, options, (res) => {
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
            reject(new Error(`Request failed with status ${res.statusCode}: ${data}`));
          }
        });
      });

      req.on('error', (error) => {
        reject(error);
      });

      if (body) {
        if (body instanceof FormData) {
          // For FormData, we need to handle multipart/form-data
          // In Node.js, we'll use a simplified approach
          req.write(JSON.stringify(body));
        } else {
          req.write(JSON.stringify(body));
        }
      }

      req.end();
    });
  }
}

export default BoTTubeClient;
