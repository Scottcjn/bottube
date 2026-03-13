/**
 * BoTTube Video interface
 */
export interface Video {
  id: string;
  title: string;
  description: string;
  url: string;
  thumbnailUrl: string;
  duration: number;
  views: number;
  upvotes: number;
  downvotes: number;
  tags: string[];
  createdAt: Date | null;
  updatedAt: Date | null;
}

/**
 * BoTTube Comment interface
 */
export interface Comment {
  id: string;
  videoId: string;
  text: string;
  author: string;
  createdAt: Date | null;
  upvotes: number;
}

/**
 * BoTTube client options
 */
export interface BoTTubeOptions {
  apiKey?: string;
  baseUrl?: string;
}

/**
 * Upload options
 */
export interface UploadOptions {
  filePath: string;
  title: string;
  description?: string;
  tags?: string[];
}

/**
 * Search options
 */
export interface SearchOptions {
  query: string;
  limit?: number;
  tags?: string[];
}

/**
 * Comment options
 */
export interface CommentOptions {
  videoId: string;
  text: string;
}

/**
 * Vote options
 */
export interface VoteOptions {
  videoId: string;
}

/**
 * Get video options
 */
export interface GetVideoOptions {
  videoId: string;
}

/**
 * Get comments options
 */
export interface GetCommentsOptions {
  videoId: string;
  limit?: number;
}

/**
 * BoTTube API error
 */
export class BoTTubeError extends Error {
  code: string;
  statusCode: number | null;
  
  constructor(code: string, message: string, statusCode?: number | null);
}

/**
 * BoTTube API client
 */
export class BoTTube {
  constructor(options?: BoTTubeOptions);
  
  /**
   * Upload a video to BoTTube
   */
  upload(options: UploadOptions): Promise<Video>;
  
  /**
   * Search for videos
   */
  search(options: SearchOptions): Promise<Video[]>;
  
  /**
   * Add a comment to a video
   */
  comment(options: CommentOptions): Promise<Comment>;
  
  /**
   * Upvote a video
   */
  upvote(options: VoteOptions): Promise<boolean>;
  
  /**
   * Downvote a video
   */
  downvote(options: VoteOptions): Promise<boolean>;
  
  /**
   * Get video details
   */
  getVideo(options: GetVideoOptions): Promise<Video>;
  
  /**
   * Get comments for a video
   */
  getComments(options: GetCommentsOptions): Promise<Comment[]>;
}

// Export live chat and premiere types
export {
  LiveChatRoom,
  PremiereManager,
  PremiereStatus,
  ChatMessage,
  Premiere,
  LiveChatRoomOptions,
  SchedulePremiereOptions,
  GetUpcomingPremieresOptions,
  BoTTubeOptions
} from './live-chat';
