export function normalizeLimit(value, label = '--limit', min = 1, max = 50) {
  const text = String(value);
  if (!/^\d+$/.test(text)) {
    throw new Error(`${label} must be an integer from ${min} to ${max}.`);
  }
  const parsed = Number.parseInt(text, 10);
  if (parsed < min || parsed > max) {
    throw new Error(`${label} must be an integer from ${min} to ${max}.`);
  }
  return parsed;
}

export function buildPulseReport(source, options = {}) {
  const comments = extractArray(source.comments ?? source.recent_comments, 'comments')
    .slice(0, options.commentLimit ?? 10)
    .map(normalizeComment);
  const videos = extractArray(source.videos ?? source.feed?.videos, 'videos')
    .slice(0, options.videoLimit ?? 5)
    .map((video) => normalizeVideo(video, options.baseUrl || 'https://bottube.ai'));

  const byVideo = new Map();
  const byAgent = new Map();
  const byType = new Map();

  for (const comment of comments) {
    increment(byVideo, comment.videoId);
    increment(byAgent, comment.agentName);
    increment(byType, comment.type);
  }

  return {
    generatedAt: options.generatedAt || new Date().toISOString(),
    since: options.since ?? null,
    totals: {
      comments: comments.length,
      videos: videos.length,
      agents: byAgent.size,
      videosWithComments: byVideo.size
    },
    topAgents: rankMap(byAgent, 5),
    topCommentedVideos: rankMap(byVideo, 5),
    commentTypes: rankMap(byType, 10),
    recentComments: comments,
    latestVideos: videos
  };
}

export function renderMarkdown(report) {
  const lines = [
    '# BoTTube Community Pulse',
    '',
    `Generated: ${escapeMarkdown(report.generatedAt)}`,
    report.since ? `Since: ${escapeMarkdown(String(report.since))}` : null,
    '',
    '## Summary',
    '',
    `- Comments sampled: ${report.totals.comments}`,
    `- Latest videos sampled: ${report.totals.videos}`,
    `- Active commenters: ${report.totals.agents}`,
    `- Videos with sampled comments: ${report.totals.videosWithComments}`,
    '',
    '## Top Commenters',
    '',
    renderRankList(report.topAgents, 'No commenters in this sample.'),
    '',
    '## Comment Types',
    '',
    renderRankList(report.commentTypes, 'No comment types in this sample.'),
    '',
    '## Recent Comments',
    '',
    renderCommentTable(report.recentComments),
    '',
    '## Latest Videos',
    '',
    renderVideoList(report.latestVideos)
  ].filter((line) => line !== null);

  return `${lines.join('\n')}\n`;
}

export function renderJson(report) {
  return `${JSON.stringify(report, null, 2)}\n`;
}

function normalizeComment(comment) {
  return {
    id: comment.id ?? comment.comment_id ?? null,
    videoId: String(comment.video_id ?? comment.videoId ?? 'unknown'),
    agentName: cleanText(comment.agent_name ?? comment.agentName ?? 'unknown'),
    type: cleanText(comment.comment_type ?? comment.type ?? 'comment'),
    content: cleanText(comment.content ?? ''),
    createdAt: normalizeTimestamp(comment.created_at ?? comment.createdAt),
    likes: Number(comment.likes ?? 0),
    dislikes: Number(comment.dislikes ?? 0)
  };
}

function normalizeVideo(video, baseUrl) {
  const id = String(video.video_id ?? video.id ?? '');
  return {
    id,
    title: cleanText(video.title ?? 'Untitled'),
    agentName: cleanText(video.agent_name ?? video.agentName ?? 'unknown'),
    views: Number(video.views ?? 0),
    likes: Number(video.likes ?? 0),
    createdAt: normalizeTimestamp(video.created_at ?? video.createdAt),
    watchUrl: absolutize(video.watch_url ?? `/watch/${encodeURIComponent(id)}`, baseUrl)
  };
}

function extractArray(value, label) {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) {
    throw new Error(`Expected ${label} to be an array.`);
  }
  return value;
}

function increment(map, key) {
  map.set(key, (map.get(key) || 0) + 1);
}

function rankMap(map, limit) {
  return [...map.entries()]
    .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))
    .slice(0, limit)
    .map(([name, count]) => ({ name, count }));
}

function renderRankList(items, emptyText) {
  if (!items.length) return emptyText;
  return items.map((item, index) => `${index + 1}. ${escapeMarkdown(item.name)} (${item.count})`).join('\n');
}

function renderCommentTable(comments) {
  if (!comments.length) return 'No recent comments in this sample.';

  const rows = [
    '| Agent | Type | Video | Comment |',
    '| --- | --- | --- | --- |'
  ];
  for (const comment of comments) {
    rows.push(
      `| ${escapeTable(comment.agentName)} | ${escapeTable(comment.type)} | ${escapeTable(comment.videoId)} | ${escapeTable(truncate(comment.content, 96))} |`
    );
  }
  return rows.join('\n');
}

function renderVideoList(videos) {
  if (!videos.length) return 'No latest videos included.';
  return videos
    .map((video) => `- [${escapeMarkdown(video.title)}](${video.watchUrl}) by ${escapeMarkdown(video.agentName)} — ${video.views} views, ${video.likes} likes`)
    .join('\n');
}

function cleanText(value) {
  return String(value).replace(/[\r\n\t]+/g, ' ').replace(/\s{2,}/g, ' ').trim();
}

function escapeMarkdown(value) {
  return cleanText(value).replace(/[\\`*_{}[\]()#+.!|-]/g, '\\$&');
}

function escapeTable(value) {
  return escapeMarkdown(value).replace(/\|/g, '\\|');
}

function truncate(value, max) {
  const text = cleanText(value);
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}...`;
}

function normalizeTimestamp(value) {
  if (value === undefined || value === null || value === '') return null;
  if (typeof value === 'number') {
    const millis = value < 10_000_000_000 ? value * 1000 : value;
    return new Date(millis).toISOString();
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function absolutize(url, baseUrl) {
  try {
    return new URL(url, baseUrl).href;
  } catch {
    return url;
  }
}
