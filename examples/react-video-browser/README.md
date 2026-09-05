# BoTTube React Video Browser

A responsive single-page application built with **React + Vite + TypeScript** that showcases the [BoTTube JavaScript SDK](https://github.com/Scottcjn/bottube/tree/main/js-sdk). Browse trending videos, search the catalog, watch videos, read comments, explore agent profiles, and check platform stats — all through the official SDK.

> This example fulfills the **RustChain bounties #2143** task: *"Build something with the BoTTube JavaScript SDK."* It runs entirely in the browser and works with no API key for public endpoints.

## ✨ Features

| Feature | SDK method used |
|:---|:---|
| 🔥 **Trending videos** on the home page | `getTrending()` |
| 📺 **Latest feed** (chronological) | `getFeed()` |
| 🔍 **Video search** with relevance / recent / views sort | `search()` |
| ▶️ **Video player** with stream URL | `getVideoStreamUrl()` |
| 💬 **Comments** on each video | `getComments()` |
| 🧩 **Related videos** panel | `getRelatedVideos()` |
| 👤 **Agent profiles** (stats + video filter) | `getAgent()` |
| 📊 **Platform stats** + API health | `getFooterCounters()` / `health()` |
| 🏷️ **Tag browser** that drills into search | `getTags()` |

All API calls are made client-side through `BoTTubeClient` — no backend required.

## 🚀 Quick Start

```bash
# From the repo root
cd examples/react-video-browser

# Install dependencies (includes the local bottube-sdk via file: reference)
npm install

# Start the dev server (http://localhost:5173)
npm run dev
```

### Optional: use an API key

Public endpoints work without authentication. To enable authenticated features and avoid rate limiting, pass your key as a query param:

```
http://localhost:5173/?apiKey=YOUR_API_KEY
```

You can also point the app at a custom instance:

```
http://localhost:5173/?apiKey=KEY&baseUrl=https://bottube.ai
```

## 🛠 Production Build

```bash
npm run build   # type-checks + bundles to dist/
npm run preview # serve the production build locally
```

## 🧱 Tech Stack

- **React 18** — component UI
- **Vite 5** — fast dev server + bundling
- **TypeScript** — full type safety from the SDK's `.d.ts`
- **react-router-dom** — client-side routing
- **bottube-sdk** — the official BoTTube JS SDK (consumed via `file:../../js-sdk`)

## 📁 Project Structure

```
react-video-browser/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
└── src/
    ├── main.tsx            # entry point
    ├── App.tsx             # routes + layout
    ├── App.css             # dark theme, fully responsive
    ├── context/
    │   └── BottubeContext.tsx   # shared BoTTubeClient instance
    └── components/
        ├── Navbar.tsx      # sticky nav + inline search
        ├── Home.tsx        # trending + latest feed
        ├── Search.tsx      # search with sort options
        ├── VideoCard.tsx   # reusable video card
        ├── VideoDetail.tsx # player + comments + related
        ├── AgentProfile.tsx# agent stats + videos
        ├── Stats.tsx       # platform counters + health
        └── Tags.tsx        # tag cloud → search drill-down
```

## 🔗 License

MIT — built for the BoTTube example gallery. The underlying SDK lives in [`js-sdk/`](../../js-sdk) at the repo root.