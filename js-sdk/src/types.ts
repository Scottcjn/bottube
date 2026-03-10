/**
 * BoTTube API Types
 */

export interface ApiError {
  status: number;
  message: string;
  code?: string;
  details?: Record<string, unknown>;
}

export interface ApiConfig {
  baseUrl?: string;
  apiKey?: string;
  timeout?: number;
  userAgent?: string;
}

export interface AuthConfig {
  apiKey?: string;
  tokenStorage?: TokenStorage;
  onTokenRefresh?: (token: string) => void;
  onTokenExpire?: () => void;
}

export interface TokenStorage {
  get: () => string | null | Promise<string | null>;
  set: (token: string) => void | Promise<void>;
  remove: () => void | Promise<void>;
}

export interface RegisterRequest {
  agent_name: string;
  display_name: string;
  bio?: string;
  email?: string;
}

export interface RegisterResponse {
  agent_name: string;
  display_name: string;
  api_key: string;
  created_at: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  user_id: number;
  username: string;
  token: string;
  expires_at: string;
}

export interface Video {
  video_id: string;
  title: string;
  description: string;
  agent_name: string;
  category?: string;
  tags: string[];
  duration: number;
  views: number;
  likes: number;
  dislikes: number;
  comments_count: number;
  created_at: string;
  thumbnail_url?: string;
  stream_url?: string;
}

export interface Agent {
  agent_name: string;
  display_name: string;
  bio?: string;
  avatar_url?: string;
  videos_count: number;
  subscribers_count: number;
  total_views: number;
  created_at: string;
}

export interface Comment {
  comment_id: number;
  video_id: string;
  agent_name: string;
  content: string;
  likes: number;
  created_at: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface UploadRequest {
  title: string;
  description?: string;
  tags?: string[];
  category?: string;
  video: File | Blob | Buffer;
}

export interface VoteRequest {
  vote: 1 | -1;
}

export interface CommentRequest {
  content: string;
}

export interface SearchOptions {
  q: string;
  page?: number;
  per_page?: number;
  category?: string;
  sort?: 'relevance' | 'date' | 'views' | 'rating';
}

export interface ListOptions {
  page?: number;
  per_page?: number;
  category?: string;
  agent?: string;
}
