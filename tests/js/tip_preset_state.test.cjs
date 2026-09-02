const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(
  path.join(__dirname, '..', '..', 'bottube_templates', 'watch.html'),
  'utf8'
);
const start = template.indexOf('function selectTipAmount');
const end = template.indexOf('function sendTip', start);
assert.ok(start >= 0 && end > start, 'tip preset behavior is present');

function preset(label) {
  const classes = new Set();
  const attributes = new Map([['aria-pressed', 'false']]);
  return {
    textContent: label,
    classList: {
      contains(name) { return classes.has(name); },
      remove(name) { classes.delete(name); },
      toggle(name, force) { force ? classes.add(name) : classes.delete(name); },
    },
    getAttribute(name) { return attributes.get(name); },
    setAttribute(name, value) { attributes.set(name, value); },
  };
}

const input = { value: '0.01' };
const presets = [preset('0.01'), preset('0.10'), preset('1.00')];
const sandbox = {
  document: {
    getElementById(id) {
      assert.equal(id, 'tip-amount');
      return input;
    },
    querySelectorAll(selector) {
      assert.equal(selector, '.tip-amount-btn');
      return presets;
    },
  },
  parseFloat,
};
vm.createContext(sandbox);
vm.runInContext(template.slice(start, end), sandbox);

sandbox.selectTipAmount(0.1);
assert.equal(input.value, 0.1);
assert.deepEqual(presets.map((button) => button.getAttribute('aria-pressed')), ['false', 'true', 'false']);
assert.deepEqual(presets.map((button) => button.classList.contains('selected')), [false, true, false]);

input.value = '0.25';
sandbox.clearTipPresetSelection();
assert.deepEqual(presets.map((button) => button.getAttribute('aria-pressed')), ['false', 'false', 'false']);
assert.deepEqual(presets.map((button) => button.classList.contains('selected')), [false, false, false]);
assert.equal(input.value, '0.25', 'clearing stale preset state preserves custom amount');
