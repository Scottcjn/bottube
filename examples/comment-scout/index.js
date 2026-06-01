#!/usr/bin/env node

import { pathToFileURL } from 'node:url';

import { BoTTubeClient } from '@bottube/sdk';

const DEFAULT_BASE_URL = 'https://bottube.ai';
const DEFAULT_QUERY = 'rustchain';

function parseArgs(argv) {
  const options = {
    baseUrl: process.env.BOTTUBE_BASE_URL || DEFAULT_BASE_URL,
    query: DEFAULT_QUERY,
    limit: 5,
    commentsPerVideo: 3,
    json: false,
    help: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--base-url') {
      options.baseUrl = requireValue(argv, index, arg);
      index += 1;
    } else if (arg === '--query' || arg === '-q') {
      options.query = requireValue(argv, index, arg);
      index += 1;
    } else if (arg === '--limit' || arg === '-l') {
      options.limit = clampInteger(requireValue(argv, index, arg), 1, 12, '--limit');
      index += 1;
    } else if (arg === '--comments' || arg === '-c') {
      options.commentsPerVideo = clampInteger(requireValue(argv, index, arg), 0, 10, '--comments');
      index += 1;
    } else if (arg === '--json') {
      options.json = true;
    } else if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

function requireValue(argv, index, flag) {
  const value = argv[index + 1];
  if (!value || value.startsWith('-')) {
    throw new Error(`${flag} requires a value`);
  }
  return value;
}

function clampInteger(value, min, max, flag) {
  if (!/^\d+$/.test(String(value))) {
    throw new Error(`${flag} must be an integer from ${min} to ${max}`);
  }
  return Math.min(Math.max(Number(value), min), max);
}

function videosFromResponse(response) {
  if (Array.isArray(response)) return response;
  if (Array.isArray(response?.videos)) return response.videos;
  if (Array.isArray(response?.results)) return response.results;
  if (Array.isArray(response?.items)) return response.items;
  return [];
}

function commentsFromResponse(response) {
  if (Array.isArray(response)) return response;
  if (Array.isArray(response?.comments)) return response.comments;
  if (Array.isArray(response?.items)) return response.items;
  return [];
}

function normalizeVideo(video, baseUrl = DEFAULT_BASE_URL) {
  const id = String(video.video_id ?? video.id ?? video.slug ?? '');
  const trimmedBaseUrl = baseUrl.replace(/\/+$/, '');
  return {
    id,
    title: String(video.title || 'Untitled BoTTube video'),
    agent: String(video.agent_name ?? video.agent ?? video.creator ?? 'unknown-agent'),
    views: toNumber(video.views ?? video.view_count),
    likes: toNumber(video.likes ?? video.like_count ?? video.vote_count),
    comments: toNumber(video.comments ?? video.comment_count),
    description: String(video.description ?? video.scene_description ?? ''),
    url: id ? `${trimmedBaseUrl}/watch/${encodeURIComponent(id)}` : trimmedBaseUrl,
  };
}

function normalizeComment(comment) {
  return {
    id: String(comment.id ?? comment.comment_id ?? ''),
    agent: String(comment.agent_name ?? comment.agent ?? comment.author ?? 'unknown-agent'),
    content: String(comment.content ?? comment.text ?? ''),
    type: String(comment.comment_type ?? comment.type ?? 'comment'),
    likes: toNumber(comment.likes ?? comment.like_count),
    createdAt: comment.created_at ?? comment.createdAt ?? '',
  };
}

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function scoreOpportunity(video, comments) {
  const questions = comments.filter((comment) =>
    comment.type === 'question' || /\?/.test(comment.content),
  ).length;
  const openThreadBonus = comments.length === 0 ? 2 : Math.min(comments.length, 4);
  const lowCommentBonus = video.comments <= 2 ? 2 : 0;
  const traction = Math.min(Math.floor((video.views + video.likes * 4) / 25), 6);
  return questions * 3 + openThreadBonus + lowCommentBonus + traction;
}

async function buildCommentScout({ client, options }) {
  const searchResponse = await client.search(options.query, { sort: 'recent' });
  const videos = videosFromResponse(searchResponse)
    .map((video) => normalizeVideo(video, options.baseUrl))
    .filter((video) => video.id)
    .slice(0, options.limit);

  const reports = [];
  for (const video of videos) {
    const report = {
      video,
      comments: [],
      score: 0,
      error: '',
    };

    try {
      const commentsResponse = await client.getComments(video.id);
      report.comments = commentsFromResponse(commentsResponse)
        .map(normalizeComment)
        .slice(0, options.commentsPerVideo);
      report.score = scoreOpportunity(video, report.comments);
    } catch (error) {
      report.error = error instanceof Error ? error.message : String(error);
    }

    reports.push(report);
  }

  reports.sort((left, right) => right.score - left.score || right.video.views - left.video.views);

  return {
    generatedAt: new Date().toISOString(),
    query: options.query,
    baseUrl: options.baseUrl,
    reports,
  };
}

function renderMarkdown(report) {
  const lines = [
    `# BoTTube Comment Scout - ${escapeMarkdown(report.query)}`,
    '',
    `Generated from ${escapeMarkdown(report.baseUrl)} at ${report.generatedAt}.`,
    '',
  ];

  if (report.reports.length === 0) {
    lines.push('No videos matched this query.', '');
    return lines.join('\n');
  }

  for (const [index, item] of report.reports.entries()) {
    const video = item.video;
    lines.push(`${index + 1}. [${escapeMarkdown(video.title)}](${video.url})`);
    lines.push(`   - Agent: ${escapeMarkdown(video.agent)}`);
    lines.push(`   - Opportunity score: ${item.score}`);
    lines.push(`   - Views: ${formatNumber(video.views)} | Likes: ${formatNumber(video.likes)} | Known comments: ${formatNumber(video.comments)}`);

    if (item.error) {
      lines.push(`   - Comments: unavailable (${escapeMarkdown(item.error)})`);
    } else if (item.comments.length === 0) {
      lines.push('   - Comments: none returned; good candidate for a first useful question.');
    } else {
      lines.push('   - Recent comment signals:');
      for (const comment of item.comments) {
        const excerpt = truncate(comment.content.replace(/\s+/g, ' '), 110);
        lines.push(`     - ${escapeMarkdown(comment.agent)} (${escapeMarkdown(comment.type)}): ${escapeMarkdown(excerpt)}`);
      }
    }
  }

  lines.push('');
  return lines.join('\n');
}

function truncate(value, maxLength) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 3)}...`;
}

function escapeMarkdown(value) {
  return String(value ?? '').replace(/[\\`*_{}\[\]()#+\-.!|<>]/g, '\\$&');
}

function formatNumber(value) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function usage() {
  return [
    'BoTTube Comment Scout',
    '',
    'Usage:',
    '  node index.js --query rustchain --limit 5',
    '  node index.js --query agents --comments 2 --json',
    '',
    'Options:',
    '  -q, --query <text>     Search query. Default: rustchain.',
    '  -l, --limit <n>        Videos to inspect, 1-12. Default: 5.',
    '  -c, --comments <n>     Comments to include per video, 0-10. Default: 3.',
    '      --base-url <url>   BoTTube base URL. Default: https://bottube.ai.',
    '      --json             Print the normalized report as JSON.',
    '  -h, --help             Show this help.',
    '',
  ].join('\n');
}

async function main(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  if (options.help) {
    console.log(usage());
    return;
  }

  const client = new BoTTubeClient({ baseUrl: options.baseUrl });
  const report = await buildCommentScout({ client, options });
  if (options.json) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.log(renderMarkdown(report));
  }
}

export {
  buildCommentScout,
  commentsFromResponse,
  escapeMarkdown,
  normalizeComment,
  normalizeVideo,
  parseArgs,
  renderMarkdown,
  scoreOpportunity,
  videosFromResponse,
};

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(`Error: ${error.message}`);
    process.exit(1);
  });
}
