const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(
  path.join(__dirname, '..', '..', 'bottube_templates', 'embed_guide.html'),
  'utf8'
);
const start = template.indexOf('function setVideo');
const end = template.indexOf('function copyCode', start);
assert.ok(start >= 0 && end > start, 'preview selection behavior is present');

function pickerButton(title) {
  const attributes = new Map([['aria-pressed', 'false']]);
  const classes = new Set();
  return {
    textContent: title,
    classList: {
      contains(name) { return classes.has(name); },
      toggle(name, force) { force ? classes.add(name) : classes.delete(name); },
    },
    getAttribute(name) { return attributes.get(name); },
    setAttribute(name, value) { attributes.set(name, value); },
  };
}

const first = pickerButton(' First video ');
const second = pickerButton('Second video');
const iframe = { src: '', title: '' };
const demo = { style: { display: 'none' } };
const codeText = { innerHTML: '' };
const output = { style: { display: 'none' } };
const sandbox = {
  document: {
    getElementById(id) {
      return {
        'embed-iframe': iframe,
        'embed-demo': demo,
        'embed-code-text': codeText,
        'embed-code-output': output,
      }[id];
    },
    querySelectorAll(selector) {
      assert.equal(selector, '.video-picker button');
      return [first, second];
    },
  },
};
vm.createContext(sandbox);
vm.runInContext(template.slice(start, end), sandbox);

sandbox.setVideo('video-1', first);
assert.equal(first.getAttribute('aria-pressed'), 'true');
assert.equal(second.getAttribute('aria-pressed'), 'false');
assert.equal(first.classList.contains('active'), true);
assert.equal(iframe.src, 'https://bottube.ai/embed/video-1');
assert.equal(iframe.title, 'BoTTube video preview: First video');

sandbox.setVideo('video-2', second);
assert.equal(first.getAttribute('aria-pressed'), 'false');
assert.equal(second.getAttribute('aria-pressed'), 'true');
assert.equal(first.classList.contains('active'), false);
assert.equal(second.classList.contains('active'), true);
assert.equal(iframe.title, 'BoTTube video preview: Second video');
assert.equal(demo.style.display, 'block');
assert.equal(output.style.display, 'block');
