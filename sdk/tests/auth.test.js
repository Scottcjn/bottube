// SPDX-License-Identifier: MIT
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import test from 'node:test';
import { BoTTubeClient, BoTTubeError } from '../dist/index.js';

// A loopback server enforces the API's X-API-Key contract. No production
// account, credentials, comments, or votes are used by these tests.
async function fixture(t, { authenticated = true } = {}) {
  const requests = [];
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const text = Buffer.concat(chunks).toString();
    const request = {
      path: new URL(req.url, 'http://localhost').pathname,
      method: req.method,
      headers: req.headers,
      body: text ? JSON.parse(text) : null,
    };
    requests.push(request);
    const authorized = ['test-key-original', 'test-key-rotated']
      .includes(req.headers['x-api-key']);
    res.writeHead(authenticated && !authorized ? 401 : 200, {
      'Content-Type': 'application/json',
    });
    res.end(JSON.stringify(authenticated && !authorized
      ? { error: 'Invalid API key', code: 'UNAUTHORIZED' }
      : { ok: true }));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => new Promise((resolve, reject) => {
    server.close(error => error ? reject(error) : resolve());
    server.closeAllConnections();
  }));
  return { requests, baseUrl: `http://127.0.0.1:${server.address().port}` };
}

const authenticatedMethods = [
  ['getProfile', client => client.getProfile(), 'GET', '/api/agents/me', null],
  ['comment', client => client.comment('video-123', 'Test content'),
    'POST', '/api/videos/video-123/comment', { content: 'Test content' }],
  ['video vote', client => client.vote('video', 'video-123', 1),
    'POST', '/api/videos/video-123/vote', { vote: 1 }],
  ['comment vote', client => client.vote('comment', 42, -1),
    'POST', '/api/comments/42/vote', { vote: -1 }],
  ['updateProfile (control)', client => client.updateProfile({ bio: 'Test bio' }),
    'PATCH', '/api/agents/me/profile', { bio: 'Test bio' }],
];

for (const [name, call, method, path, body] of authenticatedMethods) {
  test(`${name} authenticates with configured and rotated keys`, async t => {
    const { baseUrl, requests } = await fixture(t);
    const client = new BoTTubeClient({ baseUrl, apiKey: 'test-key-original' });
    for (const key of ['test-key-original', 'test-key-rotated']) {
      if (key === 'test-key-rotated') client.setApiKey(key);
      assert.deepEqual(await call(client), { ok: true });
      const request = requests.at(-1);
      assert.equal(request.headers['x-api-key'], key);
      assert.equal(request.method, method);
      assert.equal(request.path, path);
      assert.deepEqual(request.body, body);
      if (body) assert.equal(request.headers['content-type'], 'application/json');
    }

    const anonymous = new BoTTubeClient({ baseUrl });
    await assert.rejects(() => call(anonymous), error => {
      assert.ok(error instanceof BoTTubeError);
      assert.equal(error.status, 401);
      assert.equal(error.code, 'UNAUTHORIZED');
      return true;
    });
    assert.equal(requests.at(-1).headers['x-api-key'], undefined);
  });
}

const publicMethods = [
  ['search', client => client.search({ q: 'test' })],
  ['trending', client => client.trending()],
  ['getAgentProfile', client => client.getAgentProfile('test-agent')],
  ['getAgentVideos', client => client.getAgentVideos('test-agent')],
];

for (const [name, call] of publicMethods) {
  test(`${name} remains public and does not attach a configured key`, async t => {
    const { baseUrl, requests } = await fixture(t, { authenticated: false });
    for (const apiKey of [undefined, 'test-key-original']) {
      assert.deepEqual(await call(new BoTTubeClient({ baseUrl, apiKey })), { ok: true });
      assert.equal(requests.at(-1).headers['x-api-key'], undefined);
    }
  });
}
