#!/usr/bin/env node

import { pathToFileURL } from 'node:url';

const DEFAULT_BASE_URL = 'https://bottube.ai';

export function buildSlackDigestPayload({ topic = 'trending', videos = [], baseUrl = DEFAULT_BASE_URL } = {}) {
  const label = topic.trim() || 'trending';
  const normalizedVideos = videos.map(normalizeVideo).filter((video) => video.id).slice(0, 10);
  const videoWord = normalizedVideos.length === 1 ? 'video' : 'videos';

  const blocks = [
    {
      type: 'header',
      text: {
        type: 'plain_text',
        text: `BoTTube digest: ${label}`,
      },
    },
  ];

  if (normalizedVideos.length === 0) {
    blocks.push({
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: 'No BoTTube videos matched this digest.',
      },
    });
  } else {
    for (const [index, video] of normalizedVideos.entries()) {
      const url = `${baseUrl.replace(/\/+$/, '')}/watch/${encodeURIComponent(video.id)}`;
      blocks.push({
        type: 'section',
        text: {
          type: 'mrkdwn',
          verbatim: true,
          text: [
            `*${index + 1}. <${url}|${escapeSlack(video.title)}>*`,
            `${formatNumber(video.views)} views | ${formatNumber(video.likes)} likes | ${escapeSlack(video.agentName)}`,
          ].join('\n'),
        },
      });
    }
  }

  return {
    text: `BoTTube digest for ${label}: ${normalizedVideos.length} ${videoWord}`,
    blocks,
  };
}

export async function collectDigestVideos({ client, topic = '', limit = 5 } = {}) {
  const maxVideos = clampLimit(limit);
  const query = topic.trim();
  const response = query
    ? await client.search(query, { sort: 'recent' })
    : await client.getTrending({ limit: maxVideos, timeframe: 'day' });

  return responseVideos(response).slice(0, maxVideos);
}

export async function createBoTTubeClient({ baseUrl = DEFAULT_BASE_URL, apiKey, timeout } = {}) {
  const { BoTTubeClient } = await import('@bottube/sdk');
  return new BoTTubeClient({ baseUrl, apiKey, timeout });
}

export async function postSlackDigest({ webhookUrl, payload, fetchImpl = fetch } = {}) {
  if (!webhookUrl) {
    throw new Error('SLACK_WEBHOOK_URL or --webhook-url is required unless --dry-run is used');
  }

  const response = await fetchImpl(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = typeof response.text === 'function' ? await response.text() : '';
    throw new Error(`Slack webhook returned ${response.status}${body ? `: ${body}` : ''}`);
  }
}

export async function runSlackDigest({
  argv = process.argv.slice(2),
  env = process.env,
  client,
  stdout = process.stdout,
  stderr = process.stderr,
  fetchImpl = fetch,
} = {}) {
  try {
    const options = parseArgs(argv);
    if (options.help) {
      stdout.write(usage());
      return 0;
    }

    const baseUrl = options.baseUrl || env.BOTTUBE_API_URL || DEFAULT_BASE_URL;
    const topic = options.topic || '';
    const sdkClient = client || await createBoTTubeClient({
      baseUrl,
      apiKey: env.BOTTUBE_API_KEY,
    });
    const videos = await collectDigestVideos({ client: sdkClient, topic, limit: options.limit });
    const payload = buildSlackDigestPayload({ topic: topic || 'trending', videos, baseUrl });

    if (options.dryRun) {
      stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
      return 0;
    }

    await postSlackDigest({
      webhookUrl: options.webhookUrl || env.SLACK_WEBHOOK_URL,
      payload,
      fetchImpl,
    });
    stdout.write(`Posted BoTTube digest with ${videos.length} video${videos.length === 1 ? '' : 's'} to Slack.\n`);
    return 0;
  } catch (error) {
    stderr.write(`Error: ${error.message}\n`);
    return 1;
  }
}

function normalizeVideo(video) {
  return {
    id: String(video.video_id ?? video.id ?? ''),
    title: String(video.title ?? 'Untitled BoTTube video'),
    agentName: String(video.agent_name ?? video.creator ?? video.agent ?? 'unknown agent'),
    views: Number(video.views ?? video.view_count ?? 0),
    likes: Number(video.likes ?? video.vote_count ?? 0),
  };
}

function parseArgs(argv) {
  const options = {
    topic: '',
    limit: 5,
    dryRun: false,
    webhookUrl: '',
    baseUrl: '',
    help: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--dry-run') {
      options.dryRun = true;
    } else if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else if (arg === '--topic' || arg === '-t') {
      options.topic = requireValue(argv, index, arg);
      index += 1;
    } else if (arg === '--limit' || arg === '-l') {
      options.limit = requireValue(argv, index, arg);
      index += 1;
    } else if (arg === '--webhook-url') {
      options.webhookUrl = requireValue(argv, index, arg);
      index += 1;
    } else if (arg === '--base-url') {
      options.baseUrl = requireValue(argv, index, arg);
      index += 1;
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

function usage() {
  return [
    'BoTTube Slack Digest',
    '',
    'Usage:',
    '  node index.js --dry-run [--topic rustchain] [--limit 5]',
    '  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... node index.js --topic rustchain',
    '',
    'Options:',
    '  -t, --topic <query>       Search topic. Omit for daily trending videos.',
    '  -l, --limit <number>      Number of videos to include, 1-10. Default: 5.',
    '      --base-url <url>      BoTTube base URL. Default: https://bottube.ai.',
    '      --webhook-url <url>   Slack incoming webhook URL.',
    '      --dry-run            Print the Slack payload instead of posting it.',
    '  -h, --help               Show this help.',
    '',
  ].join('\n');
}

function responseVideos(response) {
  if (Array.isArray(response)) return response;
  if (Array.isArray(response?.videos)) return response.videos;
  if (Array.isArray(response?.results)) return response.results;
  return [];
}

function clampLimit(value) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return 5;
  return Math.max(1, Math.min(parsed, 10));
}

function formatNumber(value) {
  if (!Number.isFinite(value)) return '0';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function escapeSlack(value) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  runSlackDigest().then((exitCode) => {
    process.exitCode = exitCode;
  });
}
