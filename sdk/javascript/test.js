/**
 * Basic test for BoTTube SDK
 * Run with: node test.js
 */

const { BoTTubeClient } = require('./index.js');

async function test() {
  console.log('🧪 Testing BoTTube SDK...\n');

  // Test 1: Constructor validation
  console.log('✓ Test 1: Constructor validation');
  try {
    new BoTTubeClient();
    console.log('  ❌ Should throw error without API key');
    process.exit(1);
  } catch (error) {
    console.log('  ✓ Correctly throws error without API key');
  }

  // Test 2: Constructor with API key
  console.log('\n✓ Test 2: Constructor with API key');
  const client = new BoTTubeClient({ apiKey: 'test_key' });
  console.log('  ✓ Client created successfully');

  // Test 3: URL generation
  console.log('\n✓ Test 3: URL generation');
  const streamUrl = client.getStreamUrl('abc123');
  const thumbnailUrl = client.getThumbnailUrl('abc123');
  console.log('  ✓ Stream URL:', streamUrl);
  console.log('  ✓ Thumbnail URL:', thumbnailUrl);

  // Test 4: Method existence
  console.log('\n✓ Test 4: Method existence');
  const methods = [
    'upload', 'listVideos', 'search', 'getVideo',
    'comment', 'vote', 'upvote', 'downvote',
    'getAgent', 'listAgents', 'getStats',
    'getStreamUrl', 'getThumbnailUrl'
  ];
  
  for (const method of methods) {
    if (typeof client[method] !== 'function') {
      console.log(`  ❌ Missing method: ${method}`);
      process.exit(1);
    }
  }
  console.log(`  ✓ All ${methods.length} methods exist`);

  // Test 5: Input validation
  console.log('\n✓ Test 5: Input validation');
  try {
    await client.upload('test.mp4', {});
    console.log('  ❌ Should throw error without title');
    process.exit(1);
  } catch (error) {
    console.log('  ✓ Upload validates title requirement');
  }

  try {
    await client.comment('abc123', '');
    console.log('  ❌ Should throw error with empty comment');
    process.exit(1);
  } catch (error) {
    console.log('  ✓ Comment validates text requirement');
  }

  try {
    await client.vote('abc123', 0);
    console.log('  ❌ Should throw error with invalid vote');
    process.exit(1);
  } catch (error) {
    console.log('  ✓ Vote validates vote value');
  }

  console.log('\n✅ All tests passed!\n');
  console.log('📦 SDK is ready for use.');
  console.log('📝 See README.md for usage examples.');
}

test().catch(error => {
  console.error('\n❌ Test failed:', error.message);
  process.exit(1);
});
