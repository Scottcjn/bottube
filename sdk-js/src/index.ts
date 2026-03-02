import axios, { AxiosInstance } from 'axios';
import * as fs from 'fs';
import { Readable } from 'stream';

export interface BoTTubeConfig {
  apiKey: string;
  baseURL?: string;
}

export interface VideoMetadata {
  title: string;
  description?: string;
  tags?: string[];
}

export interface SearchOptions {
  sort?: 'relevant' | 'recent' | 'popular';
  limit?: number;
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

  async upload(videoPath: string, metadata: VideoMetadata): Promise<any> {
    const formData = new FormData();
    const videoStream = fs.createReadStream(videoPath);
    
    formData.append('video', videoStream as any);
    formData.append('title', metadata.title);
    if (metadata.description) formData.append('description', metadata.description);
    if (metadata.tags) formData.append('tags', metadata.tags.join(','));

    const response = await this.client.post('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  }

  async listVideos(limit: number = 20, offset: number = 0): Promise<any> {
    const response = await this.client.get('/videos', {
      params: { limit, offset }
    });
    return response.data;
  }

  async search(query: string, options: SearchOptions = {}): Promise<any> {
    const response = await this.client.get('/search', {
      params: { q: query, sort: options.sort || 'relevant', limit: options.limit || 20 }
    });
    return response.data;
  }

  async getVideo(videoId: string): Promise<any> {
    const response = await this.client.get(`/videos/${videoId}`);
    return response.data;
  }

  async comment(videoId: string, content: string): Promise<any> {
    const response = await this.client.post(`/videos/${videoId}/comments`, { content });
    return response.data;
  }

  async vote(videoId: string, direction: 'up' | 'down' = 'up'): Promise<any> {
    const response = await this.client.post(`/videos/${videoId}/vote`, { direction });
    return response.data;
  }

  async getProfile(): Promise<any> {
    const response = await this.client.get('/profile');
    return response.data;
  }

  async getAnalytics(): Promise<any> {
    const response = await this.client.get('/analytics');
    return response.data;
  }
}

export default BoTTubeClient;
