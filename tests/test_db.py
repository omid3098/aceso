"""Tests for db.py – SQLite health-log layer with medications, exercises, settings, etc."""
import json
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path

import pytest

import db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own fresh database file."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_tracker.db")


# ── get_connection ────────────────────────────────────────────────────────────

def test_get_connection_returns_connection():
    db.init_db()
    conn = db.get_connection()
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_get_connection_row_factory():
    db.init_db()
    db.insert_log(user_id=7)
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM logs LIMIT 1").fetchone()
    assert isinstance(row, sqlite3.Row)
    assert row["user_id"] == 7


# ── init_db ───────────────────────────────────────────────────────────────────

def test_init_db_creates_logs_table():
    db.init_db()
    with db.get_connection() as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='logs'"
        )
        assert cur.fetchone() is not None


def test_init_db_creates_all_tables():
    db.init_db()
    with db.get_connection() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    for expected in ("logs", "medications", "exercises", "user_settings", "sessions"):
        assert expected in tables


def test_init_db_creates_beverage_log_table():
    db.init_db()
    with db.get_connection() as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='beverage_log'"
        )
        assert cur.fetchone() is not None


def test_beverage_log_table_has_expected_columns():
    db.init_db()
    with db.get_connection() as conn:
        cur = conn.execute("PRAGMA table_info(beverage_log)")
        columns = {row[1] for row in cur.fetchall()}
    expected = {"id", "user_id", "beverage_id", "servings", "water_ml",
                "caffeine_mg", "sugar_g", "calories", "date", "timestamp"}
    assert expected == columns


def test_init_db_is_idempotent():
    db.init_db()
    db.init_db()
    with db.get_connection() as conn:
        count = conn.execute("SELECT count(*) FROM logs").fetchone()[0]
    assert count == 0


# ── insert_log ────────────────────────────────────────────────────────────────

def test_insert_log_returns_integer_id():
    db.init_db()
    row_id = db.insert_log(user_id=1)
    assert isinstance(row_id, int)
    assert row_id >= 1


def test_insert_log_ids_are_incremented():
    db.init_db()
    id1 = db.insert_log(user_id=1)
    id2 = db.insert_log(user_id=2)
    assert id2 > id1


def test_insert_log_minimal_fields_stored():
    db.init_db()
    row_id = db.insert_log(user_id=42)
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM logs WHERE id=?", (row_id,)).fetchone()
    assert row["user_id"] == 42
    assert row["back_pain"] is None
    assert row["notes"] is None


def test_insert_log_all_fields():
    db.init_db()
    ts = datetime(2024, 6, 1, 12, 0, 0)
    row_id = db.insert_log(
        user_id=99,
        back_pain=2,
        headache=1,
        peace_level=8,
        sleep_quality=7,
        sleep_hours=6.5,
        water_amount=1500,
        smoke_count=3,
        caffeine_amount=2,
        sitting_hours=9.5,
        screen_hours=5.0,
        food_details="eggs, toast",
        period_status=0,
        stress_level=4,
        anxiety_level=3,
        notes="test note",
        timestamp=ts,
    )
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM logs WHERE id=?", (row_id,)).fetchone()
    assert row["user_id"] == 99
    assert row["back_pain"] == 2
    assert row["headache"] == 1
    assert row["peace_level"] == 8
    assert row["sleep_quality"] == 7
    assert row["sleep_hours"] == pytest.approx(6.5)
    assert row["water_amount"] == 1500
    assert row["smoke_count"] == 3
    assert row["caffeine_amount"] == 2
    assert row["sitting_hours"] == pytest.approx(9.5)
    assert row["screen_hours"] == pytest.approx(5.0)
    assert row["food_details"] == "eggs, toast"
    assert row["period_status"] == 0
    assert row["stress_level"] == 4
    assert row["anxiety_level"] == 3
    assert row["notes"] == "test note"
    assert row["timestamp"] == "2024-06-01 12:00:00"


def test_insert_log_default_timestamp_is_recent():
    db.init_db()
    before = datetime.utcnow()
    db.insert_log(user_id=5)
    after = datetime.utcnow()

    with db.get_connection() as conn:
        row = conn.execute("SELECT timestamp FROM logs ORDER BY id DESC LIMIT 1").fetchone()
    ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
    assert before.replace(microsecond=0) <= ts <= after


