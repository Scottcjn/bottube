import assert from 'node:assert/strict';
import test from 'node:test';

import { buildSlackDigestPayload, collectDigestVideos, runSlackDigest } from '../index.js';

test('builds a Slack Block Kit payload with BoTTube video links', () => {
  const payload = buildSlackDigestPayload({
    topic: 'rustchain',
    videos: [
      {
        video_id: 'vid_rustchain',
        title: 'RustChain miner walkthrough',
        agent_name: 'miner-agent',
        views: 1234,
        likes: 12,
      },
      {
        id: 'vid_sdk',
        title: 'BoTTube SDK release notes',
        agent_name: 'sdk-agent',
        view_count: 98,
        vote_count: 3,
      },
    ],
  });

  assert.equal(payload.text, 'BoTTube digest for rustchain: 2 videos');
  assert.equal(payload.blocks[0].type, 'header');
  assert.match(payload.blocks[0].text.text, /BoTTube digest: rustchain/);
  assert.match(payload.blocks[1].text.text, /<https:\/\/bottube.ai\/watch\/vid_rustchain\|RustChain miner walkthrough>/);
  assert.match(payload.blocks[1].text.text, /1.2K views/);
  assert.match(payload.blocks[2].text.text, /<https:\/\/bottube.ai\/watch\/vid_sdk\|BoTTube SDK release notes>/);
});

test('escapes Slack mrkdwn fields and encodes watch URLs', () => {
  const payload = buildSlackDigestPayload({
    topic: 'security',
    videos: [
      {
        video_id: 'id with spaces/and/slashes',
        title: 'Watch <this> & ping @channel',
        agent_name: 'agent <ops> & friends',
      },
    ],
  });

  assert.match(payload.blocks[1].text.text, /watch\/id%20with%20spaces%2Fand%2Fslashes/);
  assert.match(payload.blocks[1].text.text, /Watch &lt;this&gt; &amp; ping @channel/);
  assert.match(payload.blocks[1].text.text, /agent &lt;ops&gt; &amp; friends/);
  assert.equal(payload.blocks[1].text.verbatim, true);
});

test('collects topic videos through the BoTTube SDK client', async () => {
  const calls = [];
  const client = {
    async search(query, options) {
      calls.push({ query, options });
      return {
        videos: [
          { video_id: 'vid_1', title: 'First' },
          { video_id: 'vid_2', title: 'Second' },
          { video_id: 'vid_3', title: 'Third' },
        ],
      };
    },
  };

  const videos = await collectDigestVideos({ client, topic: 'rustchain', limit: 2 });

  assert.deepEqual(calls, [{ query: 'rustchain', options: { sort: 'recent' } }]);
  assert.deepEqual(videos.map((video) => video.video_id), ['vid_1', 'vid_2']);
});

test('dry-run prints the Slack payload without calling a webhook', async () => {
  const stdout = [];
  const client = {
    async search() {
      return {
        videos: [{ video_id: 'vid_1', title: 'RustChain briefing', views: 1000, likes: 4 }],
      };
    },
  };

  const exitCode = await runSlackDigest({
    argv: ['--topic', 'rustchain', '--limit', '1', '--dry-run'],
    env: {},
    client,
    stdout: { write: (chunk) => stdout.push(chunk) },
    stderr: { write: () => {} },
    fetchImpl: async () => {
      throw new Error('webhook should not be called during dry-run');
    },
  });

  const payload = JSON.parse(stdout.join(''));
  assert.equal(exitCode, 0);
  assert.equal(payload.text, 'BoTTube digest for rustchain: 1 video');
  assert.match(payload.blocks[1].text.text, /RustChain briefing/);
});

test('posts the digest JSON to the configured Slack webhook', async () => {
  const stdout = [];
  const posts = [];
  const client = {
    async search() {
      return {
        videos: [{ video_id: 'vid_1', title: 'Webhook briefing', views: 12, likes: 1 }],
      };
    },
  };

  const exitCode = await runSlackDigest({
    argv: ['--topic', 'rustchain', '--webhook-url', 'https://hooks.slack.test/services/demo'],
    env: {},
    client,
    stdout: { write: (chunk) => stdout.push(chunk) },
    stderr: { write: () => {} },
    fetchImpl: async (url, init) => {
      posts.push({ url, init });
      return { ok: true, status: 200, text: async () => 'ok' };
    },
  });

  assert.equal(exitCode, 0);
  assert.equal(posts.length, 1);
  assert.equal(posts[0].url, 'https://hooks.slack.test/services/demo');
  assert.equal(posts[0].init.method, 'POST');
  assert.equal(posts[0].init.headers['Content-Type'], 'application/json');
  assert.equal(JSON.parse(posts[0].init.body).text, 'BoTTube digest for rustchain: 1 video');
  assert.match(stdout.join(''), /Posted BoTTube digest with 1 video to Slack/);
});

test('requires a Slack webhook outside dry-run mode', async () => {
  const stderr = [];
  const client = {
    async search() {
      return { videos: [{ video_id: 'vid_1', title: 'Missing webhook briefing' }] };
    },
  };

  const exitCode = await runSlackDigest({
    argv: ['--topic', 'rustchain'],
    env: {},
    client,
    stdout: { write: () => {} },
    stderr: { write: (chunk) => stderr.push(chunk) },
  });

  assert.equal(exitCode, 1);
  assert.match(stderr.join(''), /SLACK_WEBHOOK_URL or --webhook-url is required/);
});
