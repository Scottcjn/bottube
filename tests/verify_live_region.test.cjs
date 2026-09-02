const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');

const template = fs.readFileSync(
  path.join(__dirname, '..', 'bottube_templates', 'verify.html'),
  'utf8'
);
const script = template.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(script, 'verification behavior is present');

function makeRow() {
  const parts = {
    '.ico': { className: '', textContent: '' },
    '.title': { textContent: '' },
    '.detail': { textContent: '' },
  };
  return {
    className: '',
    innerHTML: '',
    querySelector(selector) { return parts[selector]; },
    parts,
  };
}

const steps = {
  children: [],
  appendChild(row) { this.children.push(row); },
  set innerHTML(value) {
    if (value === '') this.children = [];
  },
};
const verdict = { className: '', innerHTML: '', textContent: '' };
const output = { style: { display: 'none' } };
const input = { value: 'bad!' };
const verifyButton = { disabled: false };
const assetButton = { disabled: false };
const elements = {
  'vrf-steps': steps,
  'vrf-verdict': verdict,
  'vrf-out': output,
  'vrf-vid': input,
  'vrf-btn': verifyButton,
  'vrf-asset-btn': assetButton,
};
const sandbox = {
  crypto: webcrypto,
  document: {
    createElement() { return makeRow(); },
    getElementById(id) { return elements[id]; },
  },
  TextEncoder,
  URLSearchParams,
  Uint8Array,
  window: { location: { search: '' } },
};
vm.createContext(sandbox);
vm.runInContext(script[1], sandbox);

(async () => {
  await sandbox.window.runVerify(false);
  assert.equal(output.style.display, 'block');
  assert.equal(steps.children.length, 1);
  assert.equal(steps.children[0].parts['.title'].textContent, 'Validate input');
  assert.match(steps.children[0].parts['.detail'].textContent, /video_id must be/);
  assert.equal(verdict.className, 'vrf-verdict fail');
  assert.equal(verdict.textContent, 'FAIL');
  assert.equal(verifyButton.disabled, false);
  assert.equal(assetButton.disabled, false);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
