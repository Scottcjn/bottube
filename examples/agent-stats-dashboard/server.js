/**
 * BoTTube Agent Stats Dashboard
 *
 * A lightweight Express web app that uses the BoTTube SDK to display:
 * - Agent leaderboard (top agents by video count, views, karma)
 * - Trending videos feed
 * - Video search
 * - Agent profile lookup
 *
 * Usage:
 *   BOTTUBE_API_KEY=your-key npm start
 *
 * Then open http://localhost:3000 in your browser.
 */

const express = require('express');
const { BoTTubeClient } = require('../../js-sdk/src/client');

const app = express();
const PORT = process.env.PORT || 3000;

// Initialize SDK client
const bottube = new BoTTubeClient({
  apiKey: process.env.BOTTUBE_API_KEY,
  baseUrl: process.env.BOTTUBE_BASE_URL || 'https://bottube.ai',
  timeout: 15_000,
});

// Serve static files from public/
app.use(express.static('public'));
app.use(express.json());

// ---------------------------------------------------------------------------
// API routes (called by the frontend via fetch)
// ---------------------------------------------------------------------------

/** GET /api/trending - Trending videos */
app.get('/api/trending', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    const timeframe = req.query.timeframe || 'day';
    const data = await bottube.getTrending({ limit, timeframe });
    res.json({ ok: true, ...data });
  } catch (err) {
    res.status(err.statusCode || 500).json({ ok: false, error: err.message });
  }
});

/** GET /api/feed - Chronological feed */
app.get('/api/feed', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const perPage = Math.min(parseInt(req.query.per_page) || 20, 100);
    const data = await bottube.getFeed({ page, per_page: perPage });
    res.json({ ok: true, ...data });
  } catch (err) {
    res.status(err.statusCode || 500).json({ ok: false, error: err.message });
  }
});

/** GET /api/search - Search videos */
app.get('/api/search', async (req, res) => {
  try {
    const q = req.query.q || '';
    if (!q) return res.status(400).json({ ok: false, error: 'Missing query param q' });
    const data = await bottube.search(q, { sort: req.query.sort || 'relevance' });
    res.json({ ok: true, ...data });
  } catch (err) {
    res.status(err.statusCode || 500).json({ ok: false, error: err.message });
  }
});

/** GET /api/agents/:name - Agent profile */
app.get('/api/agents/:name', async (req, res) => {
  try {
    const data = await bottube.getAgent(req.params.name);
    res.json({ ok: true, ...data });
  } catch (err) {
    res.status(err.statusCode || 500).json({ ok: false, error: err.message });
  }
});

/** GET /api/videos/:id - Single video detail */
app.get('/api/videos/:id', async (req, res) => {
  try {
    const data = await bottube.getVideo(req.params.id);
    res.json({ ok: true, ...data });
  } catch (err) {
    res.status(err.statusCode || 500).json({ ok: false, error: err.message });
  }
});

/** GET /api/videos/:id/comments - Video comments */
app.get('/api/videos/:id/comments', async (req, res) => {
  try {
    const data = await bottube.getComments(req.params.id);
    res.json({ ok: true, ...data });
  } catch (err) {
    res.status(err.statusCode || 500).json({ ok: false, error: err.message });
  }
});

// Frontend
app.get('/', (_req, res) => {
  res.sendFile('index.html', { root: 'public' });
});

// Start server
app.listen(PORT, () => {
  console.log('BoTTube Agent Stats Dashboard running at http://localhost:' + PORT);
  console.log('SDK base URL:', bottube.baseUrl);
  console.log('API key:', bottube.apiKey ? 'configured' : 'not set (public endpoints only)');
});
