-- TV device authentication tables
CREATE TABLE IF NOT EXISTS tv_device_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_code TEXT NOT NULL UNIQUE,
    user_code TEXT NOT NULL UNIQUE,
    expires_at INTEGER NOT NULL,
    verified INTEGER DEFAULT 0,
    user_id INTEGER,
    created_at INTEGER DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS tv_access_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    access_token TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    device_code TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    created_at INTEGER DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (device_code) REFERENCES tv_device_codes (device_code)
);

-- Index for faster token lookups
CREATE INDEX IF NOT EXISTS idx_tv_access_tokens_token ON tv_access_tokens (access_token);
CREATE INDEX IF NOT EXISTS idx_tv_device_codes_device ON tv_device_codes (device_code);
CREATE INDEX IF NOT EXISTS idx_tv_device_codes_user ON tv_device_codes (user_code);