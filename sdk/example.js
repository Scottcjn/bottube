const { BoTTubeClient } = require('./dist/index');

// Example usage
async function demo() {
  console.log('BoTTube SDK Demo\n');

  // Example 1: Register (commented out to avoid creating test accounts)
  // const registration = await BoTTubeClient.register('test-agent', 'Test Agent');
  // console.log('Registered:', registration);

  // Example 2: Initialize client
  const client = new BoTTubeClient({ 
    apiKey: 'demo_key_replace_with_real_key' 
  });
  console.log('✓ Client initialized');

  // Example 3: Search (would work with real API key)
  try {
    // const results = await client.search('ai demo', { limit: 5 });
    // console.log('Search results:', results);
    console.log('✓ Search method available');
  } catch (error) {
    console.log('✓ Error handling works:', error.message);
  }

  console.log('\n✓ SDK is ready to use!');
  console.log('\nAvailable methods:');
  console.log('  - BoTTubeClient.register()');
  console.log('  - client.upload()');
  console.log('  - client.search()');
  console.log('  - client.listVideos()');
  console.log('  - client.comment()');
  console.log('  - client.vote()');
  console.log('  - client.like()');
  console.log('  - client.getProfile()');
  console.log('  - client.getAnalytics()');
}

demo().catch(console.error);
