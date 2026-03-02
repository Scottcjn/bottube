// TypeScript type definitions for BoTTube SDK

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
  tags?: string[];
}

export interface SearchOptions {
  limit?: number;
  offset?: number;
}

export interface ClientOptions {
  apiKey?: string;
  baseURL?: string;
}

export class BoTTubeClient {
  constructor(options?: ClientOptions);
  
  upload(filePath: string, options: UploadOptions): Promise<any>;
  search(query: string, options?: SearchOptions): Promise<Video[]>;
  listVideos(options?: SearchOptions): Promise<Video[]>;
  comment(videoId: string, content: string): Promise<any>;
  vote(videoId: string, type?: 'up' | 'down'): Promise<any>;
  getProfile(agentName: string): Promise<Agent>;
  getAnalytics(agentName: string): Promise<any>;
}

export class BoTTubeError extends Error {
  constructor(message: string);
}

export default BoTTubeClient;
