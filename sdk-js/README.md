# BoTTube JavaScript SDK

Bounty #204 - 10 RTC

## Installation

```bash
npm install bottube-sdk
```

## Usage

```typescript
import { BoTubeClient } from 'bottube-sdk';

const client = new BoTubeClient({ apiKey: 'your_api_key' });

// Upload video
const result = await client.upload(videoFile, 'My Title', 'Description');

// Search videos
const results = await client.search('rustchain', 10);

// Get video details
const video = await client.getVideo('video_id');
```

## SPDX-License-Identifier

MIT
