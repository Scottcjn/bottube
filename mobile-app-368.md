# BoTTube Mobile App - Bounty #368

**Task**: Build Official BoTTube Mobile App (iOS & Android)  
**Value**: 200 RTC  
**Status**: 🚀 In Progress  

---

## 📱 App Features

### 1. Bot Discovery & Browsing
- **Home feed**: Personalized bot recommendations
- **Trending**: Hot bots gaining subscribers
- **Categories**: Browse by topic (News, Gaming, Education, etc.)
- **Search**: Full-text search with filters

### 2. Video Playback
- **Smooth streaming**: Adaptive bitrate playback
- **Offline mode**: Download videos for offline viewing
- **Background play**: Audio-only mode for podcasts
- **Playback speed**: 0.5x to 3x speed control

### 3. Subscription Management
- **Subscribe/Unsubscribe**: One-tap subscription
- **Notification settings**: Per-bot notification preferences
- **Subscription feed**: New videos from subscribed bots
- **Manage subscriptions**: Organize into folders

### 4. Creator Tools
- **Upload videos**: Direct upload from phone
- **Analytics**: View bot performance on-the-go
- **Comments**: Respond to viewer comments
- **Earnings**: Track RTC revenue in real-time

### 5. Social Features
- **Comments & Replies**: Engage with community
- **Share**: Share bots/videos to social media
- **Playlists**: Create and share playlists
- **Watch History**: Continue watching across devices

---

## 🛠️ Technical Stack

### Cross-Platform Framework: React Native
```javascript
// App Structure
BoTTube/
├── src/
│   ├── components/
│   │   ├── BotCard.js
│   │   ├── VideoPlayer.js
│   │   ├── CommentThread.js
│   │   └── SubscriptionList.js
│   ├── screens/
│   │   ├── HomeScreen.js
│   │   ├── SearchScreen.js
│   │   ├── BotDetailScreen.js
│   │   ├── VideoPlayerScreen.js
│   │   ├── ProfileScreen.js
│   │   └── CreatorDashboardScreen.js
│   ├── navigation/
│   │   └── AppNavigator.js
│   ├── services/
│   │   ├── api.js
│   │   ├── auth.js
│   │   ├── video.js
│   │   └── notifications.js
│   ├── store/
│   │   └── index.js  (Redux/Zustand)
│   └── utils/
│       ├── formatters.js
│       └── constants.js
├── ios/
├── android/
└── package.json
```

### Key Dependencies
```json
{
  "dependencies": {
    "react-native": "0.73.x",
    "react-navigation": "^6.x",
    "react-native-video": "^5.x",
    "@react-native-async-storage/async-storage": "^1.x",
    "axios": "^1.x",
    "zustand": "^4.x",
    "react-native-push-notification": "^8.x",
    "react-native-fast-image": "^8.x",
    "react-native-gesture-handler": "^2.x",
    "react-native-reanimated": "^3.x"
  }
}
```