def test_insert_log_nullable_fields_can_be_none():
    db.init_db()
    row_id = db.insert_log(
        user_id=10,
        back_pain=None,
        headache=None,
        peace_level=None,
        sleep_quality=None,
        water_amount=None,
        smoke_count=None,
        caffeine_amount=None,
        sitting_hours=None,
        screen_hours=None,
        food_details=None,
        period_status=None,
        stress_level=None,
        anxiety_level=None,
        notes=None,
    )
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM logs WHERE id=?", (row_id,)).fetchone()
    for field in ("back_pain", "headache", "peace_level", "sleep_quality",
                  "sleep_hours", "water_amount", "smoke_count", "caffeine_amount",
                  "sitting_hours", "screen_hours", "food_details",
                  "period_status", "stress_level", "anxiety_level", "notes"):
        assert row[field] is None


# ── get_recent_logs ───────────────────────────────────────────────────────────

def test_get_recent_logs_empty_table():
    db.init_db()
    rows = db.get_recent_logs(50)
    assert rows == []


def test_get_recent_logs_newest_first():
    db.init_db()
    id1 = db.insert_log(user_id=1)
    id2 = db.insert_log(user_id=2)
    id3 = db.insert_log(user_id=3)
    rows = db.get_recent_logs(50)
    assert rows[0]["id"] == id3
    assert rows[1]["id"] == id2
    assert rows[2]["id"] == id1


def test_get_recent_logs_respects_limit():
    db.init_db()
    for i in range(15):
        db.insert_log(user_id=i)
    rows = db.get_recent_logs(5)
    assert len(rows) == 5


def test_get_recent_logs_limit_larger_than_data():
    db.init_db()
    for i in range(3):
        db.insert_log(user_id=i)
    rows = db.get_recent_logs(100)
    assert len(rows) == 3


def test_get_recent_logs_requires_init_db():
    """get_recent_logs requires init_db to be called first."""
    db.init_db()
    rows = db.get_recent_logs(10)
    assert rows == []


def test_get_recent_logs_returns_sqlite_rows():
    db.init_db()
    db.insert_log(user_id=77)
    rows = db.get_recent_logs(1)
    assert len(rows) == 1
    assert isinstance(rows[0], sqlite3.Row)


# ── get_recent_logs per-user filtering ────────────────────────────────────────

def test_get_recent_logs_filters_by_user_id():
    db.init_db()
    db.insert_log(user_id=10, back_pain=3)
    db.insert_log(user_id=20, back_pain=7)
    db.insert_log(user_id=10, back_pain=5)

    rows = db.get_recent_logs(50, user_id=10)
    assert len(rows) == 2
    assert all(r["user_id"] == 10 for r in rows)


def test_get_recent_logs_without_user_id_returns_all():
    db.init_db()
    db.insert_log(user_id=10)
    db.insert_log(user_id=20)
    db.insert_log(user_id=30)

    rows = db.get_recent_logs(50)
    assert len(rows) == 3


def test_get_recent_logs_user_id_no_matches():
    db.init_db()
    db.insert_log(user_id=10)
    db.insert_log(user_id=20)

    rows = db.get_recent_logs(50, user_id=999)
    assert rows == []


def test_get_recent_logs_user_id_respects_limit():
    db.init_db()
    for _ in range(10):
        db.insert_log(user_id=10)
    db.insert_log(user_id=20)

    rows = db.get_recent_logs(3, user_id=10)
    assert len(rows) == 3
    assert all(r["user_id"] == 10 for r in rows)


def test_get_recent_logs_user_id_newest_first():
    db.init_db()
    id1 = db.insert_log(user_id=10, back_pain=1)
    db.insert_log(user_id=20, back_pain=9)
    id3 = db.insert_log(user_id=10, back_pain=5)

    rows = db.get_recent_logs(50, user_id=10)
    assert rows[0]["id"] == id3
    assert rows[1]["id"] == id1


# ── get_logs_by_date_range ────────────────────────────────────────────────────

def test_get_logs_by_date_range_returns_matching():
    db.init_db()
    db.insert_log(user_id=1, timestamp=datetime(2026, 3, 1, 10, 0))
    db.insert_log(user_id=1, timestamp=datetime(2026, 3, 2, 10, 0))
    db.insert_log(user_id=1, timestamp=datetime(2026, 3, 3, 10, 0))

    rows = db.get_logs_by_date_range(1, "2026-03-01", "2026-03-03")
    assert len(rows) == 2


def test_get_logs_by_date_range_ordered_asc():
    db.init_db()
    db.insert_log(user_id=1, timestamp=datetime(2026, 3, 2, 10, 0))
    db.insert_log(user_id=1, timestamp=datetime(2026, 3, 1, 10, 0))

    rows = db.get_logs_by_date_range(1, "2026-03-01", "2026-03-03")
    assert rows[0]["timestamp"] < rows[1]["timestamp"]


