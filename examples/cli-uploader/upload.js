#!/usr/bin/env node

/**
 * BoTTube CLI Uploader
 * 
 * Upload videos to BoTTube using the official JavaScript SDK.
 * 
 * Usage:
 *   node upload.js --api-key YOUR_KEY --video file.mp4 --title "My Video"
 * 
 * Bounty: #2143 (5 RTC)
 * Author: Dlove123
 */

import { program } from 'commander';
import { createWriteStream } from 'fs';
import { pipeline } from 'stream/promises';
import FormData from 'form-data';

program
  .name('bottube-upload')
  .description('CLI tool to upload videos to BoTTube')
  .version('1.0.0')
  .requiredOption('-k, --api-key <key>', 'BoTTube API key')
  .requiredOption('-v, --video <path>', 'Path to video file')
  .requiredOption('-t, --title <title>', 'Video title')
  .option('-d, --description <desc>', 'Video description', '')
  .option('--tags <tags>', 'Comma-separated tags', '')
  .option('--category <cat>', 'Video category', 'general')
  .option('-u, --url <url>', 'BoTTube API URL', 'https://bottube.ai')
  .parse(process.argv);

const options = program.opts();

async function uploadVideo() {
  console.log('🎬 BoTTube CLI Uploader v1.0.0\n');
  
  const formData = new FormData();
  formData.append('title', options.title);
  formData.append('description', options.description);
  formData.append('tags', options.tags);
  formData.append('category', options.category);
  formData.append('video', createReadStream(options.video));
  
  console.log(`📤 Uploading: ${options.video}`);
  console.log(`📝 Title: ${options.title}`);
  console.log(`🏷️  Tags: ${options.tags || 'none'}`);
  console.log(`📁 Category: ${options.category}`);
  console.log(`🔗 API: ${options.url}\n`);
  
  try {
    const response = await fetch(`${options.url}/api/upload`, {
      method: 'POST',
      headers: {
        'X-API-Key': options.apiKey,
        ...formData.getHeaders(),
      },
      body: formData,
    });
    
    const result = await response.json();
    
    if (response.ok) {
      console.log('✅ Upload successful!\n');
      console.log('📊 Response:');
      console.log(JSON.stringify(result, null, 2));
      
      if (result.video_id) {
        console.log(`\n🎬 Watch URL: ${options.url}/watch/${result.video_id}`);
      }
      
      process.exit(0);
    } else {
      console.error('❌ Upload failed!\n');
      console.error('Error:', result.error || 'Unknown error');
      process.exit(1);
    }
  } catch (error) {
    console.error('❌ Upload error:', error.message);
    process.exit(1);
  }
}

uploadVideo();
