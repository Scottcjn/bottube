export function normalizeVideo(video, baseUrl = 'https://bottube.ai', streamUrl = null) {
  const id = String(video?.video_id ?? '').trim();
  if (!id) throw new Error('video_id is required');

  const cleanBase = String(baseUrl).replace(/\/+$/, '');
  const tags = Array.isArray(video.tags) ? video.tags.map(String) : [];

  return {
    video_id: id,
    title: String(video.title ?? ''),
    agent_name: String(video.agent_name ?? ''),
    description: String(video.description ?? ''),
    tags,
    duration_seconds: finiteNumber(video.duration),
    views: finiteNumber(video.views),
    likes: finiteNumber(video.likes),
    dislikes: finiteNumber(video.dislikes),
    created_at: finiteNumber(video.created_at),
    watch_url: `${cleanBase}/watch/${encodeURIComponent(id)}`,
    stream_url: streamUrl || video.stream_url || `${cleanBase}/api/videos/${encodeURIComponent(id)}/stream`,
  };
}

export function mergePages(pages, baseUrl = 'https://bottube.ai', streamUrlFor = null) {
  const seen = new Set();
  const videos = [];

  for (const page of pages) {
    for (const video of page?.videos ?? []) {
      const id = String(video?.video_id ?? '').trim();
      if (!id || seen.has(id)) continue;
      seen.add(id);
      const streamUrl = streamUrlFor ? streamUrlFor(id) : null;
      videos.push(normalizeVideo(video, baseUrl, streamUrl));
    }
  }

  return videos;
}

export function buildManifest(videos, { baseUrl = 'https://bottube.ai', pagesRequested = 1, generatedAt = new Date().toISOString() } = {}) {
  return {
    schema: 'bottube.video-archive-manifest.v1',
    generated_at: generatedAt,
    source: String(baseUrl).replace(/\/+$/, ''),
    pages_requested: pagesRequested,
    video_count: videos.length,
    videos,
  };
}

export function renderMarkdown(manifest) {
  const lines = [
    '# BoTTube Video Archive Manifest',
    '',
    `- Generated: ${manifest.generated_at}`,
    `- Source: ${manifest.source}`,
    `- Videos: ${manifest.video_count}`,
    '',
  ];

  for (const video of manifest.videos) {
    lines.push(`## ${escapeMarkdown(video.title || video.video_id)}`);
    lines.push('');
    lines.push(`- Video ID: \`${video.video_id}\``);
    lines.push(`- Agent: ${escapeMarkdown(video.agent_name || 'unknown')}`);
    lines.push(`- Watch: ${video.watch_url}`);
    lines.push(`- Stream: ${video.stream_url}`);
    lines.push(`- Duration: ${video.duration_seconds}s`);
    lines.push(`- Views / likes / dislikes: ${video.views} / ${video.likes} / ${video.dislikes}`);
    if (video.tags.length) lines.push(`- Tags: ${video.tags.map((tag) => `\`${escapeMarkdown(tag)}\``).join(', ')}`);
    if (video.description) {
      lines.push('');
      lines.push(video.description.replace(/\r?\n/g, ' ').trim());
    }
    lines.push('');
  }

  return `${lines.join('\n').trim()}\n`;
}

function finiteNumber(value) {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function escapeMarkdown(value) {
  return String(value).replace(/([\\`*_{}[\]()#+.!|-])/g, '\\$1');
}
