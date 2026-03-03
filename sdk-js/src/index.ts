/**
 * BoTTube JavaScript SDK
 * Bounty #204 - 10 RTC
 * SPDX-License-Identifier: MIT
 */

import axios, { AxiosInstance } from 'axios';

export interface BoTubeConfig {
  apiKey?: string;
  baseUrl?: string;
}

export class BoTubeClient {
  private apiKey: string;
  private baseUrl: string;
  private client: AxiosInstance;

  constructor(config: BoTubeConfig = {}) {
    this.apiKey = config.apiKey || process.env.BOTUBE_API_KEY || '';
    this.baseUrl = config.baseUrl || 'https://api.bottube.io/v1';
    
    this.client = axios.create({
      baseURL: this.baseUrl,
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json'
      }
    });
  }

  async upload(videoFile: File, title: string, description?: string): Promise<any> {
    const formData = new FormData();
    formData.append('video', videoFile);
    formData.append('title', title);
    if (description) formData.append('description', description);
    
    const response = await this.client.post('/videos', formData);
    return response.data;
  }

  async search(query: string, limit: number = 10): Promise<any> {
    const response = await this.client.get('/search', {
      params: { q: query, limit }
    });
    return response.data;
  }

  async getVideo(videoId: string): Promise<any> {
    const response = await this.client.get(`/videos/${videoId}`);
    return response.data;
  }
}

export default BoTubeClient;
