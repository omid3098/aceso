"""
SQLite database layer for health tracker logs, medications, exercises, and
user settings.
"""
import csv
import io
import json
import shutil
import sqlite3
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    back_pain INTEGER CHECK(back_pain BETWEEN 1 AND 10),
    headache INTEGER CHECK(headache BETWEEN 1 AND 10),
    peace_level INTEGER CHECK(peace_level BETWEEN 1 AND 10),
    sleep_quality INTEGER CHECK(sleep_quality BETWEEN 1 AND 10),
    sleep_hours REAL CHECK(sleep_hours >= 0 AND sleep_hours <= 24),
    water_amount INTEGER CHECK(water_amount >= 0),
    smoke_count REAL CHECK(smoke_count >= 0),
    caffeine_amount INTEGER CHECK(caffeine_amount >= 0),
    sitting_hours REAL CHECK(sitting_hours >= 0 AND sitting_hours <= 24),
    screen_hours REAL CHECK(screen_hours >= 0 AND screen_hours <= 24),
    food_details TEXT,
    period_status INTEGER CHECK(period_status IN (0, 1)),
    stress_level INTEGER CHECK(stress_level BETWEEN 1 AND 10),
    anxiety_level INTEGER CHECK(anxiety_level BETWEEN 1 AND 10),
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

CREATE TABLE IF NOT EXISTS beverage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    beverage_id TEXT NOT NULL,
    servings REAL NOT NULL DEFAULT 1,
    water_ml REAL NOT NULL,
    caffeine_mg REAL NOT NULL,
    sugar_g REAL NOT NULL,
    calories REAL NOT NULL,
    date TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
"""

BEVERAGES = {
    "water":     {"emoji": "💧", "label_fa": "آب",       "water_ml": 125, "caffeine_mg": 0,  "sugar_g": 0,  "calories": 0},
    "tea":       {"emoji": "🍵", "label_fa": "چای",      "water_ml": 124, "caffeine_mg": 26, "sugar_g": 0,  "calories": 1},
    "green_tea": {"emoji": "🍵", "label_fa": "چای سبز",  "water_ml": 124, "caffeine_mg": 15, "sugar_g": 0,  "calories": 1},
    "coffee":    {"emoji": "☕", "label_fa": "قهوه",     "water_ml": 124, "caffeine_mg": 50, "sugar_g": 0,  "calories": 1},
    "soda":      {"emoji": "🥤", "label_fa": "نوشابه",   "water_ml": 112, "caffeine_mg": 8,  "sugar_g": 13, "calories": 53},
    "na_beer":   {"emoji": "🍺", "label_fa": "آبجو",     "water_ml": 117, "caffeine_mg": 0,  "sugar_g": 4,  "calories": 18},
    "delster":   {"emoji": "🍺", "label_fa": "دلستر",    "water_ml": 112, "caffeine_mg": 0,  "sugar_g": 10, "calories": 45},
    "juice":     {"emoji": "🧃", "label_fa": "آبمیوه",   "water_ml": 110, "caffeine_mg": 0,  "sugar_g": 11, "calories": 56},
    "milk":      {"emoji": "🥛", "label_fa": "شیر",      "water_ml": 110, "caffeine_mg": 0,  "sugar_g": 6,  "calories": 78},
    "herbal":    {"emoji": "🌿", "label_fa": "دمنوش",    "water_ml": 124, "caffeine_mg": 0,  "sugar_g": 0,  "calories": 1},
}

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
        "tea_count": "INTEGER",
        "water_glasses": "REAL",
        "ovulation_status": "INTEGER",
        "knitting_hours": "REAL",
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
        conn.execute("PRAGMA journal_mode=WAL")
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
    ovulation_status: Optional[int] = None,
    stress_level: Optional[int] = None,
    anxiety_level: Optional[int] = None,
    back_patch: Optional[int] = None,
    heater_hours: Optional[float] = None,
    massage_type: Optional[str] = None,
    heavy_lifting_kg: Optional[float] = None,
    tea_count: Optional[int] = None,
    water_glasses: Optional[float] = None,
    knitting_hours: Optional[float] = None,
    notes: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> int:
    """Insert a log row. Returns the new row id."""
    ts = (timestamp or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")
    # Build INSERT dynamically from provided kwargs to avoid hard-coded column lists.
    fields = {"timestamp": ts, "user_id": user_id}
    local = {
        "back_pain": back_pain, "headache": headache, "peace_level": peace_level,
        "sleep_quality": sleep_quality, "sleep_hours": sleep_hours,
        "water_amount": water_amount, "smoke_count": smoke_count,
        "caffeine_amount": caffeine_amount, "sitting_hours": sitting_hours,
        "screen_hours": screen_hours, "phone_hours": phone_hours,
        "computer_hours": computer_hours, "food_details": food_details,
        "period_status": period_status, "ovulation_status": ovulation_status,
        "stress_level": stress_level, "anxiety_level": anxiety_level,
        "back_patch": back_patch, "heater_hours": heater_hours,
        "massage_type": massage_type, "heavy_lifting_kg": heavy_lifting_kg,
        "tea_count": tea_count, "water_glasses": water_glasses,
        "knitting_hours": knitting_hours, "notes": notes,
    }
    for k, v in local.items():
        if v is not None:
            fields[k] = v
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    with get_connection() as conn:
        cur = conn.execute(
            f"INSERT INTO logs ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )
        conn.commit()
        return cur.lastrowid


def get_recent_logs(limit: int = 50, user_id: Optional[int] = None) -> list[sqlite3.Row]:
    """Return the most recent log rows (newest first)."""
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
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM logs WHERE user_id = ? AND timestamp >= ? AND timestamp < ? "
            "ORDER BY timestamp ASC",
            (user_id, start_date, end_date),
        )
        return list(cur.fetchall())


def get_today_smoke_count(user_id: int, today_str: str) -> float:
    """Sum of smoke_count for a given day (today_str like '2026-03-01')."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT COALESCE(SUM(smoke_count), 0) as total "
            "FROM logs WHERE user_id = ? AND timestamp LIKE ?",
            (user_id, f"{today_str}%"),
        )
        return cur.fetchone()["total"]


