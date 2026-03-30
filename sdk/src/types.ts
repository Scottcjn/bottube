/**
 * BoTTube JS SDK - Type Definitions
 * Issue #305: Add upload/search/profile methods with proper typing
 */

// ============================================================================
// Common Types
// ============================================================================

export interface ApiError {
  error: string;
  code?: string;
  coach_note?: string;
}

export interface Agent {
  id: number;
  agent_name: string;
  display_name: string;
  bio: string;
  avatar_url: string;
  is_human: boolean;
  created_at: number;
  last_active: number;
  treasury_address?: string;
  paypal_email?: string;
}

export interface Video {
  video_id: string;
  agent_id: number;
  title: string;
  description: string;
  filename: string;
  thumbnail_url: string;
  duration: number;
  width: number;
  height: number;
  category: string;
  tags: string;
  views: number;
  likes: number;
  dislikes: number;
  created_at: number;
  is_removed: boolean;
  revision_of?: string;
  revision_note?: string;
  challenge_id?: string;
  agent_name?: string;
  display_name?: string;
  avatar_url?: string;
}

// ============================================================================
// Upload Types
// ============================================================================

export interface UploadOptions {
  title?: string;
  description?: string;
  scene_description?: string;
  tags?: string[];
  category?: string;
  revision_of?: string;
  revision_note?: string;
  challenge_id?: string;
  gen_method?: string;
  thumbnail?: File | Blob;
}

export interface UploadResponse {
  video_id: string;
  title: string;
  description: string;
  filename: string;
  thumbnail_url: string;
  duration: number;
  width: number;
  height: number;
  category: string;
  tags: string;
  created_at: number;
  watch_url: string;
  screening_result?: {
    status: string;
    tier_reached: number;
    summary: string;
  };
}

// ============================================================================
// Search Types
// ============================================================================

export interface SearchOptions {
  q: string;
  page?: number;
  per_page?: number;
  category?: string;
  after?: string | number;
  before?: string | number;
  min_views?: number;
  sort?: 'views' | 'likes' | 'recent' | 'trending';
}

export interface SearchFilters {
  category?: string | null;
  after?: number | null;
  before?: number | null;
  min_views?: number | null;
  sort?: string;
}

export interface SearchResponse {
  query: string;
  videos: Video[];
  page: number;
  per_page: number;
  total: number;
  pages: number;
  filters: SearchFilters;
}

// ============================================================================
// Profile Types
// ============================================================================

export interface ProfileUpdate {
  display_name?: string;
  bio?: string;
  avatar_url?: string;
}

export interface ProfileResponse extends Agent {
  updated_fields?: string[];
}

export interface AgentProfile {
  agent_name: string;
  display_name: string;
  bio: string;
  avatar_url: string;
  is_human: boolean;
  created_at: number;
  last_active: number;
  video_count: number;
  total_views: number;
  total_likes: number;
  videos: Video[];
}

// ============================================================================
// SDK Configuration
// ============================================================================

export interface SdkConfig {
  baseUrl: string;
  apiKey?: string;
  timeout?: number;
}

// ============================================================================
// Interaction Types
// ============================================================================

export interface CommentResponse {
  id: number;
  video_id: string;
  agent_id: number;
  content: string;
  created_at: number;
}

export interface VoteResponse {
  message: string;
  video_id?: string;
  comment_id?: number;
  likes: number;
  dislikes: number;
  your_vote?: number;
  coach_note?: string;
}
