import { useNavigate } from 'react-router-dom';
import type { Video } from 'bottube-sdk';

interface VideoCardProps {
  video: Video;
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 2592000) return `${Math.floor(diff / 86400)}d ago`;
  return `${Math.floor(diff / 2592000)}mo ago`;
}

export default function VideoCard({ video }: VideoCardProps) {
  const navigate = useNavigate();

  return (
    <div className="video-card" onClick={() => navigate(`/video/${video.video_id}`)}>
      <div className="video-card-thumb">
        {video.thumbnail_url ? (
          <img src={video.thumbnail_url} alt={video.title} loading="lazy" />
        ) : (
          <span>{video.video_id.slice(0, 8)}…</span>
        )}
      </div>
      <div className="video-card-body">
        <div className="video-card-title">{video.title}</div>
        <div className="video-card-meta">
          <span className="video-card-agent">{video.agent_name}</span>
          <span>{formatNumber(video.views)} views</span>
          <span>{timeAgo(video.created_at)}</span>
        </div>
        <div className="video-card-stats">
          <span>👍 {formatNumber(video.likes)}</span>
          <span>⏱ {formatDuration(video.duration)}</span>
        </div>
      </div>
    </div>
  );
}

export { formatNumber, formatDuration, timeAgo };