def test_get_logs_by_date_range_empty():
    db.init_db()
    rows = db.get_logs_by_date_range(1, "2026-01-01", "2026-01-02")
    assert rows == []


# ── get_today_smoke_count ─────────────────────────────────────────────────────

def test_get_today_smoke_count_sums():
    db.init_db()
    db.insert_log(user_id=1, smoke_count=3, timestamp=datetime(2026, 3, 1, 8, 0))
    db.insert_log(user_id=1, smoke_count=2, timestamp=datetime(2026, 3, 1, 14, 0))
    db.insert_log(user_id=1, smoke_count=5, timestamp=datetime(2026, 3, 2, 8, 0))

    assert db.get_today_smoke_count(1, "2026-03-01") == 5
    assert db.get_today_smoke_count(1, "2026-03-02") == 5


def test_get_today_smoke_count_zero_when_none():
    db.init_db()
    assert db.get_today_smoke_count(1, "2026-03-01") == 0


# ── delete_last_log ───────────────────────────────────────────────────────────

def test_delete_last_log_removes_latest():
    db.init_db()
    db.insert_log(user_id=1, back_pain=3)
    db.insert_log(user_id=1, back_pain=7)

    assert db.delete_last_log(1) is True
    rows = db.get_recent_logs(50, user_id=1)
    assert len(rows) == 1
    assert rows[0]["back_pain"] == 3


def test_delete_last_log_returns_false_when_empty():
    db.init_db()
    assert db.delete_last_log(999) is False


def test_update_log():
    db.init_db()
    log_id = db.insert_log(user_id=1, back_pain=8)
    assert db.update_log(log_id, back_pain=3)
    logs = db.get_recent_logs(1, user_id=1)
    assert logs[0]["back_pain"] == 3


def test_update_log_no_kwargs():
    db.init_db()
    assert db.update_log(999) is False


# ── Medications ───────────────────────────────────────────────────────────────

def test_insert_medication_returns_id():
    db.init_db()
    mid = db.insert_medication(user_id=1, name="Ibuprofen")
    assert isinstance(mid, int) and mid >= 1


def test_insert_medication_stores_fields():
    db.init_db()
    mid = db.insert_medication(user_id=1, name="Aspirin", dosage="200mg", notes="test")
    rows = db.get_recent_medications(10, user_id=1)
    assert len(rows) == 1
    assert rows[0]["name"] == "Aspirin"
    assert rows[0]["dosage"] == "200mg"
    assert rows[0]["notes"] == "test"


def test_get_recent_medications_empty():
    db.init_db()
    assert db.get_recent_medications(10, user_id=1) == []


def test_get_medications_by_date_range():
    db.init_db()
    db.insert_medication(user_id=1, name="A", timestamp=datetime(2026, 3, 1, 10, 0))
    db.insert_medication(user_id=1, name="B", timestamp=datetime(2026, 3, 2, 10, 0))
    db.insert_medication(user_id=1, name="C", timestamp=datetime(2026, 3, 3, 10, 0))

    rows = db.get_medications_by_date_range(1, "2026-03-01", "2026-03-03")
    assert len(rows) == 2


# ── Exercises ─────────────────────────────────────────────────────────────────

def test_insert_exercise_returns_id():
    db.init_db()
    eid = db.insert_exercise(user_id=1, exercise_type="Walking", duration_minutes=30)
    assert isinstance(eid, int) and eid >= 1


def test_insert_exercise_stores_fields():
    db.init_db()
    db.insert_exercise(user_id=1, exercise_type="Gym", duration_minutes=60, notes="leg day")
    rows = db.get_recent_exercises(10, user_id=1)
    assert len(rows) == 1
    assert rows[0]["exercise_type"] == "Gym"
    assert rows[0]["duration_minutes"] == 60


def test_get_recent_exercises_empty():
    db.init_db()
    assert db.get_recent_exercises(10, user_id=1) == []


# ── User settings ─────────────────────────────────────────────────────────────

def test_get_user_settings_defaults():
    db.init_db()
    s = db.get_user_settings(1)
    assert s["timezone"] == "UTC"
    assert s["reminder_noon"] == "12:00"
    assert s["reminder_night"] == "21:00"


def test_set_and_get_user_settings():
    db.init_db()
    db.set_user_settings(1, timezone="Asia/Tehran", reminder_noon="13:00")
    s = db.get_user_settings(1)
    assert s["timezone"] == "Asia/Tehran"
    assert s["reminder_noon"] == "13:00"
    assert s["reminder_night"] == "21:00"


def test_set_user_settings_update():
    db.init_db()
    db.set_user_settings(1, timezone="UTC")
    db.set_user_settings(1, timezone="Europe/London")
    s = db.get_user_settings(1)
    assert s["timezone"] == "Europe/London"


