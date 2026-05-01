
# YouTube to BoTTube Migration Guide

## Introduction

Welcome to BoTTube! This guide will help you migrate your YouTube content and metadata to our decentralized platform. BoTTube offers a more open, community-driven, and censorship-resistant alternative to traditional video platforms.

---

## Prerequisites

Before you begin, ensure you have:
- A BoTTube account (sign up at [bottube.com](https://bottube.com))
- Your YouTube channel data exported (see [YouTube Data Export Guide](#exporting-your-youtube-data))
- Basic familiarity with command line tools (optional but helpful)

---

## Step 1: Exporting Your YouTube Data

### Using YouTube Studio

1. Go to [YouTube Studio](https://studio.youtube.com/)
2. Navigate to **Settings** > **Content ownership**
3. Click on **Download your data**
4. Select **All content** and **Channel metadata**
5. Choose a file format (ZIP recommended)
6. Click **Download** and wait for the export to complete

### Using YouTube Data API (Advanced)

If you prefer programmatic access:
1. Enable the YouTube Data API v3 in the [Google Cloud Console](https://console.cloud.google.com/)
2. Create credentials and download your OAuth 2.0 client ID
3. Use the [YouTube Data API](https://developers.google.com/youtube/v3) to fetch your data

---

## Step 2: Understanding BoTTube Data Structure

BoTTube uses a decentralized storage system with the following key components:

- **Videos**: Stored as IPFS content hashes
- **Metadata**: Structured JSON documents with video information
- **Channel**: Your account represents your channel
- **Tags**: Decentralized tagging system for discoverability

### Sample Video Metadata Structure

```json
{
  "id": "QmVideoHash123",
  "title": "Your Video Title",
  "description": "Video description...",
  "tags": ["technology", "ai", "bottube"],
  "thumbnail": "QmThumbnailHash456",
  "duration": "120",
  "publishDate": "2023-01-01T00:00:00Z",
  "viewCount": 1000,
  "author": "your_channel_id",
  "contentUrl": "ipfs://QmVideoHash123"
}
```

---

## Step 3: Migrating Your Content

### Option A: Using the BoTTube CLI Uploader

1. Install the BoTTube CLI:
   ```bash
   npm install -g @bottube/cli
   ```

2. Authenticate:
   ```bash
   bottube login
   ```

3. Upload your videos:
   ```bash
   bottube upload --source /path/to/your/youtube/export --channel your_channel_id
   ```

### Option B: Manual Migration with IPFS

1. Install IPFS:
   ```bash
   curl -fsSL https://ipfs.io/install.sh | bash
   ipfs init
   ```

2. Add your video files to IPFS:
   ```bash
   ipfs add /path/to/your/video.mp4
   ```

3. Create metadata files for each video (see [Sample Metadata](#sample-video-metadata-structure))

4. Upload metadata to BoTTube:
   ```bash
   curl -X POST https://api.bottube.com/videos \
     -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
     -H "Content-Type: application/json" \
     -d @video_metadata.json
   ```

---

## Step 4: Mapping YouTube Metadata to BoTTube

Here's how to map common YouTube metadata fields to BoTTube:

| YouTube Field          | BoTTube Field       | Notes                                  |
|-----------------------|--------------------|----------------------------------------|
| title                 | title              | Required                               |
| description           | description        | Optional but recommended                |
| tags                  | tags               | Use BoTTube's tagging system            |
| publishedAt           | publishDate        | ISO 8601 format                        |
| viewCount             | viewCount          | Optional (can be updated later)        |
| duration              | duration           | In seconds                            |
| defaultAudioLanguage  | audioLanguage      | Optional                              |
| category              | category           | Map to BoTTube's category system       |
| thumbnailUrl          | thumbnail          | IPFS hash of thumbnail                 |

---

## Step 5: Preserving Your Channel Identity

1. **Channel Name**: Keep your YouTube channel name or choose a new one
2. **Profile Picture**: Upload your existing profile picture
3. **About Section**: Copy your YouTube channel description
4. **Custom URL**: Set up a custom URL if you want to maintain your brand

---

## Step 6: Post-Migration Tasks

### 1. Update Your Links

- Update all external links to point to your BoTTube content
- Update your social media profiles to include your BoTTube channel

### 2. Notify Your Audience

- Post an announcement about your migration
- Share your BoTTube channel link on all platforms
- Consider creating a migration video explaining the process

### 3. Monitor and Update

- Check your analytics dashboard regularly
- Update metadata as needed (titles, descriptions, tags)
- Engage with your community to gather feedback

---

## Troubleshooting Common Issues

### Issue: Videos not appearing in search

**Solution**: Verify that:
- Your tags are correct and follow BoTTube's tagging system
- Your metadata is properly formatted
- Your videos are properly uploaded to IPFS

### Issue: Missing video thumbnails

**Solution**:
1. Generate thumbnails using BoTTube's thumbnail generator
2. Upload thumbnails to IPFS
3. Update your metadata with the correct thumbnail hash

### Issue: View counts not syncing

**Solution**:
- View counts are initially based on upload time
- They will update as users watch your content
- You can manually update view counts through the API if needed

---

## Advanced: Automating Your Migration

For large channels, consider creating a script to automate the migration process:

```javascript
// Example Node.js script for automated migration
const fs = require('fs');
const { BottubeAPI } = require('@bottube/api');
const { ipfs } = require('ipfs-http-client');

async function migrateVideos() {
  const client = new BottubeAPI('YOUR_ACCESS_TOKEN');
  const ipfsClient = ipfs.connect('https://ipfs.infura.io:5001');

  const youtubeData = JSON.parse(fs.readFileSync('youtube_export.json'));
  const channelId = 'YOUR_CHANNEL_ID';

  for (const video of youtubeData.videos) {
    // Upload video to IPFS
    const { path: videoHash } = await ipfsClient.add(fs.createReadStream(video.filePath));

    // Generate thumbnail hash
    const { path: thumbnailHash } = await ipfsClient.add(fs.createReadStream(video.thumbnailPath));

    // Create metadata
    const metadata = {
      id: `Qm${Math.random().toString(36).substr(2, 10)}`,
      title: video.title,
      description: video.description,
      tags: video.tags,
      thumbnail: thumbnailHash,
      duration: video.duration,
      publishDate: video.publishedAt,
      viewCount: video.viewCount,
      author: channelId,
      contentUrl: `ipfs://${videoHash}`
    };

    // Upload to BoTTube
    await client.createVideo(metadata);
  }
}

migrateVideos().catch(console.error);
```

---

## Resources

- [BoTTube API Documentation](https://docs.bottube.com/api)
- [IPFS Documentation](https://docs.ipfs.io/)
- [BoTTube Community Support](https://community.bottube.com)
- [BoTTube Developer Forum](https://forum.bottube.com)

---

## Final Notes

Migrating from YouTube to BoTTube is a significant but rewarding process. While BoTTube offers many advantages, it's important to note that:

1. YouTube has a large, established audience - it may take time to rebuild your community
2. BoTTube is still evolving - new features may be added over time
3. Decentralization means some familiar tools and features may not be available

We encourage you to embrace this transition as an opportunity to create a more open, community-driven content ecosystem.

Good luck with your migration! If you encounter any issues or have questions, don't hesitate to reach out to our support team or community forums.
