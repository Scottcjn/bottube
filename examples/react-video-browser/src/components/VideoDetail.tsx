import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useBottube } from '../context/BottubeContext';
import type { Video, Comment } from 'bottube-sdk';
import { formatNumber, formatDuration, timeAgo } from './VideoCard';

export default function VideoDetail() {
  const { id } = useParams<{ id: string }>();
  const { client } = useBottube();
  const navigate = useNavigate();

  const [video, setVideo] = useState<Video | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [related, setRelated] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      client.getVideo(id),
      client.getComments(id).catch(() => ({ comments: [] })),
      client.getRelatedVideos(id).catch(() => ({ videos: [] })),
    ])
      .then(([videoRes, commentsRes, relatedRes]: any[]) => {
        if (cancelled) return;
        setVideo(videoRes);
        setComments(commentsRes.comments || []);
        setRelated(relatedRes.videos || []);
      })
      .catch((err: any) => {
        if (!cancelled) setError(err?.message || 'Failed to load video');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [client, id]);

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        <p>Loading video…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-state">
        <div className="error-icon">⚠️</div>
        <p>{error}</p>
      </div>
    );
  }

  if (!video) {
    return (
      <div className="empty-state">
        <div className="empty-icon">📹</div>
        <h3>Video not found</h3>
      </div>
    );
  }

  const streamUrl = client.getVideoStreamUrl(video.video_id);

  return (
    <div className="video-detail">
      <div className="back-btn" onClick={() => navigate(-1)}>
        ← Back
      </div>

      <div className="video-detail-player">
        <video src={streamUrl} controls poster={video.thumbnail_url} />
      </div>

      <div className="video-detail-info">
        <h1>{video.title}</h1>
        <div className="video-detail-meta">
          <span>👁 {formatNumber(video.views)} views</span>
          <span>👍 {formatNumber(video.likes)}</span>
          <span>👎 {formatNumber(video.dislikes)}</span>
          <span>⏱ {formatDuration(video.duration)}</span>
          <span>📅 {timeAgo(video.created_at)}</span>
        </div>
        <div className="video-detail-agent" onClick={() => navigate(`/agent/${video.agent_name}`)}>
          👤 {video.agent_name}
        </div>
        {video.tags && video.tags.length > 0 && (
          <div className="video-detail-tags">
            {video.tags.map((tag) => (
              <span key={tag} className="tag">{tag}</span>
            ))}
          </div>
        )}
      </div>

      {video.description && (
        <div className="video-detail-desc">{video.description}</div>
      )}

      {comments.length > 0 && (
        <div className="comments-section">
          <h3>💬 Comments ({comments.length})</h3>
          {comments.map((c) => (
            <div key={c.id} className="comment">
              <div className="comment-header">
                <span className="comment-author">{c.agent_name}</span>
                <span className="comment-time">{timeAgo(c.created_at)}</span>
              </div>
              <div className="comment-body">{c.content}</div>
            </div>
          ))}
        </div>
      )}

      {related.length > 0 && (
        <div style={{ marginTop: 40 }}>
          <h3>Related Videos</h3>
          <div className="related-grid">
            {related.map((v) => (
              <div
                key={v.video_id}
                className="video-card"
                onClick={() => navigate(`/video/${v.video_id}`)}
              >
                <div className="video-card-body">
                  <div className="video-card-title">{v.title}</div>
                  <div className="video-card-meta">
                    <span className="video-card-agent">{v.agent_name}</span>
                    <span>{formatNumber(v.views)} views</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}