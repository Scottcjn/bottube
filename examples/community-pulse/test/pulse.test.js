import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import {
  buildPulseReport,
  normalizeLimit,
  renderJson,
  renderMarkdown
} from '../src/pulse.js';

const execFileAsync = promisify(execFile);
const root = fileURLToPath(new URL('..', import.meta.url));

test('normalizeLimit rejects malformed numeric input', () => {
  assert.equal(normalizeLimit('3', '--comments', 1, 10), 3);
  assert.throws(() => normalizeLimit('3abc', '--comments', 1, 10), /--comments must be an integer/);
  assert.throws(() => normalizeLimit('0', '--comments', 1, 10), /--comments must be an integer/);
  assert.throws(() => normalizeLimit('11', '--comments', 1, 10), /--comments must be an integer/);
});

test('buildPulseReport ranks commenters, videos, and comment types', () => {
  const report = buildPulseReport({
    comments: [
      { id: 1, video_id: 'v1', agent_name: 'alice', comment_type: 'question', content: 'First' },
      { id: 2, video_id: 'v1', agent_name: 'bob', comment_type: 'answer', content: 'Second' },
      { id: 3, video_id: 'v2', agent_name: 'alice', comment_type: 'comment', content: 'Third' }
    ],
    videos: [
      { video_id: 'v1', title: 'Intro', agent_name: 'maker', views: 5, likes: 2 }
    ]
  }, {
    generatedAt: '2026-05-23T20:00:00.000Z',
    baseUrl: 'https://bottube.ai'
  });

  assert.deepEqual(report.totals, {
    comments: 3,
    videos: 1,
    agents: 2,
    videosWithComments: 2
  });
  assert.deepEqual(report.topAgents[0], { name: 'alice', count: 2 });
  assert.deepEqual(report.topCommentedVideos[0], { name: 'v1', count: 2 });
  assert.equal(report.latestVideos[0].watchUrl, 'https://bottube.ai/watch/v1');
});

test('renderMarkdown escapes table-breaking content', () => {
  const report = buildPulseReport({
    comments: [
      {
        video_id: 'v|1',
        agent_name: 'agent\nname',
        comment_type: 'comment',
        content: 'pipe | and newline\nstay in one row'
      }
    ],
    videos: []
  }, { generatedAt: '2026-05-23T20:00:00.000Z' });

  const markdown = renderMarkdown(report);
  assert.match(markdown, /agent name/);
  assert.match(markdown, /pipe \\| and newline stay in one row/);
  assert.doesNotMatch(markdown, /newline\nstay/);
});

test('renderJson emits parseable report output', () => {
  const report = buildPulseReport({ comments: [], videos: [] }, {
    generatedAt: '2026-05-23T20:00:00.000Z'
  });
  assert.deepEqual(JSON.parse(renderJson(report)).totals, report.totals);
});

test('CLI renders fixture data and writes markdown', async () => {
  const outFile = join(tmpdir(), 'bottube-community-pulse.md');
  await rm(outFile, { force: true });

  const { stdout } = await execFileAsync(process.execPath, [
    'index.js',
    '--fixture',
    'test/fixtures/pulse.json',
    '--generated-at',
    '2026-05-23T20:00:00.000Z',
    '--out',
    outFile
  ], { cwd: root });

  assert.match(stdout, /Wrote BoTTube community pulse report/);
  const markdown = await readFile(outFile, 'utf8');
  assert.match(markdown, /# BoTTube Community Pulse/);
  assert.match(markdown, /atlas\\-bot \(2\)/);
  assert.match(markdown, /RustChain miner setup/);
  await rm(outFile, { force: true });
});
