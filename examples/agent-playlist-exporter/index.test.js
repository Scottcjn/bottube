// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  collectCatalog,
  normalizePlaylistDetail,
  normalizeProfile,
  parseArgs,
  parseBaseUrl,
  parseLimit,
  renderM3u,
  renderMarkdown,
} from './index.js';

const exampleRoot = dirname(fileURLToPath(new URL('./index.js', import.meta.url)));

test('parseArgs accepts exporter controls', () => {
  assert.deepEqual(parseArgs([
    '--agent', 'demo-agent',
    '--base-url', 'https://example.test/',
    '--fixture', 'fixture.json',
    '--format', 'm3u',
    '--limit', '3',
    '--output', '/tmp/demo.m3u',
  ]), {
    agent: 'demo-agent',
    baseUrl: 'https://example.test',
    fixture: 'fixture.json',
    format: 'm3u',
    help: false,
    limit: 3,
    output: '/tmp/demo.m3u',
  });
});

test('argument validation rejects malformed limits, formats, and base URLs', () => {
  assert.equal(parseLimit('25'), 25);
  assert.throws(() => parseLimit('2abc'), /integer/);
  assert.throws(() => parseLimit('0'), /integer/);
  assert.throws(() => parseArgs(['--format', 'csv']), /markdown, json, or m3u/);
  assert.throws(() => parseBaseUrl('file:///tmp/data'), /HTTP\(S\)/);
});

test('normalizers accept live SDK wrapper shapes', () => {
  assert.deepEqual(normalizeProfile({
    agent: {
      agent_name: 'demo-agent',
      display_name: 'Demo Agent',
      bio: 'Line one\nline two',
      created_at: 1_700_000_000,
    },
    video_count: '7',
  }, 'fallback'), {
    agent: 'demo-agent',
    displayName: 'Demo Agent',
    bio: 'Line one line two',
    avatarUrl: '',
    createdAt: '2023-11-14T22:13:20.000Z',
    videoCount: 7,
    totalLikes: 0,
    totalViews: 0,
  });

  const detail = normalizePlaylistDetail({
    playlist_id: 'list/id',
    title: 'A list',
    items: [{ video_id: 'video/id', title: 'Video', position: 2, duration_sec: '4.4' }],
  }, { playlistId: 'list/id', title: 'Fallback', visibility: 'public', createdAt: '', updatedAt: '' }, 'https://example.test', {
    getVideoStreamUrl(id) {
      return `https://stream.test/${encodeURIComponent(id)}`;
    },
  });
  assert.equal(detail.playlistUrl, 'https://example.test/playlist/list%2Fid');
  assert.equal(detail.items[0].watchUrl, 'https://example.test/watch/video%2Fid');
  assert.equal(detail.items[0].streamUrl, 'https://stream.test/video%2Fid');
});

test('collectCatalog calls the public SDK playlist workflow', async () => {
  const calls = [];
  const client = {
    async getAgent(agent) {
      calls.push(`agent:${agent}`);
      return { agent: { agent_name: agent, display_name: 'Live Agent' }, video_count: 4 };
    },
    async getAgentPlaylists(agent) {
      calls.push(`lists:${agent}`);
      return { playlists: [{ playlist_id: 'public-one', title: 'Public one', item_count: 1 }] };
    },
    async getPlaylist(id) {
      calls.push(`detail:${id}`);
      return { playlist_id: id, title: 'Public one', items: [{ video_id: 'video-one', title: 'One' }] };
    },
    getVideoStreamUrl(id) {
      return `https://example.test/api/videos/${id}/stream`;
    },
  };

  const catalog = await collectCatalog({
    client,
    options: { agent: 'live-agent', baseUrl: 'https://example.test', limit: 5 },
    now: () => new Date('2026-08-16T00:00:00Z'),
  });

  assert.deepEqual(calls.sort(), ['agent:live-agent', 'detail:public-one', 'lists:live-agent']);
  assert.equal(catalog.generatedAt, '2026-08-16T00:00:00.000Z');
  assert.equal(catalog.playlistCount, 1);
  assert.equal(catalog.videoCount, 1);
  assert.equal(catalog.playlists[0].items[0].videoId, 'video-one');
});

test('fixture mode never calls SDK network methods', async () => {
  const fixture = JSON.parse(await readFile(join(exampleRoot, 'test', 'fixture.json'), 'utf8'));
  const client = {
    async getAgent() {
      throw new Error('unexpected profile request');
    },
    async getAgentPlaylists() {
      throw new Error('unexpected playlist request');
    },
    async getPlaylist() {
      throw new Error('unexpected detail request');
    },
    getVideoStreamUrl(id) {
      return `https://fixture.test/api/videos/${encodeURIComponent(id)}/stream`;
    },
  };

  const catalog = await collectCatalog({
    client,
    options: { agent: 'fixture-agent', baseUrl: 'https://fixture.test', limit: 10 },
    fixtureData: fixture,
  });
  assert.equal(catalog.profile.agent, 'fixture-agent');
  assert.equal(catalog.playlistCount, 1);
  assert.equal(catalog.videoCount, 2);
});

test('Markdown and M3U renderers normalize untrusted API text', () => {
  const catalog = {
    generatedAt: '2026-08-16T00:00:00.000Z',
    baseUrl: 'https://bottube.ai',
    profile: { agent: 'agent', displayName: 'Agent | Name', bio: 'bio\nline', videoCount: 2 },
    playlistCount: 1,
    videoCount: 1,
    playlists: [{
      title: 'List | One',
      description: 'Description\nline',
      visibility: 'public',
      itemCount: 1,
      playlistUrl: 'https://bottube.ai/playlist/list-one',
      items: [{
        position: 1,
        title: 'Video | title\ncontinued',
        agent: 'creator',
        displayName: '',
        durationSeconds: 4.4,
        views: 12,
        watchUrl: 'https://bottube.ai/watch/video-one',
        streamUrl: 'https://bottube.ai/api/videos/video-one/stream',
      }],
    }],
  };

  const markdown = renderMarkdown(catalog);
  assert.ok(markdown.includes('Agent \\| Name'));
  assert.ok(markdown.includes('Video \\| title continued'));
  assert.ok(!markdown.includes('Description\nline'));

  const m3u = renderM3u(catalog);
  assert.match(m3u, /^#EXTM3U/);
  assert.match(m3u, /#EXTINF:4,creator - Video \| title continued/);
  assert.match(m3u, /https:\/\/bottube\.ai\/api\/videos\/video-one\/stream/);
});

test('CLI help and fixture export exit successfully', () => {
  const help = spawnSync(process.execPath, [join(exampleRoot, 'index.js'), '--help'], {
    encoding: 'utf8',
  });
  assert.equal(help.status, 0);
  assert.match(help.stdout, /Agent Playlist Exporter/);

  const run = spawnSync(process.execPath, [
    join(exampleRoot, 'index.js'),
    '--fixture', join(exampleRoot, 'test', 'fixture.json'),
    '--agent', 'fixture-agent',
    '--format', 'json',
  ], { encoding: 'utf8' });
  assert.equal(run.status, 0, run.stderr);
  const result = JSON.parse(run.stdout);
  assert.equal(result.playlistCount, 1);
  assert.equal(result.videoCount, 2);
});
