"""Tests for db.py – SQLite health-log layer."""
import sqlite3
from datetime import datetime

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


def test_init_db_is_idempotent():
    db.init_db()
    db.init_db()  # must not raise
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
        water_amount=1500,
        smoke_count=3,
        caffeine_amount=2,
        sitting_hours=9.5,
        screen_hours=5.0,
        food_details="eggs, toast",
        period_status=0,
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
    assert row["water_amount"] == 1500
    assert row["smoke_count"] == 3
    assert row["caffeine_amount"] == 2
    assert row["sitting_hours"] == pytest.approx(9.5)
    assert row["screen_hours"] == pytest.approx(5.0)
    assert row["food_details"] == "eggs, toast"
    assert row["period_status"] == 0
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
        notes=None,
    )
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM logs WHERE id=?", (row_id,)).fetchone()
    for field in ("back_pain", "headache", "peace_level", "sleep_quality",
                  "water_amount", "smoke_count", "caffeine_amount",
                  "sitting_hours", "screen_hours", "food_details",
                  "period_status", "notes"):
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


def test_get_recent_logs_calls_init_db_internally():
    """get_recent_logs should work even before explicit init_db call."""
    rows = db.get_recent_logs(10)
    assert rows == []
    # Table must now exist
    with db.get_connection() as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='logs'"
        )
        assert cur.fetchone() is not None


def test_get_recent_logs_returns_sqlite_rows():
    db.init_db()
    db.insert_log(user_id=77)
    rows = db.get_recent_logs(1)
    assert len(rows) == 1
    assert isinstance(rows[0], sqlite3.Row)