def get_today_patch_count(user_id: int, today_str: str) -> int:
    """Count of back_patch entries for a given day."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT COALESCE(SUM(back_patch), 0) as total "
            "FROM logs WHERE user_id = ? AND timestamp LIKE ?",
            (user_id, f"{today_str}%"),
        )
        return cur.fetchone()["total"]


def get_today_tea_count(user_id: int, today_str: str) -> int:
    """Sum of tea_count for a given day (today_str like '2026-03-01')."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT COALESCE(SUM(tea_count), 0) as total "
            "FROM logs WHERE user_id = ? AND timestamp LIKE ?",
            (user_id, f"{today_str}%"),
        )
        return cur.fetchone()["total"]


def get_today_water_glasses(user_id: int, today_str: str) -> float:
    """Sum of water_glasses for a given day (today_str like '2026-03-01')."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT COALESCE(SUM(water_glasses), 0) as total "
            "FROM logs WHERE user_id = ? AND timestamp LIKE ?",
            (user_id, f"{today_str}%"),
        )
        return cur.fetchone()["total"]


def insert_beverage(
    user_id: int,
    beverage_id: str,
    servings: float = 1,
    timestamp: Optional[datetime] = None,
) -> int:
    """Insert a beverage log entry. Calculates nutrition from BEVERAGES dict."""
    if beverage_id not in BEVERAGES:
        raise ValueError(f"Unknown beverage: {beverage_id}")
    bev = BEVERAGES[beverage_id]
    ts = (timestamp or datetime.now(timezone.utc))
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
    date_str = ts.strftime("%Y-%m-%d")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO beverage_log "
            "(user_id, beverage_id, servings, water_ml, caffeine_mg, sugar_g, calories, date, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id, beverage_id, servings,
                bev["water_ml"] * servings,
                bev["caffeine_mg"] * servings,
                bev["sugar_g"] * servings,
                bev["calories"] * servings,
                date_str, ts_str,
            ),
        )
        conn.commit()
        return cur.lastrowid


def get_today_beverages(user_id: int, date_str: str) -> list[sqlite3.Row]:
    """Return all beverage_log rows for a given date."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM beverage_log WHERE user_id = ? AND date = ?",
            (user_id, date_str),
        )
        return list(cur.fetchall())


