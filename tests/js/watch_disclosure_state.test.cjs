const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(
  path.join(__dirname, '..', '..', 'bottube_templates', 'watch.html'),
  'utf8'
);

function extract(startMarker, endMarker) {
  const start = template.indexOf(startMarker);
  const end = template.indexOf(endMarker, start);
  assert.ok(start >= 0 && end > start, `${startMarker} behavior is present`);
  return template.slice(start, end);
}

function control() {
  const attributes = new Map([['aria-expanded', 'false']]);
  return {
    getAttribute(name) { return attributes.get(name); },
    setAttribute(name, value) { attributes.set(name, value); },
  };
}

const sharePanel = { style: { display: 'none' } };
const embedPanel = { style: { display: 'none' } };
const savePanel = { style: { display: 'none' } };
const openClasses = new Set();
const tipPanel = { classList: {
  toggle(name) {
    if (openClasses.has(name)) {
      openClasses.delete(name);
      return false;
    }
    openClasses.add(name);
    return true;
  },
} };
const controls = {
  'share-btn': control(),
  'embed-toggle-btn': control(),
  'save-btn': control(),
  'tip-toggle-btn': control(),
};
const panels = {
  'share-panel': sharePanel,
  'embed-panel': embedPanel,
  'save-panel': savePanel,
  'tip-panel': tipPanel,
};
let outsideClick;
let playlistLoads = 0;
let embedUpdates = 0;
const sandbox = {
  document: {
    addEventListener(name, callback) {
      if (name === 'click') outsideClick = callback;
    },
    getElementById(id) { return controls[id] || panels[id]; },
  },
  loadMyPlaylists() { playlistLoads += 1; },
  updateEmbedCode() { embedUpdates += 1; },
};
vm.createContext(sandbox);
vm.runInContext(extract('function shareVideo', 'function copyLink'), sandbox);
vm.runInContext(extract('function toggleEmbedPanel', 'function updateEmbedCode'), sandbox);
vm.runInContext(extract('var savePanelOpen', 'function loadMyPlaylists'), sandbox);
vm.runInContext(extract('function toggleTipPanel', 'function selectTipAmount'), sandbox);

sandbox.shareVideo();
assert.equal(sharePanel.style.display, 'block');
assert.equal(controls['share-btn'].getAttribute('aria-expanded'), 'true');
sandbox.shareVideo();
assert.equal(controls['share-btn'].getAttribute('aria-expanded'), 'false');

sandbox.toggleEmbedPanel();
assert.equal(controls['embed-toggle-btn'].getAttribute('aria-expanded'), 'true');
assert.equal(embedUpdates, 1);
sandbox.toggleEmbedPanel();
assert.equal(controls['embed-toggle-btn'].getAttribute('aria-expanded'), 'false');

sandbox.toggleSavePanel({ stopPropagation() {} });
assert.equal(controls['save-btn'].getAttribute('aria-expanded'), 'true');
assert.equal(playlistLoads, 1);
outsideClick();
assert.equal(savePanel.style.display, 'none');
assert.equal(controls['save-btn'].getAttribute('aria-expanded'), 'false');

sandbox.toggleTipPanel();
assert.equal(controls['tip-toggle-btn'].getAttribute('aria-expanded'), 'true');
sandbox.toggleTipPanel();
assert.equal(controls['tip-toggle-btn'].getAttribute('aria-expanded'), 'false');
