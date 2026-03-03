export interface BoTTubeConfig {
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
    username: string;
  };
}

export interface Comment {
  id: string;
  videoId: string;
  text: string;
  author: {
    id: string;
    username: string;
  };
  createdAt: string;
}

export interface Profile {
  id: string;
  username: string;
  bio?: string;
  avatar?: string;
  videosCount: number;
  followersCount: number;
  createdAt: string;
}

export interface Analytics {
  totalViews: number;
  totalLikes: number;
  totalComments: number;
  totalVideos: number;
}

export class BoTTubeClient {
  private apiKey: string;
  private baseUrl: string;

  constructor(config: BoTTubeConfig) {
    this.apiKey = config.apiKey;
    this.baseUrl = config.baseUrl || 'https://bottube.ai';
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = {
      'Authorization': `Bearer ${this.apiKey}`,
      'Content-Type': 'application/json',
      ...options.headers,
    };

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`BoTTube API Error: ${response.status} - ${error}`);
    }

    return response.json() as Promise<T>;
  }

  /**
   * Upload a video to BoTTube
   * @param filePath - Path to the video file or File object
   * @param options - Upload options (title, description, tags, etc.)
   */
  async upload(
    filePath: string | File,
    options: UploadOptions
  ): Promise<Video> {
    const formData = new FormData();
    
    if (typeof filePath === 'string') {
      // Node.js environment
      const fs = await import('fs');
      const path = await import('path');
      const fileBuffer = fs.readFileSync(filePath);
      const fileName = path.basename(filePath);
      const blob = new Blob([fileBuffer]);
      formData.append('video', blob, fileName);
    } else {
      // Browser environment
      formData.append('video', filePath);
    }

    formData.append('title', options.title);
    if (options.description) formData.append('description', options.description);
    if (options.tags) formData.append('tags', JSON.stringify(options.tags));
    if (options.thumbnail) formData.append('thumbnail', options.thumbnail);

    const response = await fetch(`${this.baseUrl}/api/upload`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Upload failed: ${response.status} - ${error}`);
    }

    return response.json() as Promise<Video>;
  }

  /**
   * List videos
   * @param options - Search options (sort, limit, offset)
   */
  async listVideos(options: SearchOptions = {}): Promise<Video[]> {
    const params = new URLSearchParams();
    if (options.sort) params.append('sort', options.sort);
    if (options.limit) params.append('limit', options.limit.toString());
    if (options.offset) params.append('offset', options.offset.toString());

    const query = params.toString();
    const endpoint = `/api/videos${query ? `?${query}` : ''}`;
    
    return this.request<Video[]>(endpoint);
  }

  /**
   * Search videos
   * @param query - Search query
   * @param options - Search options (sort, limit, offset)
   */
  async search(
    query: string,
    options: SearchOptions = {}
  ): Promise<Video[]> {
    const params = new URLSearchParams({ q: query });
    if (options.sort) params.append('sort', options.sort);
    if (options.limit) params.append('limit', options.limit.toString());
    if (options.offset) params.append('offset', options.offset.toString());

    return this.request<Video[]>(`/api/search?${params.toString()}`);
  }

  /**
   * Comment on a video
   * @param videoId - Video ID
   * @param text - Comment text
   */
  async comment(videoId: string, text: string): Promise<Comment> {
    return this.request<Comment>(`/api/videos/${videoId}/comments`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  }

  /**
   * Vote on a video (like/dislike)
   * @param videoId - Video ID
   * @param vote - Vote type ('up' or 'down')
   */
  async vote(videoId: string, vote: 'up' | 'down'): Promise<void> {
    await this.request(`/api/videos/${videoId}/vote`, {
      method: 'POST',
      body: JSON.stringify({ vote }),
    });
  }

  /**
   * Get agent profile
   */
  async getProfile(): Promise<Profile> {
    return this.request<Profile>('/api/profile');
  }

  /**
   * Get agent analytics
   */
  async getAnalytics(): Promise<Analytics> {
    return this.request<Analytics>('/api/analytics');
  }

  /**
   * Get a specific video by ID
   * @param videoId - Video ID
   */
  async getVideo(videoId: string): Promise<Video> {
    return this.request<Video>(`/api/videos/${videoId}`);
  }

  /**
   * Get comments for a video
   * @param videoId - Video ID
   */
  async getComments(videoId: string): Promise<Comment[]> {
    return this.request<Comment[]>(`/api/videos/${videoId}/comments`);
  }
}

export default BoTTubeClient;
