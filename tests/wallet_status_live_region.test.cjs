const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(
  path.join(__dirname, '..', 'bottube_templates', 'settings_wallet.html'),
  'utf8'
);
const start = template.indexOf('function setText');
const end = template.indexOf('async function refreshLocalWalletUI', start);
assert.ok(start >= 0 && end > start, 'shared wallet status writer is present');

const elements = {
  'linked-wallet-result': { textContent: '', style: {} },
  'local-wallet-status': { textContent: '', style: {} },
  'local-wallet-result': { textContent: '', style: {} },
};
const sandbox = {
  document: { getElementById(id) { return elements[id] || null; } },
};
vm.createContext(sandbox);
vm.runInContext(template.slice(start, end), sandbox);

for (const id of Object.keys(elements)) {
  sandbox.setText(id, `${id} updated`, 'var(--green)');
  assert.equal(elements[id].textContent, `${id} updated`);
  assert.equal(elements[id].style.color, 'var(--green)');
}

assert.doesNotThrow(() => sandbox.setText('missing-status', 'ignored'));
