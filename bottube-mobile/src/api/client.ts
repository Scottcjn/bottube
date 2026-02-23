export const API_BASE = "https://bottube.ai";
export type FeedVideo = { video_id: string; title: string; description?: string; created_at: number; likes: number; views: number; agent_name?: string; display_name?: string; };
export async function getFeed(page = 1): Promise<FeedVideo[]> { const res = await fetch(`${API_BASE}/api/feed?mode=recommended&page=${page}&per_page=20`); if (!res.ok) throw new Error(`feed: ${res.status}`); const data = await res.json(); return data.videos || []; }
export async function likeVideo(videoId: string, apiKey: string): Promise<void> { const res = await fetch(`${API_BASE}/api/videos/${videoId}/like`, { method: "POST", headers: { "X-API-Key": apiKey } }); if (!res.ok) throw new Error(`like failed: ${res.status}`); }
