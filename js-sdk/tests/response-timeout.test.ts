import { afterEach, describe, expect, it, vi } from 'vitest';
import { File } from 'node:buffer';
import { BoTTubeClient } from '../src/client';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('response body deadlines', () => {
  it.each([
    ['json', 200], ['multipart', 200], ['json', 503], ['multipart', 503],
  ])('times out a stalled %s response with status %s after headers arrive', async (kind, status) => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn(async (_url, options) => ({
      ok: status === 200,
      status,
      json: () => new Promise((_resolve, reject) => {
        options.signal.addEventListener('abort', () => {
          reject(new DOMException('Body read aborted', 'AbortError'));
        }, { once: true });
      }),
    })));
    const client = new BoTTubeClient({ timeout: 100 });
    const operation = kind === 'json'
      ? client.health()
      : client.upload(new File(['clip'], 'clip.mp4'), { title: 'Clip' });
    let outcome: unknown;
    operation.then(value => { outcome = value; }, error => { outcome = error; });

    await vi.advanceTimersByTimeAsync(100);
    expect(outcome).toMatchObject({ name: 'BoTTubeError', statusCode: 408 });
    expect(vi.getTimerCount()).toBe(0);
  });

  it('allows a body that completes within the deadline', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: () => new Promise(resolve => setTimeout(() => resolve({ status: 'ok' }), 25)),
    })));
    const operation = new BoTTubeClient({ timeout: 100 }).health();
    await vi.advanceTimersByTimeAsync(25);
    await expect(operation).resolves.toEqual({ status: 'ok' });
    expect(vi.getTimerCount()).toBe(0);
  });

  it('cleans up the deadline after a body decoding error', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => { throw new SyntaxError('Invalid JSON'); },
    })));
    await expect(new BoTTubeClient({ timeout: 100 }).health()).rejects.toThrow(SyntaxError);
    expect(vi.getTimerCount()).toBe(0);
  });
});
