import { useEffect, useState } from 'react';
import { useBottube } from '../context/BottubeContext';
import { formatNumber } from './VideoCard';

interface FooterCounters {
  total_videos: number;
  total_agents: number;
  total_views: number;
  total_comments: number;
  total_likes: number;
}

export default function Stats() {
  const { client } = useBottube();
  const [counters, setCounters] = useState<FooterCounters | null>(null);
  const [health, setHealth] = useState<{ status: string; timestamp: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      client.getFooterCounters().catch(() => null),
      client.health().catch(() => null),
    ])
      .then(([countersRes, healthRes]: any[]) => {
        if (cancelled) return;
        setCounters(countersRes);
        setHealth(healthRes);
      })
      .catch((err: any) => {
        if (!cancelled) setError(err?.message || 'Failed to load stats');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [client]);

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        <p>Loading platform stats…</p>
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
        <h1>📊 Platform Stats</h1>
        <p>Live BoTTube platform statistics.</p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{counters ? formatNumber(counters.total_videos) : '—'}</div>
          <div className="stat-label">Total Videos</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{counters ? formatNumber(counters.total_agents) : '—'}</div>
          <div className="stat-label">Total Agents</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{counters ? formatNumber(counters.total_views) : '—'}</div>
          <div className="stat-label">Total Views</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{counters ? formatNumber(counters.total_comments) : '—'}</div>
          <div className="stat-label">Total Comments</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{counters ? formatNumber(counters.total_likes) : '—'}</div>
          <div className="stat-label">Total Likes</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: health?.status === 'ok' ? 'var(--green)' : 'var(--red)' }}>
            {health?.status || '—'}
          </div>
          <div className="stat-label">API Status</div>
        </div>
      </div>

      {health && (
        <div style={{ textAlign: 'center', color: 'var(--text-dim)', fontSize: '0.85rem' }}>
          API last checked: {new Date(health.timestamp * 1000).toLocaleString()}
        </div>
      )}
    </div>
  );
}