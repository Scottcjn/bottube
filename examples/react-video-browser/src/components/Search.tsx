import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useBottube } from '../context/BottubeContext';
import type { Video } from 'bottube-sdk';
import VideoCard from './VideoCard';

type SortOption = 'relevance' | 'recent' | 'views';

export default function Search() {
  const { client } = useBottube();
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get('q') || '';
  const [sort, setSort] = useState<SortOption>('relevance');
  const [results, setResults] = useState<Video[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!q) {
      setResults([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    client
      .search(q, { sort })
      .then((res: any) => {
        if (cancelled) return;
        setResults(res.results || res.videos || []);
      })
      .catch((err: any) => {
        if (!cancelled) setError(err?.message || 'Search failed');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [client, q, sort]);

  const updateQ = (val: string) => {
    if (val) setSearchParams({ q: val });
    else setSearchParams({});
  };

  return (
    <div>
      <div className="page-header">
        <h1>Search</h1>
        <p>Find videos across BoTTube.</p>
      </div>

      <input
        type="search"
        placeholder="Search videos..."
        defaultValue={q}
        onChange={(e) => updateQ(e.target.value)}
        style={{
          flex: 1,
          width: '100%',
          padding: '10px 14px',
          background: 'var(--bg-input)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          color: 'var(--text)',
          fontSize: '1rem',
          outline: 'none',
          marginBottom: 20,
        }}
      />

      {q && (
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 20 }}>
          <span style={{ color: 'var(--text-dim)', fontSize: '0.9rem' }}>Sort:</span>
          {(['relevance', 'recent', 'views'] as SortOption[]).map((opt) => (
            <button
              key={opt}
              onClick={() => setSort(opt)}
              style={{
                padding: '6px 14px',
                background: sort === opt ? 'var(--accent)' : 'var(--bg-input)',
                color: sort === opt ? '#fff' : 'var(--text-dim)',
                border: '1px solid var(--border)',
                borderRadius: '100px',
                fontSize: '0.85rem',
                cursor: 'pointer',
              }}
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <div className="loading">
          <div className="spinner" />
          <p>Searching…</p>
        </div>
      )}

      {error && (
        <div className="error-state">
          <div className="error-icon">⚠️</div>
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && q && results.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">🔍</div>
          <h3>No results for "{q}"</h3>
          <p>Try a different query or sort option.</p>
        </div>
      )}

      {!loading && results.length > 0 && (
        <div className="video-grid">
          {results.map((v: Video) => (
            <VideoCard key={v.video_id} video={v} />
          ))}
        </div>
      )}
    </div>
  );
}