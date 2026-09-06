import assert from 'node:assert/strict';
import test from 'node:test';
import { buildManifest, mergePages, normalizeVideo, renderMarkdown } from '../lib.js';

test('normalizeVideo emits stable watch and stream URLs', () => {
  const result = normalizeVideo({ video_id: 'abc 123', title: 'Title', tags: ['one'], views: 2 }, 'https://bottube.ai/');
  assert.equal(result.watch_url, 'https://bottube.ai/watch/abc%20123');
  assert.equal(result.stream_url, 'https://bottube.ai/api/videos/abc%20123/stream');
  assert.deepEqual(result.tags, ['one']);
});

test('mergePages de-duplicates video ids and honors SDK stream URL callback', () => {
  const pages = [
    { videos: [{ video_id: 'a', title: 'A' }, { video_id: 'b', title: 'B' }] },
    { videos: [{ video_id: 'a', title: 'A duplicate' }, { video_id: 'c', title: 'C' }] },
  ];
  const videos = mergePages(pages, 'https://example.test', (id) => `sdk://${id}`);
  assert.deepEqual(videos.map((v) => v.video_id), ['a', 'b', 'c']);
  assert.equal(videos[0].stream_url, 'sdk://a');
});

test('manifest and Markdown report are deterministic with fixed timestamp', () => {
  const videos = [normalizeVideo({ video_id: 'abc', title: 'A *title*', agent_name: 'bot', tags: ['x'], views: 3 })];
  const manifest = buildManifest(videos, { generatedAt: '2026-08-30T08:00:00.000Z', pagesRequested: 2 });
  assert.equal(manifest.schema, 'bottube.video-archive-manifest.v1');
  assert.equal(manifest.video_count, 1);
  const md = renderMarkdown(manifest);
  assert.match(md, /BoTTube Video Archive Manifest/);
  assert.match(md, /A \\?\*title\\?\*/);
  assert.match(md, /https:\/\/bottube\.ai\/watch\/abc/);
});
