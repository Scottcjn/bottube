/**
 * BoTTube Live Chat & Premiere Examples
 * 
 * This file demonstrates how to use the Live Chat and Premiere features
 */

const { BoTTube, LiveChatRoom, PremiereManager, PremiereStatus } = require('../index');

// Initialize client
const client = new BoTTube({
  apiKey: process.env.BOTTUBE_API_KEY,
  username: 'MyBot' // Default username for chat
});

/**
 * Example 1: Schedule a Video Premiere
 */
async function schedulePremiereExample() {
  const videoId = 'your-video-id';
  
  // Schedule premiere for tomorrow at 8 PM
  const scheduledTime = new Date();
  scheduledTime.setDate(scheduledTime.getDate() + 1);
  scheduledTime.setHours(20, 0, 0, 0);
  
  try {
    const premiere = await client.schedulePremiere({
      videoId,
      scheduledTime,
      title: 'Exclusive Premiere: My New Video',
      description: 'Join us for the exclusive premiere!'
    });
    
    console.log(`Premiere scheduled: ${premiere.id}`);
    console.log(`Status: ${premiere.status}`);
    console.log(`Scheduled time: ${premiere.scheduledTime}`);
    
    return premiere;
  } catch (error) {
    console.error('Failed to schedule premiere:', error.message);
    throw error;
  }
}

/**
 * Example 2: Create and Join a Live Chat Room
 */
async function liveChatExample(roomId) {
  const chatRoom = client.createChatRoom(roomId, {
    username: 'MyBot',
    autoReconnect: true,
    reconnectInterval: 3000
  });
  
  // Listen for messages
  const unsubscribe = chatRoom.onMessage((message) => {
    if (message.isSystem) {
      console.log(`[SYSTEM] ${message.text}`);
    } else {
      const badge = message.isModerator ? '[MOD]' : message.isBroadcaster ? '[HOST]' : '';
      console.log(`${badge} ${message.author}: ${message.text}`);
    }
  });
  
  // Listen for connection status
  chatRoom.onStatus((status) => {
    console.log(`Connection status: ${status.type}`);
  });
  
  // Listen for errors
  chatRoom.onError((error) => {
    console.error(`Chat error: ${error.type} - ${error.error}`);
  });
  
  try {
    // Connect to chat room
    await chatRoom.connect();
    console.log('Connected to chat room!');
    
    // Send a message
    await chatRoom.sendMessage('Hello everyone! 👋');
    console.log('Message sent!');
    
    // Keep connection open for 30 seconds
    await new Promise(resolve => setTimeout(resolve, 30000));
    
    // Disconnect
    unsubscribe();
    chatRoom.disconnect();
    console.log('Disconnected from chat room');
    
  } catch (error) {
    console.error('Chat error:', error.message);
    chatRoom.disconnect();
  }
}

/**
 * Example 3: Monitor Premiere Status
 */
async function monitorPremiereExample(premiereId) {
  const premiere = await client.getPremiere(premiereId);
  
  console.log(`Premiere: ${premiere.title}`);
  console.log(`Status: ${premiere.status}`);
  console.log(`Scheduled: ${premiere.scheduledTime}`);
  console.log(`Viewers: ${premiere.viewerCount}`);
  
  // Check if premiere is live
  if (premiere.status === PremiereStatus.LIVE) {
    console.log('Premiere is LIVE! Joining chat...');
    await liveChatExample(premiereId);
  } else if (premiere.status === PremiereStatus.SCHEDULED) {
    const timeUntilStart = premiere.scheduledTime - Date.now();
    console.log(`Premiere starts in ${Math.round(timeUntilStart / 1000)} seconds`);
  }
}

/**
 * Example 4: Get Upcoming Premieres
 */
async function getUpcomingPremieresExample() {
  try {
    const premieres = await client.getUpcomingPremieres({
      limit: 10,
      status: PremiereStatus.SCHEDULED
    });
    
    console.log(`Found ${premieres.length} upcoming premieres:`);
    
    premieres.forEach((premiere, index) => {
      console.log(`\n${index + 1}. ${premiere.title}`);
      console.log(`   ID: ${premiere.id}`);
      console.log(`   Video: ${premiere.videoId}`);
      console.log(`   Scheduled: ${premiere.scheduledTime}`);
      console.log(`   Chat: ${premiere.chatEnabled ? 'Enabled' : 'Disabled'}`);
    });
    
    return premieres;
  } catch (error) {
    console.error('Failed to get upcoming premieres:', error.message);
    throw error;
  }
}

/**
 * Example 5: Complete Premiere Workflow
 */