# ── Sessions ──────────────────────────────────────────────────────────────────

def test_save_and_load_session():
    db.init_db()
    db.save_session(1, "log", "back_pain", {"sleep_quality": 7})
    sess = db.load_session(1)
    assert sess is not None
    assert sess["flow"] == "log"
    assert sess["step"] == "back_pain"
    assert sess["data"]["sleep_quality"] == 7


def test_load_session_returns_none_when_missing():
    db.init_db()
    assert db.load_session(999) is None


def test_delete_session():
    db.init_db()
    db.save_session(1, "log", "water_amount", {})
    db.delete_session(1)
    assert db.load_session(1) is None


def test_save_session_overwrites():
    db.init_db()
    db.save_session(1, "log", "sleep_quality", {})
    db.save_session(1, "log", "back_pain", {"sleep_quality": 5})
    sess = db.load_session(1)
    assert sess["step"] == "back_pain"


# ── Streak ────────────────────────────────────────────────────────────────────

def test_streak_empty():
    db.init_db()
    assert db.get_logging_streak(1) == 0


def test_streak_consecutive():
    db.init_db()
    today = date.today()
    for i in range(3):
        day = today - timedelta(days=i)
        db.insert_log(user_id=1, timestamp=datetime(day.year, day.month, day.day, 12, 0))
    assert db.get_logging_streak(1) == 3


def test_streak_gap_breaks():
    db.init_db()
    today = date.today()
    db.insert_log(user_id=1, timestamp=datetime(today.year, today.month, today.day, 12, 0))
    gap_day = today - timedelta(days=2)
    db.insert_log(user_id=1, timestamp=datetime(gap_day.year, gap_day.month, gap_day.day, 12, 0))
    assert db.get_logging_streak(1) == 1


# ── Backup ────────────────────────────────────────────────────────────────────

def test_backup_db_creates_file(tmp_path):
    db.init_db()
    db.insert_log(user_id=1)
    backup_dir = tmp_path / "backups"
    dest = db.backup_db(backup_dir)
    assert dest.exists()
    assert "tracker_" in dest.name


def test_backup_rotates(tmp_path):
    db.init_db()
    backup_dir = tmp_path / "backups"
    for _ in range(35):
        db.backup_db(backup_dir)
    backups = list(backup_dir.glob("tracker_*.db"))
    assert len(backups) <= 30


# ── Export ────────────────────────────────────────────────────────────────────

def test_export_logs_csv_empty():
    db.init_db()
    assert db.export_logs_csv(999) == ""


def test_export_logs_csv_has_header_and_data():
    db.init_db()
    db.insert_log(user_id=1, back_pain=5)
    csv_str = db.export_logs_csv(1)
    lines = csv_str.strip().split("\n")
    assert len(lines) == 2
    assert "back_pain" in lines[0]


def test_export_logs_csv_date_filter():
    db.init_db()
    db.insert_log(user_id=1, timestamp=datetime(2026, 1, 1, 10, 0))
    db.insert_log(user_id=1, timestamp=datetime(2026, 6, 1, 10, 0))
    csv_str = db.export_logs_csv(1, start_date="2026-05-01")
    lines = csv_str.strip().split("\n")
    assert len(lines) == 2


# ── Migrations ────────────────────────────────────────────────────────────────

def test_migration_adds_missing_columns():
    db.init_db()
    with db.get_connection() as conn:
        cursor = conn.execute("PRAGMA table_info(logs)")
        col_names = {row[1] for row in cursor.fetchall()}
    assert "stress_level" in col_names
    assert "anxiety_level" in col_names
    assert "sleep_hours" in col_names


def test_migration_adds_new_columns():
    db.init_db()
    with db.get_connection() as conn:
        cursor = conn.execute("PRAGMA table_info(logs)")
        col_names = {row[1] for row in cursor.fetchall()}
    for col in ("phone_hours", "computer_hours", "back_patch",
                "heater_hours", "massage_type", "heavy_lifting_kg",
                "tea_count", "water_glasses", "ovulation_status", "knitting_hours"):
        assert col in col_names, f"Missing column: {col}"


# ── insert_log new fields ────────────────────────────────────────────────────

