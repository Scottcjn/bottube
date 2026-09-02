const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(
  path.join(__dirname, '..', '..', 'bottube_templates', 'giveaway.html'),
  'utf8'
);
const start = template.lastIndexOf('(function() {');
const end = template.indexOf('})();', start) + '})();'.length;
assert.notEqual(start, -1, 'countdown IIFE is present');
assert.ok(end > start, 'countdown IIFE is complete');

let now = 1_000_000;
let writes = 0;
const intervals = [];
const cleared = [];
const valueElement = { set textContent(_value) { writes += 1; } };

const sandbox = {
  clearInterval(id) { cleared.push(id); },
  Date: { now() { return now; } },
  document: {
    getElementById(id) {
      if (id === 'countdown') {
        return { dataset: { target: String((now + 5_000) / 1_000) } };
      }
      return valueElement;
    },
  },
  Math,
  parseFloat,
  requestAnimationFrame() {
    throw new Error('countdown must not create an animation-frame loop');
  },
  setInterval(callback, delay) {
    intervals.push({ callback, delay });
    return 17;
  },
};

vm.runInNewContext(template.slice(start, end), sandbox);
assert.equal(writes, 4, 'countdown updates four values immediately');
assert.equal(intervals.length, 1, 'countdown creates one timer');
assert.equal(intervals[0].delay, 1_000, 'countdown updates once per second');

now += 6_000;
intervals[0].callback();
assert.equal(writes, 8, 'one timer tick performs one additional update');
assert.deepEqual(cleared, [17], 'timer is cleared when countdown reaches zero');
assert.equal(intervals.length, 1, 'timer callback does not spawn another timer');
