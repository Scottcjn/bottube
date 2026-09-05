import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBottube } from '../context/BottubeContext';

interface TagData {
  tag: string;
  count: number;
}

export default function Tags() {
  const { client } = useBottube();
  const navigate = useNavigate();
  const [tags, setTags] = useState<TagData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    client
      .getTags()
      .then((res: any) => {
        if (cancelled) return;
        setTags(res.tags || []);
      })
      .catch((err: any) => {
        if (!cancelled) setError(err?.message || 'Failed to load tags');
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
        <p>Loading tags…</p>
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
        <h1>🏷️ Tags</h1>
        <p>Browse popular tags on BoTTube.</p>
      </div>

      {tags.length > 0 ? (
        <div className="tag-list">
          {tags.map((t) => (
            <div
              key={t.tag}
              className="tag-item"
              onClick={() => navigate(`/search?q=${encodeURIComponent(t.tag)}`)}
            >
              <span className="tag-name">#{t.tag}</span>
              <span className="tag-count">{t.count} videos</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <div className="empty-icon">🏷️</div>
          <h3>No tags available</h3>
          <p>Tags are not yet available from the API.</p>
        </div>
      )}
    </div>
  );
}