"""
SQLite database layer for health tracker logs, medications, exercises, and
user settings.
"""
import csv
import io
import json
import shutil
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
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
    sleep_hours REAL,
    water_amount INTEGER,
    smoke_count INTEGER,
    caffeine_amount INTEGER,
    sitting_hours REAL,
    screen_hours REAL,
    food_details TEXT,
    period_status INTEGER,
    stress_level INTEGER,
    anxiety_level INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    dosage TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    exercise_type TEXT NOT NULL,
    duration_minutes INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    timezone TEXT DEFAULT 'UTC',
    reminder_noon TEXT DEFAULT '12:00',
    reminder_night TEXT DEFAULT '21:00'
);

CREATE TABLE IF NOT EXISTS sessions (
    user_id INTEGER PRIMARY KEY,
    flow TEXT NOT NULL,
    step TEXT NOT NULL,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_MIGRATIONS = {
    "logs": {
        "stress_level": "INTEGER",
        "anxiety_level": "INTEGER",
        "sleep_hours": "REAL",
        "phone_hours": "REAL",
        "computer_hours": "REAL",
        "back_patch": "INTEGER",
        "heater_hours": "REAL",
        "massage_type": "TEXT",
        "heavy_lifting_kg": "REAL",
    },
}


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _run_migrations(conn: sqlite3.Connection) -> None:
    for table, columns in _MIGRATIONS.items():
        try:
            cursor = conn.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in cursor.fetchall()}
        except sqlite3.OperationalError:
            continue
        for col, col_type in columns.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
    conn.commit()


def init_db() -> None:
    """Create all tables if they do not exist, then run migrations."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _run_migrations(conn)


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

def insert_log(
    user_id: int,
    *,
    back_pain: Optional[int] = None,
    headache: Optional[int] = None,
    peace_level: Optional[int] = None,
    sleep_quality: Optional[int] = None,
    sleep_hours: Optional[float] = None,
    water_amount: Optional[int] = None,
    smoke_count=None,
    caffeine_amount: Optional[int] = None,
    sitting_hours: Optional[float] = None,
    screen_hours: Optional[float] = None,
    phone_hours: Optional[float] = None,
    computer_hours: Optional[float] = None,
    food_details: Optional[str] = None,
    period_status: Optional[int] = None,
    stress_level: Optional[int] = None,
    anxiety_level: Optional[int] = None,
    back_patch: Optional[int] = None,
    heater_hours: Optional[float] = None,
    massage_type: Optional[str] = None,
    heavy_lifting_kg: Optional[float] = None,
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
                sleep_quality, sleep_hours, water_amount, smoke_count,
                caffeine_amount, sitting_hours, screen_hours,
                phone_hours, computer_hours,
                food_details, period_status, stress_level, anxiety_level,
                back_patch, heater_hours, massage_type, heavy_lifting_kg,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts, user_id, back_pain, headache, peace_level,
                sleep_quality, sleep_hours, water_amount, smoke_count,
                caffeine_amount, sitting_hours, screen_hours,
                phone_hours, computer_hours,
                food_details, period_status, stress_level, anxiety_level,
                back_patch, heater_hours, massage_type, heavy_lifting_kg,
                notes,
            ),
        )
        conn.commit()
        return cur.lastrowid


def get_recent_logs(limit: int = 50, user_id: Optional[int] = None) -> list[sqlite3.Row]:
    """Return the most recent log rows (newest first)."""
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


def get_logs_by_date_range(
    user_id: int, start_date: str, end_date: str,
) -> list[sqlite3.Row]:
    """Return logs within [start_date, end_date) ordered by timestamp ASC."""
    init_db()
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM logs WHERE user_id = ? AND timestamp >= ? AND timestamp < ? "
            "ORDER BY timestamp ASC",
            (user_id, start_date, end_date),
        )
        return list(cur.fetchall())


def get_today_smoke_count(user_id: int, today_str: str) -> float:
    """Sum of smoke_count for a given day (today_str like '2026-03-01')."""
    init_db()
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT COALESCE(SUM(smoke_count), 0) as total "
            "FROM logs WHERE user_id = ? AND timestamp LIKE ?",
            (user_id, f"{today_str}%"),
        )
        return cur.fetchone()["total"]


def get_today_patch_count(user_id: int, today_str: str) -> int:
    """Count of back_patch entries for a given day."""
    init_db()
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT COALESCE(SUM(back_patch), 0) as total "
            "FROM logs WHERE user_id = ? AND timestamp LIKE ?",
            (user_id, f"{today_str}%"),
        )
        return cur.fetchone()["total"]


def delete_last_log(user_id: int) -> bool:
    """Delete the most recent log for the user. Returns True if deleted."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id FROM logs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM logs WHERE id = ?", (row["id"],))
        conn.commit()
        return True


# ---------------------------------------------------------------------------
# Medications
# ---------------------------------------------------------------------------

