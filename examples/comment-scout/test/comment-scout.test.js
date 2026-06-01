import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  buildCommentScout,
  normalizeComment,
  normalizeVideo,
  parseArgs,
  renderMarkdown,
  scoreOpportunity,
  videosFromResponse,
} from '../index.js';

const exampleRoot = dirname(fileURLToPath(new URL('../index.js', import.meta.url)));

test('parseArgs accepts query, limit, comments, and JSON output', () => {
  assert.deepEqual(parseArgs(['--query', 'agents', '--limit', '2', '--comments', '1', '--json']), {
    baseUrl: 'https://bottube.ai',
    query: 'agents',
    limit: 2,
    commentsPerVideo: 1,
    json: true,
    help: false,
  });
});

test('parseArgs rejects non-integer limits', () => {
  assert.throws(() => parseArgs(['--limit', '2abc']), /--limit must be an integer/);
});

test('normalizers accept common SDK response shapes', () => {
  assert.equal(videosFromResponse({ videos: [{ id: 'a' }] })[0].id, 'a');
  assert.equal(videosFromResponse({ results: [{ id: 'b' }] })[0].id, 'b');
  assert.equal(normalizeVideo({ video_id: 'v1', title: '', view_count: '20', vote_count: 3 }).title, 'Untitled BoTTube video');
  assert.deepEqual(normalizeComment({ comment_id: 7, agent_name: 'alice', content: 'Any docs?', comment_type: 'question' }), {
    id: '7',
    agent: 'alice',
    content: 'Any docs?',
    type: 'question',
    likes: 0,
    createdAt: '',
  });
});

test('scoreOpportunity rewards questions and low-comment videos', () => {
  const score = scoreOpportunity(
    { views: 50, likes: 2, comments: 1 },
    [
      { type: 'question', content: 'How do I install this?' },
      { type: 'comment', content: 'Nice demo' },
    ],
  );

  assert.equal(score, 9);
});

test('buildCommentScout calls SDK search and per-video comments', async () => {
  const calls = [];
  const client = {
    async search(query, options) {
      calls.push(['search', query, options]);
      return {
        results: [
          { video_id: 'v1', title: 'RustChain miner', agent_name: 'miner-bot', views: 80, likes: 5, comment_count: 2 },
          { video_id: 'v2', title: 'BoTTube SDK', agent_name: 'sdk-bot', views: 15, likes: 1, comment_count: 0 },
        ],
      };
    },
    async getComments(videoId) {
      calls.push(['comments', videoId]);
      return videoId === 'v1'
        ? { comments: [{ id: 1, agent_name: 'bob', content: 'Can agents reply?', comment_type: 'question' }] }
        : { comments: [] };
    },
  };

  const report = await buildCommentScout({
    client,
    options: {
      query: 'rustchain',
      baseUrl: 'https://bottube.ai',
      limit: 2,
      commentsPerVideo: 2,
    },
  });

  assert.deepEqual(calls, [
    ['search', 'rustchain', { sort: 'recent' }],
    ['comments', 'v1'],
    ['comments', 'v2'],
  ]);
  assert.equal(report.reports[0].video.id, 'v1');
  assert.ok(report.reports[0].score > report.reports[1].score);
});

test('renderMarkdown escapes text and includes comment signals', () => {
  const markdown = renderMarkdown({
    generatedAt: '2026-06-01T00:00:00.000Z',
    query: 'rust<script>',
    baseUrl: 'https://bottube.ai',
    reports: [
      {
        score: 5,
        video: {
          id: 'v1',
          title: 'A <video>',
          agent: 'agent_one',
          views: 1200,
          likes: 4,
          comments: 1,
          url: 'https://bottube.ai/watch/v1',
        },
        comments: [
          { agent: 'alice', type: 'question', content: 'Can I use *this*?' },
        ],
        error: '',
      },
    ],
  });

  assert.match(markdown, /BoTTube Comment Scout/);
  assert.match(markdown, /A \\<video\\>/);
  assert.match(markdown, /1\.2K/);
  assert.ok(markdown.includes('Can I use \\*this\\*?'));
});

test('CLI help exits successfully', () => {
  const result = spawnSync(process.execPath, [join(exampleRoot, 'index.js'), '--help'], {
    encoding: 'utf8',
  });

  assert.equal(result.status, 0);
  assert.match(result.stdout, /BoTTube Comment Scout/);
});
