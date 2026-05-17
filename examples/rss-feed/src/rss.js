const DEFAULT_SITE_URL = 'https://bottube.ai';

export function escapeXml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

export function extractVideos(response, limit = 20) {
  const source = Array.isArray(response)
    ? response
    : response?.videos ?? response?.results ?? response?.items ?? response?.data ?? [];

  if (!Array.isArray(source)) return [];
  return source
    .filter((video) => video && typeof video === 'object')
    .slice(0, normalizeLimit(limit));
}

export function normalizeLimit(limit) {
  const parsed = Number.parseInt(String(limit), 10);
  if (!Number.isFinite(parsed) || parsed < 1) return 20;
  return Math.min(parsed, 50);
}

export function generateRss(options) {
  const siteUrl = trimTrailingSlash(options.siteUrl || DEFAULT_SITE_URL);
  const title = options.title || 'BoTTube Videos';
  const description = options.description || 'A generated RSS feed powered by the BoTTube JavaScript SDK.';
  const feedUrl = options.feedUrl;
  const videos = Array.isArray(options.videos) ? options.videos : [];
  const now = new Date().toUTCString();

  const atomSelf = feedUrl
    ? `    <atom:link href="${escapeXml(feedUrl)}" rel="self" type="application/rss+xml"/>\n`
    : '';

  const items = videos.map((video) => renderItem(video, siteUrl)).join('');

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
    '  <channel>',
    `    <title>${escapeXml(title)}</title>`,
    `    <link>${escapeXml(siteUrl)}</link>`,
    `    <description>${escapeXml(description)}</description>`,
    atomSelf.trimEnd(),
    `    <lastBuildDate>${now}</lastBuildDate>`,
    '    <generator>BoTTube RSS feed example</generator>',
    items.trimEnd(),
    '  </channel>',
    '</rss>',
    ''
  ].filter(Boolean).join('\n');
}

function renderItem(video, siteUrl) {
  const link = getVideoUrl(video, siteUrl);
  const title = getFirst(video, ['title', 'name'], 'Untitled BoTTube video');
  const description = getDescription(video);
  const pubDate = getPubDate(video);

  return [
    '    <item>',
    `      <title>${escapeXml(title)}</title>`,
    `      <link>${escapeXml(link)}</link>`,
    `      <guid isPermaLink="true">${escapeXml(link)}</guid>`,
    `      <description><![CDATA[${escapeCdata(description)}]]></description>`,
    pubDate ? `      <pubDate>${pubDate}</pubDate>` : '',
    '    </item>',
    ''
  ].filter(Boolean).join('\n');
}

function getDescription(video) {
  const description = getFirst(video, ['description', 'summary', 'caption'], '');
  if (description) return description;

  const creator = getFirst(video, ['creator', 'agent_name', 'author', 'uploader'], '');
  const views = getFirst(video, ['view_count', 'views'], '');
  const parts = [];
  if (creator) parts.push(`Creator: ${creator}`);
  if (views !== '') parts.push(`Views: ${views}`);
  return parts.length ? parts.join(' | ') : 'Watch this video on BoTTube.';
}

function getVideoUrl(video, siteUrl) {
  const absoluteUrl = getFirst(video, ['url', 'watch_url', 'link'], '');
  if (absoluteUrl && /^https?:\/\//i.test(absoluteUrl)) return absoluteUrl;

  const relativeUrl = getFirst(video, ['watch_url', 'link'], '');
  if (relativeUrl && String(relativeUrl).startsWith('/')) return `${siteUrl}${relativeUrl}`;

  const id = getFirst(video, ['video_id', 'public_id', 'id', 'slug'], '');
  if (!id) return siteUrl;
  return `${siteUrl}/watch/${encodeURIComponent(String(id))}`;
}

function getPubDate(video) {
  const raw = getFirst(video, ['created_at', 'createdAt', 'uploaded_at', 'upload_date', 'timestamp'], '');
  if (!raw) return '';
  const date = new Date(normalizeDateValue(raw));
  if (Number.isNaN(date.getTime())) return '';
  return date.toUTCString();
}

function normalizeDateValue(value) {
  const numeric = typeof value === 'number' ? value : Number(value);
  if (Number.isFinite(numeric)) {
    return Math.abs(numeric) < 100000000000 ? numeric * 1000 : numeric;
  }
  return value;
}

function escapeCdata(value) {
  return String(value ?? '').replaceAll(']]>', ']]]]><![CDATA[>');
}

function getFirst(video, keys, fallback) {
  for (const key of keys) {
    const value = video[key];
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return fallback;
}

function trimTrailingSlash(value) {
  return String(value).replace(/\/+$/, '');
}
