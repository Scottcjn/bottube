const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(
  path.join(__dirname, '..', 'bottube_templates', 'report.html'),
  'utf8'
);
const script = template.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(script, 'report behavior is present');

function classList() {
  const tokens = new Set();
  return {
    add(...names) { names.forEach((name) => tokens.add(name)); },
    remove(...names) { names.forEach((name) => tokens.delete(name)); },
    contains(name) { return tokens.has(name); },
  };
}

function createSandbox(fetchImpl) {
  const elements = {
    'r-submit': { disabled: false, textContent: 'Submit report' },
    'r-toast': { classList: classList() },
    'r-toast-message': { textContent: '' },
    'r-ref': { textContent: '' },
    'r-category': { value: 'spam' },
    'r-target': { value: 'video-1' },
    'r-detail': { value: 'Repeated promotion' },
    'r-email': { value: '' },
    'report-form': { resetCount: 0, reset() { this.resetCount += 1; } },
  };
  const sandbox = {
    document: { getElementById(id) { return elements[id]; } },
    fetch: fetchImpl,
    JSON,
  };
  vm.createContext(sandbox);
  vm.runInContext(script[1], sandbox);
  return { sandbox, elements };
}

async function settle() {
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
}

(async () => {
  let current = createSandbox(() => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ ok: true, report_id: 'rep-42' }),
  }));
  current.sandbox.submitReport({ preventDefault() {} });
  await settle();
  assert.equal(current.elements['r-ref'].textContent, 'rep-42');
  assert.equal(current.elements['r-toast'].classList.contains('show'), true);
  assert.equal(current.elements['r-toast'].classList.contains('error'), false);
  assert.equal(current.elements['report-form'].resetCount, 1);
  assert.equal(current.elements['r-submit'].disabled, false);

  current = createSandbox(() => Promise.resolve({
    ok: false,
    json: () => Promise.resolve({ error: 'Invalid target' }),
  }));
  current.sandbox.submitReport({ preventDefault() {} });
  await settle();
  assert.equal(current.elements['r-toast-message'].textContent, 'Invalid target');
  assert.equal(current.elements['r-toast'].classList.contains('show'), true);
  assert.equal(current.elements['r-toast'].classList.contains('error'), true);
  assert.equal(current.elements['r-ref'].textContent, '');

  current = createSandbox(() => Promise.reject(new Error('offline')));
  current.sandbox.submitReport({ preventDefault() {} });
  await settle();
  assert.match(current.elements['r-toast-message'].textContent, /Network error/);
  assert.equal(current.elements['r-toast'].classList.contains('show'), true);
  assert.equal(current.elements['r-toast'].classList.contains('error'), true);
  assert.equal(current.elements['r-submit'].disabled, false);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