def insert_medication(
    user_id: int,
    name: str,
    dosage: Optional[str] = None,
    notes: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> int:
    ts = (timestamp or datetime.utcnow()).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO medications (timestamp, user_id, name, dosage, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (ts, user_id, name, dosage, notes),
        )
        conn.commit()
        return cur.lastrowid


def get_recent_medications(
    limit: int = 10, user_id: Optional[int] = None,
) -> list[sqlite3.Row]:
    init_db()
    with get_connection() as conn:
        if user_id is not None:
            cur = conn.execute(
                "SELECT * FROM medications WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM medications ORDER BY id DESC LIMIT ?", (limit,),
            )
        return list(cur.fetchall())


def get_medications_by_date_range(
    user_id: int, start_date: str, end_date: str,
) -> list[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM medications WHERE user_id = ? "
            "AND timestamp >= ? AND timestamp < ? ORDER BY timestamp ASC",
            (user_id, start_date, end_date),
        )
        return list(cur.fetchall())


# ---------------------------------------------------------------------------
# Exercises
# ---------------------------------------------------------------------------

def insert_exercise(
    user_id: int,
    exercise_type: str,
    duration_minutes: Optional[int] = None,
    notes: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> int:
    ts = (timestamp or datetime.utcnow()).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO exercises (timestamp, user_id, exercise_type, duration_minutes, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (ts, user_id, exercise_type, duration_minutes, notes),
        )
        conn.commit()
        return cur.lastrowid


def get_recent_exercises(
    limit: int = 10, user_id: Optional[int] = None,
) -> list[sqlite3.Row]:
    init_db()
    with get_connection() as conn:
        if user_id is not None:
            cur = conn.execute(
                "SELECT * FROM exercises WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM exercises ORDER BY id DESC LIMIT ?", (limit,),
            )
        return list(cur.fetchall())


# ---------------------------------------------------------------------------
# User settings
# ---------------------------------------------------------------------------

_SETTINGS_DEFAULTS = {
    "timezone": "UTC",
    "reminder_noon": "12:00",
    "reminder_night": "21:00",
}


def get_user_settings(user_id: int) -> dict:
    init_db()
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,),
        )
        row = cur.fetchone()
        if row:
            return dict(row)
    return {"user_id": user_id, **_SETTINGS_DEFAULTS}


def set_user_settings(user_id: int, **kwargs) -> None:
    init_db()
    current = get_user_settings(user_id)
    current.update(kwargs)
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO user_settings "
            "(user_id, timezone, reminder_noon, reminder_night) "
            "VALUES (?, ?, ?, ?)",
            (
                user_id,
                current.get("timezone", "UTC"),
                current.get("reminder_noon", "12:00"),
                current.get("reminder_night", "21:00"),
            ),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Sessions (resilient state)
# ---------------------------------------------------------------------------

def save_session(user_id: int, flow: str, step: str, data: dict) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions "
            "(user_id, flow, step, data, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, flow, step, json.dumps(data), ts),
        )
        conn.commit()


def load_session(user_id: int) -> Optional[dict]:
    """Return session dict or None. Deserialises the JSON data field."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM sessions WHERE user_id = ?", (user_id,),
        )
        row = cur.fetchone()
        if row:
            return {
                "flow": row["flow"],
                "step": row["step"],
                "data": json.loads(row["data"]),
            }
    return None


def delete_session(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# Streak
# ---------------------------------------------------------------------------

def get_logging_streak(user_id: int) -> int:
    """Count consecutive days (ending today or yesterday) with at least one log."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT DISTINCT DATE(timestamp) as log_date FROM logs "
            "WHERE user_id = ? ORDER BY log_date DESC",
            (user_id,),
        )
        dates = [row["log_date"] for row in cur.fetchall()]

    if not dates:
        return 0

    streak = 0
    today = date.today()
    expected = today

    for d_str in dates:
        d = date.fromisoformat(d_str)
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif streak == 0 and d == today - timedelta(days=1):
            expected = d
            streak = 1
            expected -= timedelta(days=1)
        else:
            break
    return streak


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def backup_db(backup_dir: Optional[Path] = None) -> Path:
    """Copy tracker.db to a timestamped backup. Keep the newest 7."""
    if backup_dir is None:
        backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"tracker_{ts}.db"
    shutil.copy2(DB_PATH, dest)

    backups = sorted(
        backup_dir.glob("tracker_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[7:]:
        old.unlink()
    return dest


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_logs_csv(
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Return CSV string of all logs for user within optional date range."""
    init_db()
    with get_connection() as conn:
        query = "SELECT * FROM logs WHERE user_id = ?"
        params: list = [user_id]
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        if end_date:
            query += " AND timestamp < ?"
            params.append(end_date)
        query += " ORDER BY timestamp ASC"
        cur = conn.execute(query, params)
        rows = cur.fetchall()

    if not rows:
        return ""

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(rows[0].keys())
    for row in rows:
        writer.writerow(tuple(row))
    return output.getvalue()
