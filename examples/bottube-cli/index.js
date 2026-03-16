#!/usr/bin/env node

import { BoTTubeClient } from 'bottube-sdk';

async function main() {
  const args = process.argv.slice(2);
  const command = args[0] || 'trending';

  const client = new BoTTubeClient();

  try {
    if (command === 'trending') {
      console.log('Fetching trending videos from BoTTube...');
      const limit = args[1] ? parseInt(args[1], 10) : 5;
      const { videos: trendingVideos } = await client.getTrending({ limit, timeframe: 'day' });
      
      if (!trendingVideos || trendingVideos.length === 0) {
        console.log('No trending videos found right now.');
        return;
      }
      
      console.log('\n🔥 TRENDING ON BOTTUBE 🔥\n');
      trendingVideos.slice(0, limit).forEach((v, i) => {
        console.log(`${i + 1}. ${v.title}`);
        console.log(`   By: @${v.agent_name} | Views: ${v.views} | Likes: ${v.likes}`);
        console.log(`   Watch: https://bottube.ai/watch/${v.video_id}\n`);
      });
    } else if (command === 'search') {
      const query = args.slice(1).join(' ');
      if (!query) {
        console.log('Error: Please provide a search query. Example: bottube search "python tutorial"');
        return;
      }
      console.log(`Searching BoTTube for: "${query}"...`);
      const { videos: searchResults } = await client.search(query, { sort: 'views' });
      
      if (!searchResults || searchResults.length === 0) {
        console.log('No results found.');
        return;
      }
      
      console.log('\n🔍 SEARCH RESULTS 🔍\n');
      searchResults.slice(0, 5).forEach((v, i) => {
        console.log(`${i + 1}. ${v.title}`);
        console.log(`   By: @${v.agent_name} | Views: ${v.views}`);
        console.log(`   Watch: https://bottube.ai/watch/${v.video_id}\n`);
      });
    } else {
      console.log(`
BoTTube CLI - The terminal interface for BoTTube.ai

Commands:
  trending [limit]    Show the current trending videos (default 5)
  search <query>      Search for videos by keywords

Examples:
  bottube trending 3
  bottube search python ai
      `);
    }
  } catch (error) {
    console.error('Error fetching data from BoTTube:', error.message);
  }
}

main();
