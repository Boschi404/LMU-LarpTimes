-- LMU Pit Strategist — Cloud Schema (Turso / libSQL)
--
-- This schema mirrors the local SQLite one, with two additions:
--   1. A `users` table for opt-in identity (random UUID + display name)
--   2. A `user_id` column on `sessions` to aggregate per-user stats
--
-- The local DB and the cloud DB share the SAME `session_uuid` values, so
-- dedup is automatic when the local app imports community laps.

-- ════════════════════════════════════════════════════════════════════════════
-- 1. Users (one row per opt-in user, identified by random UUID)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,                -- Random UUID generated on opt-in
    display_name TEXT NOT NULL,         -- User-chosen (or auto-generated) name
    created_at TEXT NOT NULL,           -- ISO 8601
    last_seen_at TEXT,                  -- ISO 8601, updated on each push
    total_sessions INTEGER NOT NULL DEFAULT 0,
    total_laps INTEGER NOT NULL DEFAULT 0,
    opt_out_at TEXT                     -- ISO 8601, set when user deletes data
);

CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen_at DESC);

-- ════════════════════════════════════════════════════════════════════════════
-- 2. Sessions (same as local, +user_id)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid TEXT NOT NULL UNIQUE,
    user_id TEXT,                       -- NULL for legacy / anonymous data
    track TEXT NOT NULL,
    layout TEXT NOT NULL,
    car TEXT NOT NULL,
    session_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_car_track ON sessions(car, track);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);

-- ════════════════════════════════════════════════════════════════════════════
-- 3. Stints
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS stints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    stint_number INTEGER NOT NULL,
    compound_front TEXT NOT NULL,
    compound_rear TEXT NOT NULL,
    start_lap INTEGER NOT NULL,
    end_lap INTEGER,
    start_fuel_l REAL NOT NULL,
    end_fuel_l REAL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- ════════════════════════════════════════════════════════════════════════════
-- 4. Laps (main table — same as local)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS laps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    stint_id INTEGER,
    lap_number INTEGER NOT NULL,
    lap_time REAL NOT NULL,
    sector_1 REAL NOT NULL,
    sector_2 REAL NOT NULL,
    sector_3 REAL NOT NULL,
    is_valid_lap INTEGER NOT NULL,
    is_pit_in_lap INTEGER NOT NULL,
    is_pit_out_lap INTEGER NOT NULL,
    compound_front TEXT NOT NULL,
    compound_rear TEXT NOT NULL,
    tyre_age_laps INTEGER NOT NULL,
    wear_pct_start_FL REAL NOT NULL,
    wear_pct_start_FR REAL NOT NULL,
    wear_pct_start_RL REAL NOT NULL,
    wear_pct_start_RR REAL NOT NULL,
    wear_pct_end_FL REAL NOT NULL,
    wear_pct_end_FR REAL NOT NULL,
    wear_pct_end_RL REAL NOT NULL,
    wear_pct_end_RR REAL NOT NULL,
    fuel_start_l REAL NOT NULL,
    fuel_end_l REAL NOT NULL,
    fuel_used_l REAL NOT NULL,
    track_temp REAL NOT NULL,
    ambient_temp REAL NOT NULL,
    weather_state TEXT NOT NULL,
    rain_intensity REAL NOT NULL,
    completed_at TEXT NOT NULL,
    anomaly_flag INTEGER NOT NULL DEFAULT 0,
    anomaly_reason TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (stint_id) REFERENCES stints(id)
);

CREATE INDEX IF NOT EXISTS idx_laps_session ON laps(session_id, lap_number);
CREATE INDEX IF NOT EXISTS idx_laps_compound ON laps(compound_front);

-- ════════════════════════════════════════════════════════════════════════════
-- 5. Pit stops
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS pit_stops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    lap_number INTEGER NOT NULL,
    pit_loss REAL NOT NULL,
    in_lap_number INTEGER NOT NULL,
    out_lap_number INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- ════════════════════════════════════════════════════════════════════════════
-- 6. Community meta (for future global stats: top contributors, etc.)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS community_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Seed with a few defaults
INSERT OR IGNORE INTO community_meta (key, value, updated_at) VALUES
    ('schema_version', '1', datetime('now')),
    ('total_sessions', '0', datetime('now')),
    ('total_laps', '0', datetime('now')),
    ('total_users', '0', datetime('now'));

-- ════════════════════════════════════════════════════════════════════════════
-- 7. Shareable bundles (the push payload store, JSON in a row)
--    Each row = one push from one user. The first session_uuid is the
--    natural primary key (dedup on subsequent pushes).
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS shareable_bundles (
    remote_id TEXT PRIMARY KEY,
    exported_at TEXT,
    session_count INTEGER,
    lap_count INTEGER,
    payload_json TEXT,
    pushed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_bundles_exported ON shareable_bundles(exported_at DESC);
