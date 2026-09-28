"""
SQLite-Datenbank für alle Bot-Features (XP, Streaks, Workouts, Tickets, ...).

Die Datei liegt standardmäßig unter data/mancave.db (per DB_PATH in der .env änderbar).
Der Bot läuft in einem einzigen Event-Loop – eine gemeinsame Verbindung reicht.
"""

import os
import sqlite3

DB_PATH = os.getenv("DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mancave.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    xp            INTEGER NOT NULL DEFAULT 0,
    level         INTEGER NOT NULL DEFAULT 0,
    messages      INTEGER NOT NULL DEFAULT 0,
    voice_minutes INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS checkins (
    user_id    INTEGER NOT NULL,
    day        TEXT    NOT NULL,
    koerper    TEXT,
    business   TEXT,
    wissen     TEXT,
    created_at TEXT,
    PRIMARY KEY (user_id, day)
);
CREATE TABLE IF NOT EXISTS workouts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    day        TEXT    NOT NULL,
    kind       TEXT    NOT NULL,
    minutes    INTEGER NOT NULL,
    note       TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS hall_of_fame (
    message_id     INTEGER PRIMARY KEY,
    hof_message_id INTEGER,
    author_id      INTEGER,
    content        TEXT,
    reactions      INTEGER,
    created_at     TEXT
);
CREATE TABLE IF NOT EXISTS ideas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  INTEGER UNIQUE,
    channel_id  INTEGER,
    author_id   INTEGER,
    title       TEXT,
    description TEXT,
    up          INTEGER NOT NULL DEFAULT 0,
    down        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS challenges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    days        INTEGER NOT NULL,
    start_day   TEXT NOT NULL,
    end_day     TEXT NOT NULL,
    message_id  INTEGER,
    channel_id  INTEGER,
    active      INTEGER NOT NULL DEFAULT 1,
    created_by  INTEGER
);
CREATE TABLE IF NOT EXISTS challenge_participants (
    challenge_id INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    joined_at    TEXT,
    completed    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (challenge_id, user_id)
);
CREATE TABLE IF NOT EXISTS challenge_checkins (
    challenge_id INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    day          TEXT    NOT NULL,
    PRIMARY KEY (challenge_id, user_id, day)
);
CREATE TABLE IF NOT EXISTS warnings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    moderator_id INTEGER,
    reason       TEXT,
    created_at   TEXT
);
CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    created_at TEXT,
    closed_at  TEXT
);
CREATE TABLE IF NOT EXISTS invites (
    member_id  INTEGER PRIMARY KEY,
    inviter_id INTEGER,
    code       TEXT,
    joined_at  TEXT,
    left_guild INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS member_stats (
    day     TEXT PRIMARY KEY,
    members INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS coach_usage (
    user_id INTEGER NOT NULL,
    day     TEXT    NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute("PRAGMA journal_mode=WAL")
_conn.executescript(SCHEMA)
_conn.commit()


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    cur = _conn.execute(sql, params)
    _conn.commit()
    return cur


def fetchone(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return _conn.execute(sql, params).fetchone()


def fetchall(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return _conn.execute(sql, params).fetchall()


def scalar(sql: str, params: tuple = (), default=0):
    row = fetchone(sql, params)
    return row[0] if row and row[0] is not None else default


def kv_get(key: str, default: str | None = None) -> str | None:
    row = fetchone("SELECT value FROM kv WHERE key = ?", (key,))
    return row["value"] if row else default


def kv_set(key: str, value: str):
    execute("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value))


def ensure_user(user_id: int):
    execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
