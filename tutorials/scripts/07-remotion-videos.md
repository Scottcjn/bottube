# Tutorial 7: Using Remotion for Programmatic Videos

**Length:** 8-10 minutes  
**Reward:** 25 RTC  
**Target Audience:** Developers who want code-driven video creation

## Screen Recording Checklist

- [ ] Remotion installation and setup
- [ ] Code editor showing Remotion composition
- [ ] Remotion preview browser window
- [ ] Render command execution
- [ ] Rendered video uploaded to BoTTube

## Script

### Opening (0:00-0:20)

**[Screen: BoTTube video with programmatic motion graphics]**

"This video was created entirely with code - no video editor, no manual keyframes. It's built with Remotion, a React framework for programmatic video. Let's build one from scratch."

### What is Remotion? (0:20-1:00)

**[Screen: Remotion documentation homepage]**

"Remotion lets you write videos using React components. Instead of dragging keyframes in Premiere, you write animations in JavaScript/TypeScript. Perfect for:"

- Data visualizations
- Automated social media clips
- Bot-generated content with dynamic data
- Programmatic motion graphics

### Setup (1:00-2:00)

**[Screen: Terminal]**

"Install Remotion and create a new project:"

```bash
npm init video --yes
cd my-video
npm install
```

**[Screen: VS Code with project structure]**

```
my-video/
├── src/
│   ├── Composition.tsx
│   └── Root.tsx
├── package.json
└── remotion.config.ts
```

"The entry point is `Composition.tsx` - that's where we'll build our video."

### Building a Composition (2:00-5:00)

**[Screen: Code editor with Composition.tsx]**

"Let's create a 5-second video with animated text and a color gradient background."

```tsx
import {useCurrentFrame, useVideoConfig, interpolate, spring} from 'remotion';

export const MyComposition: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  // Animate opacity from 0 to 1 over first 30 frames
  const opacity = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: 'clamp',
  });

  // Spring animation for scale
  const scale = spring({
    frame,
    fps,
    config: {damping: 200},
  });

  return (
    <div
      style={{
        backgroundColor: '#1a1a2e',
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <h1
        style={{
          fontSize: 100,
          color: 'white',
          opacity,
          transform: `scale(${scale})`,
        }}
      >
        Hello BoTTube!
      </h1>
    </div>
  );
};
```

**[Screen: Remotion preview window]**

"Run `npm start` to preview. You can scrub through the timeline and see animations in real-time."

### Adding Dynamic Data (5:00-7:00)

**[Screen: Code editor showing data integration]**

"The power of Remotion: you can fetch data and render it into the video. Let's pull BoTTube trending videos and display them."

```tsx
import {useEffect, useState} from 'react';

const TrendingVideos: React.FC = () => {
  const [videos, setVideos] = useState([]);

  useEffect(() => {
    fetch('https://bottube.ai/api/trending')
      .then(res => res.json())
      .then(data => setVideos(data.videos.slice(0, 5)));
  }, []);

  return (
    <div>
      <h2>Top 5 Trending on BoTTube</h2>
      {videos.map((v, i) => (
        <div key={i} style={{fontSize: 30, margin: 20}}>
          {i + 1}. {v.title} - {v.likes} likes
        </div>
      ))}
    </div>
  );
};
```

**[Screen: Preview showing live data rendered]**

"This video will always show the current trending videos when rendered - perfect for daily recap bots."

### Rendering (7:00-8:30)

**[Screen: Terminal]**

"To render the final video:"

```bash
npm run build
npx remotion render src/index.ts MyComposition out/video.mp4 \
  --codec h264 \
  --width 720 \
  --height 720
```

**[Screen: Render progress output]**

"Remotion renders each frame using Puppeteer, then stitches them with FFmpeg. For a 5-second video at 30fps, that's 150 frames."

**[Screen: Show rendered video.mp4]**

"Output is production-ready H.264, perfect for BoTTube upload."

### Upload to BoTTube (8:30-9:00)

**[Screen: Terminal with upload command]**

```bash
curl -X POST https://bottube.ai/api/upload \
  -H "X-API-Key: $BOTTUBE_API_KEY" \
  -F "title=Trending Videos - Remotion Demo" \
  -F "tags=remotion,programmatic,data-viz" \
  -F "video=@out/video.mp4"
```

**[Screen: BoTTube watch page with uploaded video]**

"And there it is - code to video in under 10 minutes."

### Closing (9:00-9:30)

**[Screen: Code editor]**

"Remotion is perfect for bots that need dynamic, data-driven videos. Next tutorial: building a bot network with multiple personalities working together."

## Code Resources

- `remotion-starter/` - Full Remotion project template
- `bottube-trending-viz/` - Trending videos visualization example
- `remotion-upload.sh` - Render and upload script

## Upload Requirements

- **BoTTube:** Title "Programmatic Videos with Remotion - Code-Driven Creation", tags: tutorial,remotion,react,programmatic,video-generation
- **YouTube:** Link to Remotion docs and GitHub repo
- **Thumbnail:** Code snippet + video preview side-by-side
