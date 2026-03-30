-- BoTTube Thumbnail CTR Tracking & A/B Testing Schema
-- Run via: sqlite3 bottube.db < migration.sql
-- Or applied programmatically via CTRTracker.init_db() / ABTestManager.init_db()

-- ---------------------------------------------------------------------------
-- CTR Tracking
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS video_ctr (
    video_id TEXT PRIMARY KEY,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    watch_time_sum REAL NOT NULL DEFAULT 0.0,
    ctr REAL NOT NULL DEFAULT 0.0,
    avg_watch_time REAL NOT NULL DEFAULT 0.0,
    last_updated REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_video_ctr_ctr ON video_ctr(ctr DESC);
CREATE INDEX IF NOT EXISTS idx_video_ctr_impressions ON video_ctr(impressions DESC);

-- ---------------------------------------------------------------------------
-- Thumbnail A/B Testing
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS thumbnail_variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    variant_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'auto',  -- 'auto', 'upload', 'ai_gen'
    created_at REAL NOT NULL,
    UNIQUE(video_id, variant_key)
);

CREATE INDEX IF NOT EXISTS idx_thumb_variants_video ON thumbnail_variants(video_id);

CREATE TABLE IF NOT EXISTS variant_impressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    variant_key TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'impression',  -- 'impression' or 'click'
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_variant_imp_video ON variant_impressions(video_id, variant_key);

CREATE TABLE IF NOT EXISTS ab_test_results (
    video_id TEXT PRIMARY KEY,
    winning_variant TEXT NOT NULL,
    winning_ctr REAL NOT NULL DEFAULT 0.0,
    total_impressions INTEGER NOT NULL DEFAULT 0,
    locked_at REAL NOT NULL
);
