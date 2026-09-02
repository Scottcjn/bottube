const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(
  path.join(__dirname, '..', '..', 'bottube_templates', 'badges.html'),
  'utf8'
);
const start = template.indexOf('function copyCode');
const end = template.indexOf('document.addEventListener', start);
assert.ok(start >= 0 && end > start, 'copy behavior is present');

const clipboardWrites = [];
const timers = [];
const clearedTimers = [];
const btn = { textContent: 'Copy', _copyResetTimer: undefined };
const snippet = '<a href="https://bottube.ai">badge</a>';
btn.parentElement = {
  cloneNode() {
    let controlRemoved = false;
    return {
      querySelectorAll(selector) {
        assert.equal(selector, '.copy-btn');
        return [{ remove() { controlRemoved = true; } }];
      },
      get textContent() {
        return `${controlRemoved ? '' : btn.textContent}${snippet}`;
      },
    };
  },
};

const sandbox = {
  clearTimeout(id) { clearedTimers.push(id); },
  navigator: {
    clipboard: {
      writeText(value) {
        clipboardWrites.push(value);
        return Promise.resolve();
      },
    },
  },
  Promise,
  setTimeout(callback, delay) {
    const id = timers.length + 1;
    timers.push({ callback, delay, id });
    return id;
  },
};
vm.createContext(sandbox);
vm.runInContext(template.slice(start, end), sandbox);

async function run() {
  sandbox.copyCode(btn);
  await Promise.resolve();
  assert.equal(btn.textContent, 'Copied!');

  sandbox.copyCode(btn);
  await Promise.resolve();

  assert.deepEqual(clipboardWrites, [snippet, snippet]);
  assert.deepEqual(clearedTimers, [1]);
  assert.equal(timers.length, 2);
  assert.equal(timers[1].delay, 1500);
  timers[1].callback();
  assert.equal(btn.textContent, 'Copy');
  assert.equal(btn._copyResetTimer, undefined);

  const embedTemplate = fs.readFileSync(
    path.join(__dirname, '..', '..', 'bottube_templates', 'embed_guide.html'),
    'utf8'
  );
  const embedStart = embedTemplate.indexOf('function copyCode');
  const embedEnd = embedTemplate.indexOf('document.addEventListener', embedStart);
  const embedWrites = [];
  const embedButton = { textContent: 'Copied!', _copyResetTimer: undefined };
  embedButton.parentElement = {
    cloneNode() {
      let controlRemoved = false;
      return {
        querySelectorAll() { return [{ remove() { controlRemoved = true; } }]; },
        get textContent() { return `${controlRemoved ? '' : embedButton.textContent}${snippet}`; },
      };
    },
  };
  const embedSandbox = {
    clearTimeout() {},
    document: {
      createElement() {
        return {
          set innerHTML(value) { this.value = value; },
          value: '',
        };
      },
    },
    navigator: { clipboard: { writeText(value) { embedWrites.push(value); return Promise.resolve(); } } },
    Promise,
    setTimeout() { return 1; },
  };
  vm.createContext(embedSandbox);
  vm.runInContext(embedTemplate.slice(embedStart, embedEnd), embedSandbox);
  embedSandbox.copyCode(embedButton);
  embedSandbox.copyCode(embedButton);
  await Promise.resolve();
  assert.deepEqual(embedWrites, [snippet, snippet]);
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
