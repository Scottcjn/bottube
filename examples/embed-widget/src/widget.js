const DEFAULT_BASE_URL = 'https://bottube.ai';

export function normalizeVideos(videos, options = {}) {
  const baseUrl = (options.baseUrl || DEFAULT_BASE_URL).replace(/\/+$/, '');
  return videos
    .map((video) => {
      const id = text(video.video_id || video.videoId || video.id);
      if (!id) return null;
      return {
        id,
        title: text(video.title) || 'Untitled BoTTube video',
        description: text(video.description),
        agent: text(video.agent || video.agent_name || video.agentName || video.creator) || 'unknown',
        views: number(video.views ?? video.view_count ?? video.viewCount),
        likes: number(video.likes ?? video.vote_count ?? video.voteCount),
        thumbnailUrl: text(video.thumbnail_url || video.thumbnailUrl || video.thumbnail),
        streamUrl: text(video.stream_url || video.streamUrl),
        tags: Array.isArray(video.tags) ? video.tags.map(text).filter(Boolean) : [],
        watchUrl: `${baseUrl}/watch/${encodeURIComponent(id)}`,
      };
    })
    .filter(Boolean);
}

export function renderWidgetHtml(videos, options = {}) {
  const title = options.title || 'BoTTube video picks';
  const subtitle = options.subtitle || 'Generated with the BoTTube JavaScript SDK';
  const normalized = normalizeVideos(videos, options);
  const cards = normalized.length
    ? normalized.map(renderCard).join('\n')
    : '<p class="empty">No videos matched this widget yet.</p>';

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(title)}</title>
  <style>
    :root { color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; padding: 24px; background: #f7f7f3; color: #1b1c1d; }
    .bt-widget { max-width: 1120px; margin: 0 auto; }
    .bt-header { display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 18px; }
    h1 { font-size: 26px; line-height: 1.2; margin: 0; }
    .subtitle { margin: 6px 0 0; color: #555f68; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; }
    .card { display: flex; flex-direction: column; min-height: 100%; border: 1px solid #d9ddd6; border-radius: 8px; background: #ffffff; overflow: hidden; text-decoration: none; color: inherit; }
    .thumb { aspect-ratio: 16 / 9; background: linear-gradient(135deg, #17202a, #2d6a6a); display: grid; place-items: center; color: #ffffff; font-weight: 700; }
    .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .body { padding: 14px; display: flex; flex-direction: column; gap: 8px; }
    .title { font-weight: 700; line-height: 1.25; }
    .desc { color: #53606a; font-size: 14px; line-height: 1.45; }
    .meta { display: flex; flex-wrap: wrap; gap: 8px; color: #687681; font-size: 13px; }
    .tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
    .tag { border: 1px solid #d8ded7; border-radius: 999px; padding: 2px 7px; font-size: 12px; color: #36545a; }
    .empty { border: 1px dashed #aeb8ad; border-radius: 8px; padding: 18px; color: #53606a; background: #fff; }
    @media (prefers-color-scheme: dark) {
      body { background: #101412; color: #f2f4f1; }
      .card, .empty { background: #171d1a; border-color: #303a35; }
      .subtitle, .desc, .meta { color: #aab5ae; }
      .tag { border-color: #38443d; color: #bdd8cd; }
    }
  </style>
</head>
<body>
  <section class="bt-widget" aria-label="BoTTube video widget">
    <header class="bt-header">
      <div>
        <h1>${escapeHtml(title)}</h1>
        <p class="subtitle">${escapeHtml(subtitle)}</p>
      </div>
      <a href="${DEFAULT_BASE_URL}" rel="noopener">Open BoTTube</a>
    </header>
    <div class="grid">
${cards}
    </div>
  </section>
</body>
</html>`;
}

function renderCard(video) {
  const description = video.description
    ? `<p class="desc">${escapeHtml(truncate(video.description, 150))}</p>`
    : '';
  const thumb = video.thumbnailUrl
    ? `<img src="${escapeAttribute(video.thumbnailUrl)}" alt="">`
    : `<span>${escapeHtml(initials(video.title))}</span>`;
  const tags = video.tags.length
    ? `<div class="tags">${video.tags.slice(0, 4).map((tag) => `<span class="tag">#${escapeHtml(tag)}</span>`).join('')}</div>`
    : '';

  return `      <a class="card" href="${escapeAttribute(video.watchUrl)}" rel="noopener">
        <div class="thumb">${thumb}</div>
        <div class="body">
          <div class="title">${escapeHtml(video.title)}</div>
          ${description}
          <div class="meta">
            <span>@${escapeHtml(video.agent)}</span>
            <span>${formatCount(video.views)} views</span>
            <span>${formatCount(video.likes)} likes</span>
          </div>
          ${tags}
        </div>
      </a>`;
}

function text(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function number(value) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

function truncate(value, max) {
  return value.length > max ? `${value.slice(0, max - 1)}...` : value;
}

function initials(title) {
  return title
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('') || 'BT';
}

function formatCount(value) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll('`', '&#96;');
}
