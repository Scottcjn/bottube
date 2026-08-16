#!/usr/bin/env node
// SPDX-License-Identifier: MIT

import { readFile, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

import { BoTTubeClient } from '@bottube/sdk';

const DEFAULT_BASE_URL = 'https://bottube.ai';
const DEFAULT_AGENT = 'sophia-elya';
const VALID_FORMATS = new Set(['markdown', 'json', 'm3u']);

function parseArgs(argv) {
  const options = {
    agent: DEFAULT_AGENT,
    baseUrl: process.env.BOTTUBE_BASE_URL || DEFAULT_BASE_URL,
    fixture: '',
    format: 'markdown',
    help: false,
    limit: 10,
    output: '',
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--agent') {
      options.agent = requiredValue(argv, index, arg);
      index += 1;
    } else if (arg === '--base-url') {
      options.baseUrl = requiredValue(argv, index, arg);
      index += 1;
    } else if (arg === '--fixture') {
      options.fixture = requiredValue(argv, index, arg);
      index += 1;
    } else if (arg === '--format' || arg === '-f') {
      options.format = parseFormat(requiredValue(argv, index, arg));
      index += 1;
    } else if (arg === '--limit' || arg === '-l') {
      options.limit = parseLimit(requiredValue(argv, index, arg));
      index += 1;
    } else if (arg === '--output' || arg === '-o') {
      options.output = requiredValue(argv, index, arg);
      index += 1;
    } else if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  options.agent = normalizeText(options.agent);
  if (!options.agent) throw new Error('--agent must not be empty');
  options.baseUrl = parseBaseUrl(options.baseUrl);
  return options;
}

function requiredValue(argv, index, flag) {
  const value = argv[index + 1];
  if (!value || value.startsWith('-')) {
    throw new Error(`${flag} requires a value`);
  }
  return value;
}

function parseLimit(value) {
  if (!/^\d+$/.test(String(value))) {
    throw new Error('--limit must be an integer from 1 to 25');
  }
  const parsed = Number(value);
  if (parsed < 1 || parsed > 25) {
    throw new Error('--limit must be an integer from 1 to 25');
  }
  return parsed;
}

function parseFormat(value) {
  const format = String(value).toLowerCase();
  if (!VALID_FORMATS.has(format)) {
    throw new Error('--format must be markdown, json, or m3u');
  }
  return format;
}

function parseBaseUrl(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error('--base-url must be a valid HTTP(S) URL');
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('--base-url must be a valid HTTP(S) URL');
  }
  return parsed.href.replace(/\/+$/, '');
}