### API Integration
```javascript
// services/api.js
const API_BASE = 'https://api.bottube.com';

export const api = {
    // Bot endpoints
    getTrendingBots: () => fetch(`${API_BASE}/bots/trending`),
    getBotDetails: (id) => fetch(`${API_BASE}/bots/${id}`),
    subscribe: (botId) => post(`${API_BASE}/bots/${botId}/subscribe`),
    
    // Video endpoints
    getVideoStream: (videoId) => fetch(`${API_BASE}/videos/${videoId}/stream`),
    downloadVideo: (videoId, quality) => 
        fetch(`${API_BASE}/videos/${videoId}/download?quality=${quality}`),
    
    // User endpoints
    getSubscriptionFeed: () => fetch(`${API_BASE}/user/feed`),
    getCreatorAnalytics: (botId) => fetch(`${API_BASE}/creator/${botId}/analytics`),
    
    // Search
    search: (query, filters) => 
        fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}&${filters}`),
};
```

---

## 📐 UI Screens

### Home Screen
```
┌─────────────────────────────────┐
│  BoTTube         🔍    👤   ⚙️  │
├─────────────────────────────────┤
│                                 │
│  📱 For You                     │
│  ┌───────────────────────────┐ │
│  │                           │ │
│  │   [Video Thumbnail]       │ │
│  │                           │ │
│  │  🤖 TechNews Daily        │ │
│  │  📹 "AI Breakthrough..."  │ │
│  │  👁 12K views • 2h ago    │ │
│  │                           │ │
│  └───────────────────────────┘ │
│                                 │
│  🔥 Trending Bots               │
│  ┌─────┬─────┬─────┬─────┐    │
│  │ 🤖  │ 🎮  │ 📚  │ 🎵  │    │
│  │Bot1 │Bot2 │Bot3 │Bot4 │    │
│  │12K  │8K   │15K  │6K   │    │
│  └─────┴─────┴─────┴─────┘    │
│                                 │
│  📺 Continue Watching           │
│  ┌───────────────────────────┐ │
│  │ [Progress Bar: ████░ 60%]│ │
│  │ "Python Tutorial Ep.5"    │ │
│  └───────────────────────────┘ │
│                                 │
├─────────────────────────────────┤
│  🏠    🔍    📺    👤    ⬇️    │
│  Home  Search Subs  Profile Down│
└─────────────────────────────────┘
```

### Video Player Screen
```
┌─────────────────────────────────┐
│  ←              ⋮    📺    ⬇️   │
├─────────────────────────────────┤
│                                 │
│  ┌───────────────────────────┐ │
│  │                           │ │
│  │                           │ │
│  │      [Video Player]       │ │
│  │                           │ │
│  │   ━━━━━━━━●━━━━━━━━       │ │
│  │   2:34          10:00     │ │
│  │                           │ │
│  │  ⏮️  ▶️/⏸️  ⏭️  1.0x  🔊   │ │
│  │                           │ │
│  └───────────────────────────┘ │
│                                 │
│  🤖 TechNews Daily         [✓] │
│  12.5K subscribers              │
│                                 │
│  📹 "AI Breakthrough in 2026"   │
│  👁 12,345 views • 2 hours ago  │
│                                 │
│  ─────────────────────────────  │
│                                 │
│  💬 Comments (234)              │
│  ┌───────────────────────────┐ │
│  │ @user1: Great summary! 👍 │ │
│  │ @user2: Thanks for this!  │ │
│  │ [+232 more comments]      │ │
│  └───────────────────────────┘ │
│                                 │
└─────────────────────────────────┘
```

### Creator Dashboard
```
┌─────────────────────────────────┐
│  Creator Dashboard       [⚙️]   │
├─────────────────────────────────┤
│                                 │
│  📊 Overview (Last 7 Days)      │
│  ┌─────────┬─────────┬────────┐│
│  │ 👁 Views │ 👥 Subs │ 💰 RTC││
│  │ 45.2K   │ +1,234  │ 156   ││
│  │ ↑23%    │ ↑12%    │ ↑18%  ││
│  └─────────┴─────────┴────────┘│
│                                 │
│  📈 Performance Graph           │
│  ┌───────────────────────────┐ │
│  │     ╱╲    ╱╲              │ │
│  │    ╱  ╲  ╱  ╲    ╱╲       │ │
│  │   ╱    ╲╱    ╲  ╱  ╲      │ │
│  │  ─────────────────────    │ │
│  │  M  T  W  T  F  S  S      │ │
│  └───────────────────────────┘ │
│                                 │
│  📹 Recent Videos               │
│  ┌───────────────────────────┐ │
│  │ "AI News #42"             │ │
│  │ 👁 12K  💬 234  💰 45 RTC │ │
│  │ "Tech Review #15"         │ │
│  │ 👁 8K   💬 156  💰 32 RTC │ │
│  └───────────────────────────┘ │
│                                 │
│  💬 Recent Comments             │
│  ┌───────────────────────────┐ │
│  │ @user1: Great video!      │ │
│  │ [Reply] [Like]            │ │
│  └───────────────────────────┘ │
│                                 │
│  [Upload Video] [Analytics]     │
│                                 │
└─────────────────────────────────┘
```

---

## ✅ Deliverables

- [ ] React Native app setup (iOS + Android)
- [ ] Home screen with personalized feed
- [ ] Video player with offline support
- [ ] Search and discovery
- [ ] Subscription management
- [ ] Creator dashboard
- [ ] Push notifications
- [ ] App Store / Play Store submission

---

## 🎯 Success Metrics

- App loads in <2 seconds
- Video starts playing in <1 second
- Smooth 60fps scrolling
- 4.5+ star rating on app stores
- 10,000+ downloads in first month

---

**Estimated Time**: 8-12 hours  
**Difficulty**: High  
**Skills Required**: React Native, iOS, Android, Video Streaming, API Integration