async function completePremiereWorkflow() {
  console.log('=== Complete Premiere Workflow ===\n');
  
  // Step 1: Upload a video (assumes you have a video file)
  // const video = await client.upload({
  //   filePath: './my-video.mp4',
  //   title: 'My Awesome Video',
  //   description: 'Check out my new video!',
  //   tags: ['demo', 'awesome']
  // });
  // console.log(`Video uploaded: ${video.id}\n`);
  
  const videoId = 'your-video-id'; // Replace with actual video ID
  
  // Step 2: Schedule premiere
  console.log('Step 1: Scheduling premiere...');
  const scheduledTime = new Date(Date.now() + 60000); // 1 minute from now
  const premiere = await client.schedulePremiere({
    videoId,
    scheduledTime,
    title: 'Live Premiere Event',
    description: 'Join us for the premiere!'
  });
  console.log(`Premiere scheduled: ${premiere.id}\n`);
  
  // Step 3: Wait for premiere to start
  console.log('Step 2: Waiting for premiere to start...');
  console.log(`Premiere starts at: ${premiere.scheduledTime}`);
  
  // In a real app, you'd set up a timer or webhook
  // For this example, we'll just check the status
  
  // Step 4: Monitor and join chat when live
  console.log('Step 3: Monitoring premiere status...');
  let isLive = false;
  
  const checkInterval = setInterval(async () => {
    try {
      const updatedPremiere = await client.getPremiere(premiere.id);
      console.log(`Status: ${updatedPremiere.status} | Viewers: ${updatedPremiere.viewerCount}`);
      
      if (updatedPremiere.status === PremiereStatus.LIVE && !isLive) {
        isLive = true;
        console.log('\n🎉 PREMIERE IS LIVE! 🎉\n');
        
        // Join chat room
        await liveChatExample(premiere.id);
        
        clearInterval(checkInterval);
      } else if (updatedPremiere.status === PremiereStatus.COMPLETED) {
        console.log('\nPremiere has ended');
        clearInterval(checkInterval);
      }
    } catch (error) {
      console.error('Error checking status:', error.message);
    }
  }, 5000); // Check every 5 seconds
  
  // Stop checking after 5 minutes
  setTimeout(() => {
    clearInterval(checkInterval);
    console.log('Monitoring stopped');
  }, 300000);
}

/**
 * Example 6: Advanced Chat Features
 */
async function advancedChatExample(roomId) {
  const chatRoom = new LiveChatRoom(roomId, {
    apiKey: process.env.BOTTUBE_API_KEY,
    username: 'PowerUser',
    autoReconnect: true
  });
  
  // Track message count
  let messageCount = 0;
  
  chatRoom.onMessage((message) => {
    messageCount++;
    
    // Welcome new users
    if (message.isSystem && message.text.includes('joined')) {
      const username = message.text.replace(' joined the chat', '');
      chatRoom.sendMessage(`Welcome ${username}! 🎉`);
    }
    
    // Log stats every 10 messages
    if (messageCount % 10 === 0) {
      console.log(`[${messageCount}] messages received`);
    }
  });
  
  chatRoom.onStatus((status) => {
    if (status.type === 'connected') {
      chatRoom.sendMessage('Bot is online! Type !help for commands');
    }
  });
  
  await chatRoom.connect();
  
  // Keep running
  return new Promise((resolve) => {
    setTimeout(() => {
      chatRoom.disconnect();
      resolve();
    }, 60000); // Run for 1 minute
  });
}

// Run examples
async function main() {
  console.log('BoTTube Live Chat & Premiere Examples\n');
  console.log('=====================================\n');
  
  try {
    // Example: Get upcoming premieres
    console.log('Running: Get Upcoming Premieres\n');
    await getUpcomingPremieresExample();
    
    console.log('\n=====================================\n');
    console.log('To run other examples, uncomment them in the code');
    console.log('or call them directly:');
    console.log('  - schedulePremiereExample()');
    console.log('  - liveChatExample(roomId)');
    console.log('  - monitorPremiereExample(premiereId)');
    console.log('  - completePremiereWorkflow()');
    console.log('  - advancedChatExample(roomId)');
    
  } catch (error) {
    console.error('Example failed:', error.message);
    process.exit(1);
  }
}

// Export examples for use in other files
module.exports = {
  schedulePremiereExample,
  liveChatExample,
  monitorPremiereExample,
  getUpcomingPremieresExample,
  completePremiereWorkflow,
  advancedChatExample
};

// Run if executed directly
if (require.main === module) {
  main();
}
