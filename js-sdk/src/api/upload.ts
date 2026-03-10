import type { HttpClient } from '../client';
import type { Video, UploadRequest } from '../types';

/**
 * Upload API client
 * Handles video upload operations
 */
export class UploadApi {
  private client: HttpClient;

  constructor(client: HttpClient) {
    this.client = client;
  }

  /**
   * Upload a video
   * 
   * Note: This method requires FormData support. In Node.js environments,
   * you may need to use a FormData polyfill like 'formdata-node'.
   */
  async upload(data: UploadRequest): Promise<Video> {
    const formData = new FormData();

    formData.append('title', data.title);

    if (data.description) {
      formData.append('description', data.description);
    }

    if (data.tags && data.tags.length > 0) {
      formData.append('tags', data.tags.join(','));
    }

    if (data.category) {
      formData.append('category', data.category);
    }

    formData.append('video', data.video);

    return this.client.upload('/api/upload', formData);
  }
}
