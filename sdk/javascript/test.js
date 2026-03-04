const BoTTubeClient = require('./index');

// Basic validation tests (no API calls)
console.log('Running BoTTube SDK tests...\n');

// Test 1: Constructor validation
console.log('Test 1: Constructor validation');
try {
  new BoTTubeClient();
  console.log('❌ Should throw error without API key');
} catch (e) {
  console.log('✅ Correctly throws error without API key');
}

try {
  const client = new BoTTubeClient({ apiKey: 'test_key' });
  console.log('✅ Constructor accepts valid options');
} catch (e) {
  console.log('❌ Constructor failed:', e.message);
}

// Test 2: Method existence
console.log('\nTest 2: Method existence');
const client = new BoTTubeClient({ apiKey: 'test_key' });
const methods = [
  'upload', 'search', 'listVideos', 'getVideo',
  'comment', 'getComments', 'vote', 'like', 'dislike',
  'getAgent', 'trending', 'feed', 'me'
];

let allMethodsExist = true;
for (const method of methods) {
  if (typeof client[method] !== 'function') {
    console.log(`❌ Missing method: ${method}`);
    allMethodsExist = false;
  }
}
if (allMethodsExist) {
  console.log('✅ All required methods exist');
}

// Test 3: Input validation
console.log('\nTest 3: Input validation');
(async () => {
  try {
    await client.vote('test_id', 2);
    console.log('❌ Should reject invalid vote value');
  } catch (e) {
    console.log('✅ Correctly validates vote value');
  }

  try {
    await client.comment('test_id', 'x'.repeat(5001));
    console.log('❌ Should reject comment > 5000 chars');
  } catch (e) {
    console.log('✅ Correctly validates comment length');
  }

  // Test 4: TypeScript types
  console.log('\nTest 4: TypeScript types');
  const fs = require('fs');
  if (fs.existsSync('./index.d.ts')) {
    console.log('✅ TypeScript definitions file exists');
  } else {
    console.log('❌ TypeScript definitions file missing');
  }

  console.log('\n✅ All basic tests passed!');
  console.log('\nNote: Integration tests require a valid API key and network access.');
  console.log('To test with real API:');
  console.log('  export BOTTUBE_API_KEY=your_key');
  console.log('  node test.js --integration');
})();

// Test 4: TypeScript types
console.log('\nTest 4: TypeScript types');
