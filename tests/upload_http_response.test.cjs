const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(
  path.join(__dirname, '..', 'bottube_templates', 'upload.html'),
  'utf8'
);
const blockStart = template.indexOf('{% if not current_user %}');
const scriptStart = template.indexOf('<script>', blockStart) + '<script>'.length;
const scriptEnd = template.indexOf('</script>', scriptStart);
assert.ok(blockStart >= 0 && scriptStart > blockStart && scriptEnd > scriptStart);
const script = template.slice(scriptStart, scriptEnd);

async function settle() {
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
}

async function exercise(fetchImpl) {
  let submitHandler;
  const alerts = [];
  const button = { textContent: 'Upload Video', disabled: false };
  const apiKey = { value: 'bottube_sk_test' };
  const form = {
    querySelector(selector) {
      assert.equal(selector, 'input[type="file"]');
      return { files: [] };
    },
  };
  const sandbox = {
    alert(message) { alerts.push(message); },
    document: {
      querySelector(selector) {
        assert.equal(selector, '.upload-form');
        return {
          addEventListener(name, handler) {
            assert.equal(name, 'submit');
            submitHandler = handler;
          },
        };
      },
      getElementById(id) {
        return id === 'apiKeyInput' ? apiKey : button;
      },
    },
    fetch: fetchImpl,
    FormData: class {
      constructor(value) { assert.equal(value, form); }
      delete() {}
    },
    JSON,
    window: { location: { href: '' } },
  };
  vm.createContext(sandbox);
  vm.runInContext(script, sandbox);
  assert.equal(typeof submitHandler, 'function');

  submitHandler({ preventDefault() {}, target: form });
  await settle();
  return { alerts, button, location: sandbox.window.location };
}

(async () => {
  let result = await exercise(() => Promise.resolve({
    ok: true,
    status: 201,
    json: () => Promise.resolve({ ok: true, watch_url: '/watch/video-1' }),
  }));
  assert.equal(result.location.href, '{{ P }}/watch/video-1');
  assert.deepEqual(result.alerts, []);

  result = await exercise(() => Promise.resolve({
    ok: false,
    status: 400,
    json: () => Promise.resolve({ error: 'Unsupported file type' }),
  }));
  assert.deepEqual(result.alerts, ['Upload failed: Unsupported file type']);
  assert.equal(result.button.disabled, false);
  assert.equal(result.button.textContent, 'Upload Video');

  result = await exercise(() => Promise.resolve({
    ok: false,
    status: 413,
    json: () => Promise.reject(new SyntaxError('Unexpected token <')),
  }));
  assert.deepEqual(result.alerts, ['Upload failed: HTTP 413']);
  assert.equal(result.button.disabled, false);
  assert.equal(result.button.textContent, 'Upload Video');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