def test_insert_log_new_fields():
    db.init_db()
    row_id = db.insert_log(
        user_id=1,
        phone_hours=3.5,
        computer_hours=6.0,
        back_patch=1,
        heater_hours=2.0,
        massage_type="firm",
        heavy_lifting_kg=10.0,
    )
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM logs WHERE id=?", (row_id,)).fetchone()
    assert row["phone_hours"] == pytest.approx(3.5)
    assert row["computer_hours"] == pytest.approx(6.0)
    assert row["back_patch"] == 1
    assert row["heater_hours"] == pytest.approx(2.0)
    assert row["massage_type"] == "firm"
    assert row["heavy_lifting_kg"] == pytest.approx(10.0)


def test_insert_log_half_smoke_count():
    db.init_db()
    row_id = db.insert_log(user_id=1, smoke_count=0.5)
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM logs WHERE id=?", (row_id,)).fetchone()
    assert row["smoke_count"] == pytest.approx(0.5)


# ── get_today_smoke_count with decimals ──────────────────────────────────────

def test_get_today_smoke_count_half_units():
    db.init_db()
    db.insert_log(user_id=1, smoke_count=0.5, timestamp=datetime(2026, 3, 1, 8, 0))
    db.insert_log(user_id=1, smoke_count=0.5, timestamp=datetime(2026, 3, 1, 10, 0))
    db.insert_log(user_id=1, smoke_count=0.5, timestamp=datetime(2026, 3, 1, 14, 0))
    total = db.get_today_smoke_count(1, "2026-03-01")
    assert total == pytest.approx(1.5)


# ── get_today_patch_count ────────────────────────────────────────────────────

def test_get_today_patch_count_sums():
    db.init_db()
    db.insert_log(user_id=1, back_patch=1, timestamp=datetime(2026, 3, 1, 8, 0))
    db.insert_log(user_id=1, back_patch=1, timestamp=datetime(2026, 3, 1, 14, 0))
    db.insert_log(user_id=1, back_patch=1, timestamp=datetime(2026, 3, 2, 8, 0))
    assert db.get_today_patch_count(1, "2026-03-01") == 2
    assert db.get_today_patch_count(1, "2026-03-02") == 1


def test_get_today_patch_count_zero_when_none():
    db.init_db()
    assert db.get_today_patch_count(1, "2026-03-01") == 0


def test_get_today_tea_count_sums():
    db.init_db()
    db.insert_log(user_id=1, tea_count=1, timestamp=datetime(2026, 3, 1, 8, 0))
    db.insert_log(user_id=1, tea_count=1, timestamp=datetime(2026, 3, 1, 14, 0))
    db.insert_log(user_id=1, tea_count=2, timestamp=datetime(2026, 3, 2, 8, 0))
    assert db.get_today_tea_count(1, "2026-03-01") == 2
    assert db.get_today_tea_count(1, "2026-03-02") == 2


def test_get_today_tea_count_zero_when_none():
    db.init_db()
    assert db.get_today_tea_count(1, "2026-03-01") == 0


def test_get_today_water_glasses_sums():
    db.init_db()
    db.insert_log(user_id=1, water_glasses=0.5, timestamp=datetime(2026, 3, 1, 8, 0))
    db.insert_log(user_id=1, water_glasses=0.5, timestamp=datetime(2026, 3, 1, 14, 0))
    db.insert_log(user_id=1, water_glasses=1.0, timestamp=datetime(2026, 3, 2, 8, 0))
    assert db.get_today_water_glasses(1, "2026-03-01") == pytest.approx(1.0)
    assert db.get_today_water_glasses(1, "2026-03-02") == pytest.approx(1.0)


def test_get_today_water_glasses_zero_when_none():
    db.init_db()
    assert db.get_today_water_glasses(1, "2026-03-01") == 0


def test_has_today_sleep_data_true():
    db.init_db()
    db.insert_log(user_id=1, sleep_quality=7, timestamp=datetime(2026, 3, 1, 12, 0))
    assert db.has_today_sleep_data(1, "2026-03-01") is True


def test_has_today_sleep_data_false_no_logs():
    db.init_db()
    assert db.has_today_sleep_data(1, "2026-03-01") is False


def test_has_today_sleep_data_false_no_sleep():
    db.init_db()
    db.insert_log(user_id=1, back_pain=5, timestamp=datetime(2026, 3, 1, 12, 0))
    assert db.has_today_sleep_data(1, "2026-03-01") is False


def test_insert_log_tea_water_ovulation_knitting():
    db.init_db()
    row_id = db.insert_log(
        user_id=1,
        tea_count=2,
        water_glasses=1.5,
        ovulation_status=1,
        knitting_hours=3.0,
    )
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM logs WHERE id=?", (row_id,)).fetchone()
    assert row["tea_count"] == 2
    assert row["water_glasses"] == pytest.approx(1.5)
    assert row["ovulation_status"] == 1
    assert row["knitting_hours"] == pytest.approx(3.0)
