import sqlite3
from pathlib import Path

DB_PATH = Path("kosmostream.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS bd_calendar (
    date TEXT PRIMARY KEY,  -- ISO YYYY-MM-DD
    phase TEXT,
    sign TEXT,
    type TEXT,
    activities TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS weather_daily (
    date TEXT PRIMARY KEY,
    temp_min REAL,
    temp_max REAL,
    precipitation REAL,
    pop REAL,
    description TEXT,
    icon TEXT,
    moon_phase REAL,
    fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS space_weather (
    fetched_at TEXT PRIMARY KEY,
    kp_now REAL,
    kp_24h_max REAL,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS suggestions (
    date TEXT PRIMARY KEY,
    headline TEXT,
    detail TEXT,
    alert_level TEXT  -- info|warn|alert
);
"""

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()