def get_today_beverage_totals(user_id: int, date_str: str) -> dict:
    """Return aggregated beverage totals for a given date."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT COALESCE(SUM(water_ml), 0) as total_water_ml, "
            "COALESCE(SUM(caffeine_mg), 0) as total_caffeine_mg, "
            "COALESCE(SUM(sugar_g), 0) as total_sugar_g, "
            "COALESCE(SUM(calories), 0) as total_calories "
            "FROM beverage_log WHERE user_id = ? AND date = ?",
            (user_id, date_str),
        )
        row = cur.fetchone()
        cur2 = conn.execute(
            "SELECT beverage_id, SUM(servings) as total_servings "
            "FROM beverage_log WHERE user_id = ? AND date = ? "
            "GROUP BY beverage_id",
            (user_id, date_str),
        )
        per_beverage = {r["beverage_id"]: r["total_servings"] for r in cur2.fetchall()}
    return {
        "total_water_ml": row["total_water_ml"],
        "total_caffeine_mg": row["total_caffeine_mg"],
        "total_sugar_g": row["total_sugar_g"],
        "total_calories": row["total_calories"],
        "per_beverage": per_beverage,
    }


def get_beverages_by_date_range(user_id: int, start_date: str, end_date: str) -> list[sqlite3.Row]:
    """Return beverage_log rows within [start_date, end_date)."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM beverage_log WHERE user_id = ? AND date >= ? AND date < ? "
            "ORDER BY timestamp ASC",
            (user_id, start_date, end_date),
        )
        return list(cur.fetchall())


def get_daily_beverage_totals_by_range(user_id: int, start_date: str, end_date: str) -> dict[str, dict]:
    """Return per-day aggregated beverage totals for a date range."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT date, "
            "SUM(water_ml) as total_water_ml, "
            "SUM(caffeine_mg) as total_caffeine_mg, "
            "SUM(sugar_g) as total_sugar_g, "
            "SUM(calories) as total_calories "
            "FROM beverage_log WHERE user_id = ? AND date >= ? AND date < ? "
            "GROUP BY date",
            (user_id, start_date, end_date),
        )
        result = {}
        for row in cur.fetchall():
            result[row["date"]] = {
                "total_water_ml": row["total_water_ml"],
                "total_caffeine_mg": row["total_caffeine_mg"],
                "total_sugar_g": row["total_sugar_g"],
                "total_calories": row["total_calories"],
            }
        return result


def has_today_sleep_data(user_id: int, today_str: str) -> bool:
    """Check if sleep data was already logged today."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT 1 FROM logs WHERE user_id = ? AND timestamp LIKE ? "
            "AND sleep_quality IS NOT NULL LIMIT 1",
            (user_id, f"{today_str}%"),
        )
        return cur.fetchone() is not None


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


def update_log(log_id: int, **kwargs) -> bool:
    """Update specific fields of a log row. Returns True if updated."""
    if not kwargs:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [log_id]
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE logs SET {set_clause} WHERE id = ?", values,
        )
        conn.commit()
        return cur.rowcount > 0


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
    ts = (timestamp or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")
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
    ts = (timestamp or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")
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
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,),
        )
        row = cur.fetchone()
        if row:
            return dict(row)
    return {"user_id": user_id, **_SETTINGS_DEFAULTS}


def set_user_settings(user_id: int, **kwargs) -> None:
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
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
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
                "updated_at": row["updated_at"],
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
    """Copy tracker.db to a timestamped backup. Keep the newest 30."""
    if backup_dir is None:
        backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"tracker_{ts}.db"
    shutil.copy2(DB_PATH, dest)

    backups = sorted(
        backup_dir.glob("tracker_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[30:]:
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