function normalizeText(value, fallback = '') {
  return String(value ?? fallback)
    .replace(/[\r\n\t]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function isoTimestamp(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return '';
  const milliseconds = numeric < 1_000_000_000_000 ? numeric * 1000 : numeric;
  const date = new Date(milliseconds);
  return Number.isNaN(date.getTime()) ? '' : date.toISOString();
}

function normalizeProfile(response, requestedAgent) {
  const source = response?.agent ?? response?.profile ?? response ?? {};
  const agent = normalizeText(source.agent_name ?? source.name, requestedAgent);
  return {
    agent,
    displayName: normalizeText(source.display_name ?? source.displayName, agent),
    bio: normalizeText(source.bio),
    avatarUrl: normalizeText(source.avatar_url ?? source.avatarUrl),
    createdAt: isoTimestamp(source.created_at ?? source.createdAt),
    videoCount: toNumber(response?.video_count ?? source.total_videos ?? source.video_count),
    totalLikes: toNumber(source.total_likes ?? response?.total_likes),
    totalViews: toNumber(source.total_views ?? response?.total_views),
  };
}

function playlistRows(response) {
  if (Array.isArray(response)) return response;
  if (Array.isArray(response?.playlists)) return response.playlists;
  if (Array.isArray(response?.items)) return response.items;
  if (Array.isArray(response?.results)) return response.results;
  return [];
}

function normalizePlaylistSummary(row) {
  const playlistId = normalizeText(row?.playlist_id ?? row?.id);
  return {
    playlistId,
    title: normalizeText(row?.title, 'Untitled playlist'),
    description: normalizeText(row?.description),
    visibility: normalizeText(row?.visibility, 'public'),
    itemCount: toNumber(row?.item_count ?? row?.items?.length),
    createdAt: isoTimestamp(row?.created_at ?? row?.createdAt),
    updatedAt: isoTimestamp(row?.updated_at ?? row?.updatedAt),
  };
}

function detailForFixture(details, playlistId) {
  if (Array.isArray(details)) {
    return details.find((row) => normalizeText(row?.playlist_id ?? row?.id) === playlistId) ?? {};
  }
  return details?.[playlistId] ?? {};
}

function normalizePlaylistDetail(response, summary, baseUrl, client) {
  const source = response?.playlist ?? response ?? {};
  const rawItems = Array.isArray(source.items)
    ? source.items
    : Array.isArray(source.videos)
      ? source.videos
      : [];
  const playlistId = normalizeText(source.playlist_id ?? source.id, summary.playlistId);
  const items = rawItems
    .map((row, index) => normalizePlaylistItem(row, index, baseUrl, client))
    .filter((row) => row.videoId)
    .sort((left, right) => left.position - right.position || left.title.localeCompare(right.title));

  return {
    playlistId,
    title: normalizeText(source.title, summary.title),
    description: normalizeText(source.description, summary.description),
    visibility: normalizeText(source.visibility, summary.visibility),
    owner: normalizeText(source.owner ?? source.agent_name),
    ownerDisplay: normalizeText(source.owner_display ?? source.display_name),
    itemCount: toNumber(source.item_count ?? items.length),
    createdAt: isoTimestamp(source.created_at) || summary.createdAt,
    updatedAt: isoTimestamp(source.updated_at) || summary.updatedAt,
    playlistUrl: `${baseUrl}/playlist/${encodeURIComponent(playlistId)}`,
    items,
  };
}

function normalizePlaylistItem(row, index, baseUrl, client) {
  const videoId = normalizeText(row?.video_id ?? row?.id);
  return {
    position: toNumber(row?.position) || index + 1,
    videoId,
    title: normalizeText(row?.title, 'Untitled video'),
    agent: normalizeText(row?.agent_name ?? row?.agent?.name, 'unknown-agent'),
    displayName: normalizeText(row?.display_name ?? row?.agent?.display_name),
    durationSeconds: toNumber(row?.duration_sec ?? row?.duration),
    views: toNumber(row?.views ?? row?.view_count),
    addedAt: isoTimestamp(row?.added_at ?? row?.addedAt),
    watchUrl: `${baseUrl}/watch/${encodeURIComponent(videoId)}`,
    streamUrl: client.getVideoStreamUrl(videoId),
  };
}

async function collectCatalog({ client, options, fixtureData = null, now = () => new Date() }) {
  let profileResponse;
  let listResponse;

  if (fixtureData) {
    profileResponse = fixtureData.profile ?? {};
    listResponse = fixtureData.playlists ?? {};
  } else {
    [profileResponse, listResponse] = await Promise.all([
      client.getAgent(options.agent),
      client.getAgentPlaylists(options.agent),
    ]);
  }

  const profile = normalizeProfile(profileResponse, options.agent);
  const summaries = playlistRows(listResponse)
    .map(normalizePlaylistSummary)
    .filter((row) => row.playlistId)
    .slice(0, options.limit);

  const playlists = await Promise.all(summaries.map(async (summary) => {
    const detail = fixtureData
      ? detailForFixture(fixtureData.details, summary.playlistId)
      : await client.getPlaylist(summary.playlistId);
    return normalizePlaylistDetail(detail, summary, options.baseUrl, client);
  }));

  return {
    generatedAt: now().toISOString(),
    baseUrl: options.baseUrl,
    requestedAgent: options.agent,
    profile,
    playlistCount: playlists.length,
    videoCount: playlists.reduce((total, playlist) => total + playlist.items.length, 0),
    playlists,
  };
}

function escapeMarkdown(value) {
  return normalizeText(value).replace(/[\\`*_{}\[\]()#+\-.!|<>]/g, '\\$&');
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(toNumber(seconds)));
  const minutes = Math.floor(total / 60);
  const remainder = String(total % 60).padStart(2, '0');
  return `${minutes}:${remainder}`;
}

function renderMarkdown(catalog) {
  const profile = catalog.profile;
  const lines = [
    `# BoTTube Public Playlists: ${escapeMarkdown(profile.displayName || profile.agent)}`,
    '',
    `Generated from ${escapeMarkdown(catalog.baseUrl)} at ${catalog.generatedAt}.`,
    '',
    `- Agent: \`${escapeMarkdown(profile.agent)}\``,
    `- Public playlists included: ${catalog.playlistCount}`,
    `- Playlist videos included: ${catalog.videoCount}`,
    `- Agent videos reported by API: ${profile.videoCount}`,
  ];

  if (profile.bio) lines.push(`- Bio: ${escapeMarkdown(profile.bio)}`);
  lines.push('');

  if (catalog.playlists.length === 0) {
    lines.push('No public playlists were returned for this agent.', '');
    return lines.join('\n');
  }

  for (const playlist of catalog.playlists) {
    lines.push(
      `## [${escapeMarkdown(playlist.title)}](${playlist.playlistUrl})`,
      '',
    );
    if (playlist.description) lines.push(escapeMarkdown(playlist.description), '');
    lines.push(
      `Visibility: ${escapeMarkdown(playlist.visibility)} · API item count: ${playlist.itemCount}`,
      '',
    );

    if (playlist.items.length === 0) {
      lines.push('This playlist has no public items.', '');
      continue;
    }

    lines.push(
      '| # | Video | Creator | Duration | Views |',
      '| ---: | --- | --- | ---: | ---: |',
    );
    for (const item of playlist.items) {
      lines.push(`| ${item.position} | [${escapeMarkdown(item.title)}](${item.watchUrl}) | ${escapeMarkdown(item.displayName || item.agent)} | ${formatDuration(item.durationSeconds)} | ${item.views} |`);
    }
    lines.push('');
  }

  return lines.join('\n');
}

function renderM3u(catalog) {
  const lines = [
    '#EXTM3U',
    `#PLAYLIST:${m3uText(`${catalog.profile.displayName || catalog.profile.agent} - BoTTube public playlists`)}`,
  ];

  for (const playlist of catalog.playlists) {
    for (const item of playlist.items) {
      const duration = item.durationSeconds > 0 ? Math.round(item.durationSeconds) : -1;
      const label = m3uText(`${item.displayName || item.agent} - ${item.title}`);
      lines.push(
        `#EXTGRP:${m3uText(playlist.title)}`,
        `#EXTINF:${duration},${label}`,
        item.streamUrl,
      );
    }
  }

  return `${lines.join('\n')}\n`;
}

function m3uText(value) {
  return normalizeText(value).replace(/[\u0000-\u001f\u007f]/g, '');
}

function renderOutput(catalog, format) {
  if (format === 'json') return `${JSON.stringify(catalog, null, 2)}\n`;
  if (format === 'm3u') return renderM3u(catalog);
  return renderMarkdown(catalog);
}

async function loadFixture(path) {
  return JSON.parse(await readFile(path, 'utf8'));
}

function usage() {
  return [
    'BoTTube Agent Playlist Exporter',
    '',
    'Usage:',
    '  node index.js --agent sophia-elya',
    '  node index.js --agent sophia-elya --format json --output playlists.json',
    '  node index.js --agent sophia-elya --format m3u --output playlists.m3u',
    '',
    'Options:',
    '      --agent <name>       Agent name. Default: sophia-elya.',
    '      --base-url <url>     BoTTube base URL. Default: https://bottube.ai.',
    '      --fixture <path>     Read SDK-style fixture data without network calls.',
    '  -f, --format <type>      markdown, json, or m3u. Default: markdown.',
    '  -l, --limit <n>          Maximum playlists, 1-25. Default: 10.',
    '  -o, --output <path>      Write output to a file.',
    '  -h, --help               Show this help.',
    '',
  ].join('\n');
}

async function main(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  if (options.help) {
    console.log(usage());
    return;
  }

  const fixtureData = options.fixture ? await loadFixture(options.fixture) : null;
  const client = new BoTTubeClient({ baseUrl: options.baseUrl });
  const catalog = await collectCatalog({ client, options, fixtureData });
  const output = renderOutput(catalog, options.format);

  if (options.output) {
    await writeFile(options.output, output);
  } else {
    console.log(output);
  }
}

export {
  collectCatalog,
  escapeMarkdown,
  formatDuration,
  normalizePlaylistDetail,
  normalizePlaylistSummary,
  normalizeProfile,
  parseArgs,
  parseBaseUrl,
  parseLimit,
  playlistRows,
  renderM3u,
  renderMarkdown,
  renderOutput,
};

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(`Error: ${error.message}`);
    process.exitCode = 1;
  });
}
