"""
SQLite database layer for health tracker logs.
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    back_pain INTEGER,
    headache INTEGER,
    peace_level INTEGER,
    sleep_quality INTEGER,
    water_amount INTEGER,
    smoke_count INTEGER,
    caffeine_amount INTEGER,
    sitting_hours REAL,
    screen_hours REAL,
    food_details TEXT,
    period_status INTEGER,
    notes TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the logs table if it does not exist."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def insert_log(
    user_id: int,
    *,
    back_pain: Optional[int] = None,
    headache: Optional[int] = None,
    peace_level: Optional[int] = None,
    sleep_quality: Optional[int] = None,
    water_amount: Optional[int] = None,
    smoke_count: Optional[int] = None,
    caffeine_amount: Optional[int] = None,
    sitting_hours: Optional[float] = None,
    screen_hours: Optional[float] = None,
    food_details: Optional[str] = None,
    period_status: Optional[int] = None,
    notes: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> int:
    """Insert a log row. Returns the new row id."""
    ts = (timestamp or datetime.utcnow()).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO logs (
                timestamp, user_id, back_pain, headache, peace_level,
                sleep_quality, water_amount, smoke_count, caffeine_amount,
                sitting_hours, screen_hours, food_details, period_status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                user_id,
                back_pain,
                headache,
                peace_level,
                sleep_quality,
                water_amount,
                smoke_count,
                caffeine_amount,
                sitting_hours,
                screen_hours,
                food_details,
                period_status,
                notes,
            ),
        )
        conn.commit()
        return cur.lastrowid


def get_recent_logs(limit: int = 50, user_id: Optional[int] = None) -> list[sqlite3.Row]:
    """Return the most recent log rows (newest first).

    If *user_id* is given, only that user's logs are returned.
    """
    init_db()
    with get_connection() as conn:
        if user_id is not None:
            cur = conn.execute(
                "SELECT * FROM logs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM logs ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        return list(cur.fetchall())
