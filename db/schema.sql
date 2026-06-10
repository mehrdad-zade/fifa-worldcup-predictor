-- FIFA World Cup 2026 Predictor — SQLite Schema
-- All CREATE TABLE statements are idempotent (IF NOT EXISTS).

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ── Teams ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS teams (
    team_id             INTEGER PRIMARY KEY,
    name                TEXT    NOT NULL UNIQUE,
    group_code          TEXT    NOT NULL,          -- A–L
    confederation       TEXT    NOT NULL,
    api_football_id     INTEGER,
    fbref_slug          TEXT,
    transfermarkt_id    INTEGER
);

-- ── Fixtures ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fixtures (
    fixture_id          TEXT    PRIMARY KEY,       -- wc-2026-m{N}
    api_fixture_id      INTEGER,
    stage               TEXT    NOT NULL,          -- Group Stage, R32, R16, QF, SF, Final
    group_code          TEXT,                      -- NULL for knockout rounds
    home_team_id        INTEGER REFERENCES teams(team_id),
    away_team_id        INTEGER REFERENCES teams(team_id),
    match_date          TEXT    NOT NULL,          -- ISO 8601 datetime
    venue               TEXT,
    fetched_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Results ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS results (
    fixture_id          TEXT    PRIMARY KEY REFERENCES fixtures(fixture_id),
    home_score          INTEGER NOT NULL,
    away_score          INTEGER NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'FT',  -- FT / AET / PEN
    fetched_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Predictions ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS predictions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id          TEXT    NOT NULL REFERENCES fixtures(fixture_id),
    model_version       TEXT    NOT NULL,
    predicted_home      INTEGER NOT NULL,
    predicted_away      INTEGER NOT NULL,
    prob_home_win       REAL    NOT NULL,
    prob_draw           REAL    NOT NULL,
    prob_away_win       REAL    NOT NULL,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(fixture_id, model_version)
);

-- ── Elo History ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS elo_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id             INTEGER NOT NULL REFERENCES teams(team_id),
    elo_rating          REAL    NOT NULL,
    effective_date      TEXT    NOT NULL,          -- ISO 8601 date
    reason              TEXT                       -- e.g. "WC 2022 Group Stage: BRA 2-0 SRB"
);

-- ── Evaluation Log ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS evaluation_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    model_version       TEXT    NOT NULL,
    fixture_id          TEXT    NOT NULL REFERENCES fixtures(fixture_id),
    brier_score         REAL,
    rps                 REAL,
    outcome_correct     INTEGER,                   -- 0 or 1
    evaluated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Player Stats (from FBref) ────────────────────────────────
CREATE TABLE IF NOT EXISTS player_stats (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id             INTEGER NOT NULL REFERENCES teams(team_id),
    player_name         TEXT    NOT NULL,
    position            TEXT,
    club                TEXT,
    minutes_played      INTEGER DEFAULT 0,         -- last 30 days at club
    sca                 REAL    DEFAULT 0.0,        -- shot-creating actions
    gca                 REAL    DEFAULT 0.0,        -- goal-creating actions
    goals               INTEGER DEFAULT 0,
    assists             INTEGER DEFAULT 0,
    is_injured          INTEGER DEFAULT 0,          -- 0 or 1
    is_suspended        INTEGER DEFAULT 0,          -- 0 or 1
    fetched_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Player Values (from Transfermarkt) ──────────────────────
CREATE TABLE IF NOT EXISTS player_values (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id             INTEGER NOT NULL REFERENCES teams(team_id),
    player_name         TEXT    NOT NULL,
    market_value_eur    INTEGER DEFAULT 0,
    fetched_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Claude News Cache ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS claude_news_cache (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id             INTEGER NOT NULL REFERENCES teams(team_id),
    response_json       TEXT    NOT NULL,           -- full structured JSON from Claude
    disruption_severity REAL    NOT NULL DEFAULT 0.0,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at          TEXT    NOT NULL             -- created_at + 6 hours
);

-- ── Trophy Events (for momentum feature) ────────────────────
CREATE TABLE IF NOT EXISTS trophy_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id             INTEGER NOT NULL REFERENCES teams(team_id),
    tournament_name     TEXT    NOT NULL,
    tournament_type     TEXT    NOT NULL,           -- WC, Continental, NationsLeague, Friendly
    won_date            TEXT    NOT NULL,           -- ISO 8601 date
    importance_multiplier REAL  NOT NULL DEFAULT 1.0
);

-- ── Indexes ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_fixtures_date         ON fixtures(match_date);
CREATE INDEX IF NOT EXISTS idx_elo_team_date         ON elo_history(team_id, effective_date);
CREATE INDEX IF NOT EXISTS idx_player_stats_team     ON player_stats(team_id);
CREATE INDEX IF NOT EXISTS idx_eval_log_version      ON evaluation_log(model_version);
CREATE INDEX IF NOT EXISTS idx_claude_cache_team_exp ON claude_news_cache(team_id, expires_at);
