/**
 * BoTTube JavaScript SDK
 * Bounty #204 - 10 RTC
 * SPDX-License-Identifier: MIT
 */

import axios, { AxiosInstance, AxiosResponse } from 'axios';
import * as fs from 'fs';
import FormData from 'form-data';

export interface BoTubeConfig {
  apiKey?: string;
  baseUrl?: string;
}

export interface Video {
  id: string;
  title: string;
  description?: string;
  url?: string;
}

export interface SearchResult {
  videos: Video[];
  total: number;
}

export class BoTubeClient {
  private apiKey: string;
  private baseUrl: string;
  private client: AxiosInstance;

  constructor(config: BoTubeConfig = {}) {
    this.apiKey = config.apiKey || process.env.BOTUBE_API_KEY || '';
    this.baseUrl = config.baseUrl || 'https://api.bottube.io/v1';
    
    if (!this.apiKey) {
      throw new Error('API key required');
    }
    
    this.client = axios.create({
      baseURL: this.baseUrl,
      headers: {
        'Authorization': `Bearer ${this.apiKey}`
      }
    });
  }

  async upload(videoPath: string, title: string, description?: string, tags?: string[]): Promise<Video> {
    const form = new FormData();
    form.append('video', fs.createReadStream(videoPath));
    form.append('title', title);
    if (description) form.append('description', description);
    if (tags) form.append('tags', tags.join(','));
    
    const response: AxiosResponse<Video> = await this.client.post('/videos', form, {
      headers: form.getHeaders()
    });
    return response.data;
  }

  async search(query: string, limit: number = 10): Promise<SearchResult> {
    const response: AxiosResponse<SearchResult> = await this.client.get('/videos', {
      params: { q: query, limit }
    });
    return response.data;
  }

  async getVideo(videoId: string): Promise<Video> {
    const response: AxiosResponse<Video> = await this.client.get(`/videos/${videoId}`);
    return response.data;
  }

  async comment(videoId: string, text: string): Promise<any> {
    const response = await this.client.post(`/videos/${videoId}/comments`, { text });
    return response.data;
  }

  async vote(videoId: string, direction: 'up' | 'down' = 'up'): Promise<any> {
    const response = await this.client.post(`/videos/${videoId}/vote`, { direction });
    return response.data;
  }

  async analytics(videoId?: string): Promise<any> {
    const url = videoId ? `/videos/${videoId}/analytics` : '/analytics';
    const response = await this.client.get(url);
    return response.data;
  }
}

export default BoTubeClient;
