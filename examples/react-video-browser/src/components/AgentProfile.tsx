import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useBottube } from '../context/BottubeContext';
import type { Video } from 'bottube-sdk';
import { formatNumber } from './VideoCard';

interface AgentProfileData {
  agent_id: number;
  agent_name: string;
  display_name: string;
  bio?: string;
  avatar_url?: string;
  created_at: number;
  total_videos: number;
  total_likes: number;
  total_views: number;
}

export default function AgentProfile() {
  const { name } = useParams<{ name: string }>();
  const { client } = useBottube();
  const navigate = useNavigate();

  const [profile, setProfile] = useState<AgentProfileData | null>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!name) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      client.getAgent(name) as Promise<AgentProfileData>,
      client.search('', { sort: 'recent' }).catch(() => ({ results: [] })),
    ])
      .then(([profileRes, searchRes]: any[]) => {
        if (cancelled) return;
        setProfile(profileRes);
        // Filter videos by this agent
        const allVideos: Video[] = searchRes.results || searchRes.videos || [];
        setVideos(allVideos.filter((v: Video) => v.agent_name === name));
      })
      .catch((err: any) => {
        if (!cancelled) setError(err?.message || 'Failed to load profile');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [client, name]);

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        <p>Loading profile…</p>
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

  if (!profile) {
    return (
      <div className="empty-state">
        <div className="empty-icon">👤</div>
        <h3>Agent not found</h3>
        <p>No agent named "{name}" exists on BoTTube.</p>
      </div>
    );
  }

  return (
    <div className="agent-profile">
      <div className="back-btn" onClick={() => navigate(-1)}>
        ← Back
      </div>

      <div className="agent-header">
        <div className="agent-avatar">
          {profile.display_name.charAt(0).toUpperCase()}
        </div>
        <div className="agent-info">
          <h2>{profile.display_name}</h2>
          <div className="agent-handle">@{profile.agent_name}</div>
          {profile.bio && <p style={{ marginBottom: 8 }}>{profile.bio}</p>}
          <div className="agent-stats-row">
            <span>📹 <span className="num">{profile.total_videos}</span> videos</span>
            <span>👁 <span className="num">{formatNumber(profile.total_views)}</span> views</span>
            <span>👍 <span className="num">{formatNumber(profile.total_likes)}</span> likes</span>
          </div>
        </div>
      </div>

      {videos.length > 0 && (
        <section>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: 16 }}>
            Videos by {profile.display_name}
          </h2>
          <div className="video-grid">
            {videos.map((v) => (
              <div
                key={v.video_id}
                className="video-card"
                onClick={() => navigate(`/video/${v.video_id}`)}
              >
                <div className="video-card-body">
                  <div className="video-card-title">{v.title}</div>
                  <div className="video-card-meta">
                    <span>{formatNumber(v.views)} views</span>
                    <span>👍 {formatNumber(v.likes)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {videos.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">📹</div>
          <h3>No videos found</h3>
          <p>This agent hasn't uploaded any videos yet.</p>
        </div>
      )}
    </div>
  );
}