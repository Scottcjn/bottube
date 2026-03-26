-- BoTTube Generation Router -- Database Migration
-- Run against SQLite (bottube.db) or Supabase PostgreSQL
-- =================================================
-- Safe to run multiple times (all CREATE IF NOT EXISTS).

-- -----------------------------------------------------------
-- 1. generation_jobs -- central job tracking
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS generation_jobs (
    id TEXT PRIMARY KEY,
    owner_user_id INTEGER NOT NULL,           -- IMMUTABLE: never update this column
    request_json TEXT NOT NULL DEFAULT '{}',   -- GenerationRequest serialised as JSON
    status TEXT NOT NULL DEFAULT 'queued',     -- JobStatus enum value
    routing_mode TEXT DEFAULT 'quality',       -- fast | quality | experimental | safe
    selected_provider TEXT DEFAULT '',
    external_job_id TEXT DEFAULT '',
    progress REAL DEFAULT 0.0,                -- 0.0 - 100.0
    error TEXT DEFAULT '',

    -- Output references
    video_id TEXT DEFAULT '',                 -- BoTTube video_id once published
    video_url TEXT DEFAULT '',
    output_path TEXT DEFAULT '',              -- server-local filesystem path

    -- Quality gate
    quality_score INTEGER DEFAULT 0,          -- 0 - 100
    quality_passed INTEGER DEFAULT 0,         -- boolean
    requires_approval INTEGER DEFAULT 0,      -- boolean

    -- Timestamps (unix epoch)
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_genjobs_status ON generation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_genjobs_owner ON generation_jobs(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_genjobs_created ON generation_jobs(created_at);


-- -----------------------------------------------------------
-- 2. generation_attempts -- per-provider attempt log
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS generation_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    attempt_number INTEGER DEFAULT 0,
    success INTEGER DEFAULT 0,                -- boolean
    detail TEXT DEFAULT '',
    external_id TEXT DEFAULT '',
    started_at REAL NOT NULL,
    finished_at REAL DEFAULT 0,
    FOREIGN KEY (job_id) REFERENCES generation_jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_genattempts_job ON generation_attempts(job_id);


-- -----------------------------------------------------------
-- 3. generation_assets -- intermediate/final files
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS generation_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,                  -- 'raw', 'transcoded', 'thumbnail', 'audio'
    provider TEXT DEFAULT '',
    file_path TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    mime_type TEXT DEFAULT '',
    width INTEGER DEFAULT 0,
    height INTEGER DEFAULT 0,
    duration_sec REAL DEFAULT 0,
    created_at REAL NOT NULL,
    FOREIGN KEY (job_id) REFERENCES generation_jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_genassets_job ON generation_assets(job_id);


-- -----------------------------------------------------------
-- 4. Extend videos table -- add generation source columns
-- -----------------------------------------------------------
-- These ALTER TABLE statements must be run via application code
-- that catches "duplicate column" errors (SQLite does not support
-- ADD COLUMN IF NOT EXISTS).
--
-- Python migration code:
--   for col in ['source_job_id TEXT DEFAULT ""',
--               'source_provider TEXT DEFAULT ""',
--               'source_model TEXT DEFAULT ""']:
--       try: conn.execute(f"ALTER TABLE videos ADD COLUMN {col}")
--       except: pass
