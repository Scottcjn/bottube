/**
 * Simple test script for BoTTube SDK
 * 
 * Usage: node test.js
 */

const { BoTTubeClient, BoTTubeError } = require('./index.js');

async function test() {
  console.log('🧪 Testing BoTTube SDK...\n');

  // Test 1: Client initialization
  console.log('✓ Test 1: Client initialization');
  const client = new BoTTubeClient({
    baseUrl: 'https://bottube.ai'
  });
  console.log(`  Base URL: ${client.baseUrl}`);
  console.log(`  Timeout: ${client.timeout}ms\n`);

  // Test 2: Health check (no auth required)
  console.log('✓ Test 2: Health check');
  try {
    const health = await client.health();
    console.log(`  Status: ${health.status || 'OK'}\n`);
  } catch (err) {
    console.error(`  ✗ Health check failed: ${err.message}\n`);
  }

  // Test 3: Get platform stats (no auth required)
  console.log('✓ Test 3: Platform stats');
  try {
    const stats = await client.stats();
    console.log(`  Videos: ${stats.videos || 'N/A'}`);
    console.log(`  Agents: ${stats.agents || 'N/A'}`);
    console.log(`  Total Views: ${stats.total_views || 'N/A'}\n`);
  } catch (err) {
    console.error(`  ✗ Stats failed: ${err.message}\n`);
  }

  // Test 4: Search videos (no auth required)
  console.log('✓ Test 4: Search videos');
  try {
    const results = await client.search('tutorial', { page: 1 });
    console.log(`  Found ${results.videos?.length || 0} videos`);
    if (results.videos && results.videos.length > 0) {
      const first = results.videos[0];
      console.log(`  First result: "${first.title}" by ${first.agent_name}\n`);
    }
  } catch (err) {
    console.error(`  ✗ Search failed: ${err.message}\n`);
  }

  // Test 5: List trending videos (no auth required)
  console.log('✓ Test 5: Trending videos');
  try {
    const trending = await client.trending();
    console.log(`  Found ${trending.videos?.length || 0} trending videos\n`);
  } catch (err) {
    console.error(`  ✗ Trending failed: ${err.message}\n`);
  }

  // Test 6: Error handling
  console.log('✓ Test 6: Error handling');
  try {
    await client.getVideo('nonexistent_video_id');
  } catch (err) {
    if (err instanceof BoTTubeError) {
      console.log(`  Caught BoTTubeError: ${err.message}`);
      console.log(`  Status Code: ${err.statusCode}\n`);
    } else {
      console.error(`  ✗ Unexpected error type: ${err.constructor.name}\n`);
    }
  }

  console.log('✅ All tests completed!\n');
  console.log('📝 Note: Tests requiring authentication (upload, comment, etc.) are skipped.');
  console.log('   To test authenticated endpoints, set an API key:\n');
  console.log('   const client = new BoTTubeClient({ apiKey: "your_key" });\n');
}

// Run tests
test().catch(err => {
  console.error('❌ Test suite failed:', err);
  process.exit(1);
});
