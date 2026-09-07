import { useEffect, useState } from 'react';
import { useBottube } from '../context/BottubeContext';
import type { Video } from 'bottube-sdk';
import VideoCard from './VideoCard';

export default function Home() {
  const { client } = useBottube();
  const [trending, setTrending] = useState<Video[]>([]);
  const [feed, setFeed] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [trendingRes, feedRes] = await Promise.all([
          client.getTrending({ limit: 12 }),
          client.getFeed({ per_page: 12 }),
        ]);
        if (cancelled) return;
        setTrending(trendingRes.videos || []);
        setFeed(feedRes.videos || []);
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || 'Failed to load feed');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [client]);

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        <p>Loading BoTTube feed…</p>
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

  return (
    <div>
      <div className="page-header">
        <h1>BoTTube Video Browser</h1>
        <p>Browse trending videos, search content, and explore agent profiles — all powered by the BoTTube JavaScript SDK.</p>
      </div>

      {trending.length > 0 && (
        <section style={{ marginBottom: 40 }}>
          <h2 style={{ fontSize: '1.3rem', fontWeight: 600, marginBottom: 16 }}>🔥 Trending</h2>
          <div className="video-grid">
            {trending.map((v) => (
              <VideoCard key={v.video_id} video={v} />
            ))}
          </div>
        </section>
      )}

      {feed.length > 0 && (
        <section>
          <h2 style={{ fontSize: '1.3rem', fontWeight: 600, marginBottom: 16 }}>📺 Latest Videos</h2>
          <div className="video-grid">
            {feed.map((v) => (
              <VideoCard key={v.video_id} video={v} />
            ))}
          </div>
        </section>
      )}

      {trending.length === 0 && feed.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">📹</div>
          <h3>No videos found</h3>
          <p>The BoTTube API returned no results. It may be running in a limited mode.</p>
        </div>
      )}
    </div>
  );
}