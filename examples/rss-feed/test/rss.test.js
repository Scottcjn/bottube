import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { promisify } from 'node:util';
import { extractVideos, generateRss } from '../src/rss.js';

const execFileAsync = promisify(execFile);

function exampleRootFromMetaUrl(metaUrl) {
  return fileURLToPath(new URL('..', metaUrl));
}

const root = exampleRootFromMetaUrl(import.meta.url);

test('exampleRootFromMetaUrl decodes file URLs for child process cwd', () => {
  const encodedMetaUrl = pathToFileURL(
    join(tmpdir(), 'bottube rss', 'examples', 'rss-feed', 'test', 'rss.test.js')
  ).href;
  const decodedRoot = exampleRootFromMetaUrl(encodedMetaUrl);

  assert.equal(decodedRoot.includes('%20'), false);
  assert.match(decodedRoot, /bottube rss/);
});

test('generateRss escapes XML and emits watch links', () => {
  const xml = generateRss({
    title: 'BoTTube <Trending>',
    description: 'AI & agent videos',
    siteUrl: 'https://bottube.ai',
    feedUrl: 'https://example.com/bottube.xml',
    videos: [
      {
        id: 'video-1',
        title: 'RustChain & "Agents"',
        description: 'Preserve <old> machines ]]> safely',
        creator: 'alice',
        created_at: '2026-05-17T10:00:00Z'
      }
    ]
  });

  assert.match(xml, /^<\?xml version="1.0" encoding="UTF-8"\?>/);
  assert.match(xml, /<title>BoTTube &lt;Trending&gt;<\/title>/);
  assert.match(xml, /<title>RustChain &amp; &quot;Agents&quot;<\/title>/);
  assert.match(xml, /<description><!\[CDATA\[Preserve <old> machines \]\]\]\]><!\[CDATA\[> safely\]\]><\/description>/);
  assert.match(xml, /<link>https:\/\/bottube\.ai\/watch\/video-1<\/link>/);
  assert.match(xml, /<guid isPermaLink="true">https:\/\/bottube\.ai\/watch\/video-1<\/guid>/);
});

test('extractVideos accepts SDK response shapes and respects limit', () => {
  assert.deepEqual(
    extractVideos({ videos: [{ id: 1 }, { id: 2 }, { id: 3 }] }, 2).map((video) => video.id),
    [1, 2]
  );
  assert.deepEqual(
    extractVideos({ results: [{ id: 'a' }] }, 10).map((video) => video.id),
    ['a']
  );
  assert.deepEqual(
    extractVideos([{ id: 'direct' }], 10).map((video) => video.id),
    ['direct']
  );
});

test('generateRss treats numeric timestamps as Unix seconds', () => {
  const xml = generateRss({
    siteUrl: 'https://bottube.ai',
    videos: [
      {
        video_id: 'GRMIiChn-UM',
        watch_url: '/watch/GRMIiChn-UM',
        title: 'SDK timestamp sample',
        created_at: 1778940440.082385
      }
    ]
  });

  assert.match(xml, /<link>https:\/\/bottube\.ai\/watch\/GRMIiChn-UM<\/link>/);
  assert.match(xml, /<pubDate>Sat, 16 May 2026 14:07:20 GMT<\/pubDate>/);
});

test('CLI renders fixture data and writes an RSS file', async () => {
  const outFile = join(root, 'test', 'tmp-feed.xml');
  await rm(outFile, { force: true });

  const { stdout } = await execFileAsync(process.execPath, [
    'index.js',
    '--fixture',
    'test/fixtures/videos.json',
    '--out',
    outFile,
    '--title',
    'Fixture Feed'
  ], { cwd: root });

  assert.match(stdout, /Wrote 2 videos to/);
  const xml = await readFile(outFile, 'utf8');
  assert.match(xml, /<title>Fixture Feed<\/title>/);
  assert.match(xml, /<title>Antique GPU Miner Tour<\/title>/);
  assert.match(xml, /<title>BoTTube SDK Demo<\/title>/);
  await rm(outFile, { force: true });
});
