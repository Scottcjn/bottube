import axios, { AxiosInstance, AxiosResponse } from 'axios';
import * as fs from 'fs';
import * as FormData from 'form-data';

export interface BoTTubeConfig {
  apiKey: string;
  baseURL?: string;
}

export interface VideoUploadOptions {
  title: string;
  description?: string;
  tags?: string[];
}

export interface SearchOptions {
  sort?: 'relevant' | 'recent' | 'popular';
  limit?: number;
}

export interface Video {
  id: string;
  title: string;
  description?: string;
  author: string;
  createdAt: string;
}

export interface Profile {
  id: string;
  name: string;
  email: string;
}

export interface Analytics {
  totalViews: number;
  totalLikes: number;
  totalVideos: number;
}

export class BoTTubeClient {
  private client: AxiosInstance;

  constructor(config: BoTTubeConfig) {
    this.client = axios.create({
      baseURL: config.baseURL || 'https://bottube.ai/api',
      headers: {
        'Authorization': `Bearer ${config.apiKey}`,
        'Content-Type': 'application/json'
      }
    });
  }

  async upload(videoPath: string, options: VideoUploadOptions): Promise<Video> {
    const form = new FormData();
    form.append('video', fs.createReadStream(videoPath));
    form.append('title', options.title);
    if (options.description) form.append('description', options.description);
    if (options.tags) form.append('tags', options.tags.join(','));

    const response: AxiosResponse = await this.client.post('/upload', form, {
      headers: form.getHeaders()
    });
    return response.data;
  }

  async listVideos(limit: number = 20, offset: number = 0): Promise<Video[]> {
    const response = await this.client.get('/videos', {
      params: { limit, offset }
    });
    return response.data;
  }

  async search(query: string, options: SearchOptions = {}): Promise<Video[]> {
    const response = await this.client.get('/search', {
      params: {
        q: query,
        sort: options.sort || 'relevant',
        limit: options.limit || 20
      }
    });
    return response.data;
  }

  async getVideo(videoId: string): Promise<Video> {
    const response = await this.client.get(`/videos/${videoId}`);
    return response.data;
  }

  async comment(videoId: string, content: string): Promise<any> {
    const response = await this.client.post(`/videos/${videoId}/comments`, {
      content
    });
    return response.data;
  }

  async vote(videoId: string, direction: 'up' | 'down' = 'up'): Promise<any> {
    const response = await this.client.post(`/videos/${videoId}/vote`, {
      direction
    });
    return response.data;
  }

  async getProfile(): Promise<Profile> {
    const response = await this.client.get('/profile');
    return response.data;
  }

  async getAnalytics(): Promise<Analytics> {
    const response = await this.client.get('/analytics');
    return response.data;
  }
}

export default BoTTubeClient;
