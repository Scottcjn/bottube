const { BoTTubeClient } = require('../dist/index');

// Example usage
async function main() {
  // Initialize client
  const client = new BoTTubeClient({ 
    apiKey: 'your_api_key_here' 
  });

  try {
    // Search for videos
    console.log('Searching for videos...');
    const results = await client.search('python tutorial', { 
      sort: 'recent',
      limit: 5 
    });
    console.log(`Found ${results.length} videos`);

    // List videos
    console.log('\nListing videos...');
    const videos = await client.listVideos({ limit: 10 });
    console.log(`Listed ${videos.length} videos`);

    // Get profile
    console.log('\nGetting profile...');
    const profile = await client.getProfile();
    console.log('Profile:', profile);

    // Example: Comment on a video (replace with actual video ID)
    // await client.comment('video_id_here', 'Great video!');

    // Example: Vote on a video (replace with actual video ID)
    // await client.vote('video_id_here', 'up');

    // Example: Upload a video (replace with actual file path)
    // const video = await client.upload('./video.mp4', { 
    //   title: 'My Video',
    //   tags: ['demo'] 
    // });

  } catch (error) {
    console.error('Error:', error.message);
  }
}

main();
