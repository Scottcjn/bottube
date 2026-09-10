import { afterEach, describe, expect, it, vi } from 'vitest';
import { File } from 'node:buffer';
import { BoTTubeClient } from '../src/client';

afterEach(() => vi.unstubAllGlobals());

function captureUpload() {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })));
  vi.stubGlobal('fetch', fetchMock);
  return {
    client: new BoTTubeClient(),
    fetchMock,
    uploadedFile: () => (fetchMock.mock.calls[0][1].body as FormData).get('video') as File,
  };
}

describe('Blob upload filenames', () => {
  it.each([
    ['video/mp4', 'video.mp4'],
    ['video/webm', 'video.webm'],
    ['video/webm;codecs=vp9', 'video.webm'],
    ['video/quicktime', 'video.mov'],
    ['video/x-matroska', 'video.mkv'],
    ['video/x-msvideo', 'video.avi'],
  ])('gives %s blobs a filename accepted by the upload endpoint', async (type, filename) => {
    const { client, uploadedFile } = captureUpload();
    const video = new Blob(['video bytes'], { type });
    await client.upload(video, { title: 'Clip' });
    expect(uploadedFile().name).toBe(filename);
    expect(uploadedFile().type).toBe(type);
    expect(await uploadedFile().text()).toBe('video bytes');
  });

  it('preserves the original name of a browser File', async () => {
    const { client, uploadedFile } = captureUpload();
    await client.upload(new File(['clip'], 'recording.webm'), { title: 'Clip' });
    expect(uploadedFile().name).toBe('recording.webm');
  });

  it('accepts an explicit filename when a Blob has no media type', async () => {
    const { client, uploadedFile } = captureUpload();
    await client.upload(new Blob(['clip']), { title: 'Clip', filename: 'capture.mkv' });
    expect(uploadedFile().name).toBe('capture.mkv');
  });

  it('explains how to name a Blob with an unsupported or absent media type', async () => {
    const { client, fetchMock } = captureUpload();
    await expect(client.upload(new Blob(['clip']), { title: 'Clip' }))
      .rejects.toThrow('filename');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
