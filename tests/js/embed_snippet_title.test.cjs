const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// The watch page's embed generator, run for real (#2251). The snippet it
// produces is copied onto other people's sites, so its iframe needs an
// accessible name of its own: a screen reader announces frames by name, and an
// unnamed one gives the reader nothing to decide on before entering it.
const template = fs.readFileSync(
  path.join(__dirname, '..', '..', 'bottube_templates', 'watch.html'),
  'utf8'
);
const start = template.indexOf('function escapeEmbedAttribute');
const end = template.indexOf('function copyEmbedCode', start);
assert.ok(start >= 0 && end > start, 'the embed generator is present');

function harness(size) {
  const embedCode = { value: '' };
  const sandbox = {
    videoId: 'GAdSoP9G9Q2',
    videoTitle: '',
    document: {
      getElementById(id) {
        return { 'embed-size': { value: size }, 'embed-code': embedCode }[id];
      },
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(template.slice(start, end), sandbox);
  return { sandbox, embedCode };
}

// A plain title becomes the frame's name, so several BoTTube embeds on one
// page announce as different frames rather than as a row of identical ones.
{
  const { sandbox, embedCode } = harness('853x480');
  sandbox.videoTitle = 'How agents learn';
  sandbox.updateEmbedCode();
  assert.equal(
    embedCode.value,
    '<iframe src="https://bottube.ai/embed/GAdSoP9G9Q2" title="BoTTube video: How agents learn"'
      + ' width="853" height="480" frameborder="0" allowfullscreen></iframe>'
  );
}

// A title is free text. Unescaped, a quote in it would close the attribute and
// the copied snippet would carry whatever followed as markup.
{
  const { sandbox, embedCode } = harness('853x480');
  sandbox.videoTitle = 'He said "hi" & <b>bold</b>';
  sandbox.updateEmbedCode();
  assert.match(
    embedCode.value,
    /title="BoTTube video: He said &quot;hi&quot; &amp; &lt;b&gt;bold&lt;\/b&gt;"/
  );
  assert.ok(!embedCode.value.includes('<b>'), 'the title must not reach the snippet as markup');
}

{
  const { sandbox, embedCode } = harness('853x480');
  sandbox.videoTitle = "'single' quotes";
  sandbox.updateEmbedCode();
  assert.match(embedCode.value, /title="BoTTube video: &#39;single&#39; quotes"/);
}

// No title, whitespace, or a missing variable still names the frame.
for (const absent of ['', '   ', undefined, null]) {
  const { sandbox, embedCode } = harness('853x480');
  sandbox.videoTitle = absent;
  sandbox.updateEmbedCode();
  assert.match(
    embedCode.value,
    /title="BoTTube video"/,
    `a video title of ${JSON.stringify(absent)} must still produce a named frame`
  );
}

// The responsive size keeps its inline style, and the name sits before it.
{
  const { sandbox, embedCode } = harness('100%x480');
  sandbox.videoTitle = 'Responsive';
  sandbox.updateEmbedCode();
  assert.equal(
    embedCode.value,
    '<iframe src="https://bottube.ai/embed/GAdSoP9G9Q2" title="BoTTube video: Responsive"'
      + ' width="100%" height="480" frameborder="0" allowfullscreen'
      + ' style="width:100%;max-width:853px;"></iframe>'
  );
}

console.log('embed snippet title: ok');
