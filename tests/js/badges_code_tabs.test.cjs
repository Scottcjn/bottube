const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(
  path.join(__dirname, '..', '..', 'bottube_templates', 'badges.html'),
  'utf8'
);
const start = template.indexOf('function showTab');
const end = template.indexOf('function copyCode', start);
assert.ok(start >= 0 && end > start, 'tab behavior is present');

function element(id) {
  const attributes = new Map();
  const classes = new Set();
  return {
    id,
    attributes,
    classList: {
      contains(name) { return classes.has(name); },
      toggle(name, force) { force ? classes.add(name) : classes.delete(name); },
    },
    focusCalls: 0,
    focus() { this.focusCalls += 1; },
    getAttribute(name) { return attributes.get(name); },
    setAttribute(name, value) { attributes.set(name, value); },
    tabIndex: -1,
  };
}

const markdown = element('vid-md-tab');
const html = element('vid-html-tab');
markdown.setAttribute('aria-controls', 'vid-md');
html.setAttribute('aria-controls', 'vid-html');
const markdownPanel = element('vid-md');
const htmlPanel = element('vid-html');
const tabs = [markdown, html];
const panels = [markdownPanel, htmlPanel];
const card = {
  querySelectorAll(selector) {
    if (selector === '.code-tab') return tabs;
    if (selector === '.code-panel') return panels;
    throw new Error(`unexpected selector: ${selector}`);
  },
};
const tablist = { querySelectorAll(selector) {
  assert.equal(selector, '.code-tab');
  return tabs;
} };
for (const tab of tabs) {
  tab.closest = (selector) => {
    assert.equal(selector, '.badge-card');
    return card;
  };
  tab.parentElement = tablist;
}

const sandbox = { Array };
vm.createContext(sandbox);
vm.runInContext(template.slice(start, end), sandbox);

sandbox.showTab(html, 'vid-html');
assert.equal(markdown.getAttribute('aria-selected'), 'false');
assert.equal(markdown.tabIndex, -1);
assert.equal(markdownPanel.hidden, true);
assert.equal(html.getAttribute('aria-selected'), 'true');
assert.equal(html.tabIndex, 0);
assert.equal(htmlPanel.hidden, false);

let prevented = 0;
sandbox.handleCodeTabKeydown({
  currentTarget: html,
  key: 'ArrowRight',
  preventDefault() { prevented += 1; },
});
assert.equal(prevented, 1);
assert.equal(markdown.focusCalls, 1, 'ArrowRight wraps within this card');
assert.equal(markdown.getAttribute('aria-selected'), 'true');
assert.equal(markdownPanel.hidden, false);
assert.equal(html.getAttribute('aria-selected'), 'false');
assert.equal(htmlPanel.hidden, true);

sandbox.handleCodeTabKeydown({
  currentTarget: markdown,
  key: 'End',
  preventDefault() { prevented += 1; },
});
assert.equal(html.focusCalls, 1, 'End selects the last tab in this card');
assert.equal(html.getAttribute('aria-selected'), 'true');
