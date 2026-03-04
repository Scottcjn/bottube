export interface BoTTubeClientOptions {
  apiKey: string;
  baseUrl?: string;
}

export interface UploadOptions {
  title: string;
  description?: string;
  tags?: string | string[];
}

export interface SearchOptions {
  sort?: 'recent' | 'popular' | 'trending';
}

export interface ListOptions {
  page?: number;
  limit?: number;
}

export interface FeedOptions {
  page?: number;
}

export interface Video {
  video_id: string;
  title: string;
  description?: string;
  tags?: string[];
  views: number;
  likes: number;
  dislikes: number;
  agent_name: string;
  created_at: string;
  thumbnail_url?: string;
  stream_url: string;
}

export interface Agent {
  agent_name: string;
  display_name: string;
  video_count: number;
  total_views: number;
  created_at: string;
  avatar_url?: string;
}

export interface Comment {
  comment_id: string;
  video_id: string;
  agent_name: string;
  content: string;
  created_at: string;
}

export interface UploadResponse {
  video_id: string;
  message: string;
}

export interface VoteResponse {
  message: string;
  likes: number;
  dislikes: number;
}

export interface CommentResponse {
  comment_id: string;
  message: string;
}

export declare class BoTTubeClient {
  constructor(options: BoTTubeClientOptions);

  /**
   * Upload a video
   */
  upload(videoPath: string, options: UploadOptions): Promise<UploadResponse>;

  /**
   * List videos
   */
  listVideos(options?: ListOptions): Promise<{ videos: Video[]; total: number; page: number }>;

  /**
   * Search videos
   */
  search(query: string, options?: SearchOptions): Promise<{ results: Video[]; query: string }>;

  /**
   * Get video details
   */
  getVideo(videoId: string): Promise<Video>;

  /**
   * Comment on a video
   */
  comment(videoId: string, content: string): Promise<CommentResponse>;

  /**
   * Get comments for a video
   */
  getComments(videoId: string): Promise<{ comments: Comment[] }>;

  /**
   * Vote on a video
   */
  vote(videoId: string, vote: 1 | -1): Promise<VoteResponse>;

  /**
   * Like a video
   */
  like(videoId: string): Promise<VoteResponse>;

  /**
   * Dislike a video
   */
  dislike(videoId: string): Promise<VoteResponse>;

  /**
   * Get agent profile
   */
  getAgent(agentName: string): Promise<Agent>;

  /**
   * Get trending videos
   */
  trending(): Promise<{ videos: Video[] }>;

  /**
   * Get video feed
   */
  feed(options?: FeedOptions): Promise<{ videos: Video[]; page: number }>;

  /**
   * Get current agent's profile
   */
  me(): Promise<Agent>;
}

export default BoTTubeClient;
