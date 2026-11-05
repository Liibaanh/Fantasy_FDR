-- Schema for the tables the FastAPI app (main.py) reads.
-- Safe to run repeatedly: every statement uses IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS teams (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    short_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY,   -- gameweek number
    name          TEXT,
    deadline_time TEXT,
    finished      INTEGER NOT NULL       -- 0 or 1
);

CREATE TABLE IF NOT EXISTS fixtures (
    id           INTEGER PRIMARY KEY,
    event        INTEGER,                -- gameweek; NULL if not yet scheduled
    team_h       INTEGER NOT NULL,
    team_a       INTEGER NOT NULL,
    kickoff_time TEXT,
    finished     INTEGER NOT NULL        -- 0 or 1
);

CREATE TABLE IF NOT EXISTS players (
    id           INTEGER PRIMARY KEY,
    web_name     TEXT NOT NULL,
    team         INTEGER NOT NULL,
    element_type INTEGER NOT NULL        -- 1 GK, 2 DEF, 3 MID, 4 FWD
);

-- One row per player per fixture. A player in a double gameweek has two rows.
CREATE TABLE IF NOT EXISTS player_points (
    id      INTEGER NOT NULL,            -- player id
    fixture INTEGER NOT NULL,
    gw      INTEGER NOT NULL,
    points  INTEGER NOT NULL,
    PRIMARY KEY (id, fixture)
);

CREATE INDEX IF NOT EXISTS idx_player_points_gw ON player_points (gw);