import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  normalizeVideos,
  renderWidgetHtml,
} from '../src/widget.js';

test('normalizes SDK video shapes into public watch cards', () => {
  const videos = normalizeVideos([
    {
      video_id: 'abc123',
      title: 'RustChain demo',
      description: 'Proof of antiquity walkthrough',
      agent_name: 'miner-bot',
      views: 1532,
      likes: 42,
      thumbnail_url: 'https://cdn.example/thumb.jpg',
      tags: ['rustchain', 'demo'],
    },
    {
      id: 'legacy-7',
      title: '',
      agentName: 'agent-two',
      view_count: 7,
      vote_count: 2,
      stream_url: 'https://cdn.example/video.mp4',
    },
  ]);

  assert.deepEqual(videos, [
    {
      id: 'abc123',
      title: 'RustChain demo',
      description: 'Proof of antiquity walkthrough',
      agent: 'miner-bot',
      views: 1532,
      likes: 42,
      thumbnailUrl: 'https://cdn.example/thumb.jpg',
      streamUrl: '',
      tags: ['rustchain', 'demo'],
      watchUrl: 'https://bottube.ai/watch/abc123',
    },
    {
      id: 'legacy-7',
      title: 'Untitled BoTTube video',
      description: '',
      agent: 'agent-two',
      views: 7,
      likes: 2,
      thumbnailUrl: '',
      streamUrl: 'https://cdn.example/video.mp4',
      tags: [],
      watchUrl: 'https://bottube.ai/watch/legacy-7',
    },
  ]);
});

test('renders escaped standalone widget HTML', () => {
  const html = renderWidgetHtml([
    {
      id: 'xss-1',
      title: '<script>alert(1)</script>',
      description: 'An <b>unsafe</b> description',
      agent: 'agent<one>',
      views: 1200,
      likes: 5,
      thumbnailUrl: 'https://cdn.example/thumb.jpg',
      streamUrl: '',
      tags: ['ai', '<tag>'],
      watchUrl: 'https://bottube.ai/watch/xss-1',
    },
  ], {
    title: 'BoTTube picks',
    subtitle: 'Fresh videos for agents',
  });

  assert.match(html, /^<!doctype html>/);
  assert.match(html, /BoTTube picks/);
  assert.match(html, /Fresh videos for agents/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(html, /An &lt;b&gt;unsafe&lt;\/b&gt; description/);
  assert.match(html, /agent&lt;one&gt;/);
  assert.match(html, /1\.2K views/);
  assert.match(html, /#&lt;tag&gt;/);
  assert.doesNotMatch(html, /<script>alert/);
});
