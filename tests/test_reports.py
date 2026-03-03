"""Tests for reports.py – analytics, charts, and correlations."""
import sqlite3
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import db
import reports


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_tracker.db")
    db.init_db()


# ── generate_trend_chart ──────────────────────────────────────────────────────

def test_generate_trend_chart_returns_bytes():
    db.insert_log(user_id=1, back_pain=5, timestamp=datetime(2026, 3, 1, 12, 0))
    db.insert_log(user_id=1, back_pain=7, timestamp=datetime(2026, 3, 2, 12, 0))
    logs = db.get_logs_by_date_range(1, "2026-03-01", "2026-03-03")
    result = reports.generate_trend_chart(logs, ["back_pain"], title="Test")
    if reports.MATPLOTLIB_AVAILABLE:
        assert isinstance(result, bytes)
        assert len(result) > 100
    else:
        assert result is None


def test_generate_trend_chart_empty_logs():
    result = reports.generate_trend_chart([], ["back_pain"])
    assert result is None


def test_generate_trend_chart_multiple_fields():
    db.insert_log(user_id=1, back_pain=5, headache=3, timestamp=datetime(2026, 3, 1, 12, 0))
    db.insert_log(user_id=1, back_pain=7, headache=6, timestamp=datetime(2026, 3, 2, 12, 0))
    logs = db.get_logs_by_date_range(1, "2026-03-01", "2026-03-03")
    result = reports.generate_trend_chart(logs, ["back_pain", "headache"])
    if reports.MATPLOTLIB_AVAILABLE:
        assert isinstance(result, bytes)


def test_generate_trend_chart_with_sleep_hours():
    db.insert_log(user_id=1, sleep_hours=7.5, timestamp=datetime(2026, 3, 1, 12, 0))
    db.insert_log(user_id=1, sleep_hours=6.0, timestamp=datetime(2026, 3, 2, 12, 0))
    logs = db.get_logs_by_date_range(1, "2026-03-01", "2026-03-03")
    result = reports.generate_trend_chart(logs, ["sleep_hours"])
    if reports.MATPLOTLIB_AVAILABLE:
        assert isinstance(result, bytes)


# ── generate_weekly_report ────────────────────────────────────────────────────

def test_weekly_report_basic():
    db.insert_log(user_id=1, back_pain=5, sleep_quality=7, smoke_count=3)
    logs = db.get_recent_logs(50, user_id=1)
    text = reports.generate_weekly_report(logs, [], [], [])
    assert "گزارش هفتگی" in text
    assert "سیگار" in text


def test_weekly_report_with_trend_arrows():
    def _make_row(vals):
        mock = MagicMock()
        mock.__getitem__ = lambda self, k: vals.get(k)
        mock.get = vals.get
        return mock

    this_week = [_make_row({
        "back_pain": 7, "headache": None, "peace_level": None,
        "sleep_quality": 6, "sleep_hours": 7.0,
        "water_amount": None, "caffeine_amount": None,
        "screen_hours": None, "sitting_hours": None, "smoke_count": 3,
    })]
    prev_week = [_make_row({
        "back_pain": 4, "headache": None, "peace_level": None,
        "sleep_quality": 8, "sleep_hours": 8.0,
        "water_amount": None, "caffeine_amount": None,
        "screen_hours": None, "sitting_hours": None, "smoke_count": 1,
    })]
    text = reports.generate_weekly_report(this_week, prev_week, [], [])
    assert "گزارش هفتگی" in text


# ── generate_monthly_report ───────────────────────────────────────────────────

def test_monthly_report_no_data():
    text = reports.generate_monthly_report([], [], [], [])
    assert "ثبت نشده" in text


def test_monthly_report_basic():
    db.insert_log(user_id=1, back_pain=5, sleep_hours=7.0)
    logs = db.get_recent_logs(50, user_id=1)
    text = reports.generate_monthly_report(logs, [], [], [])
    assert "گزارش ماهانه" in text
    assert "روزهای ثبت‌شده" in text


# ── generate_daily_summary ────────────────────────────────────────────────────

def test_daily_summary_no_data():
    text = reports.generate_daily_summary([], [], [])
    assert "هنوز داده‌ای ثبت نشده" in text


def test_daily_summary_with_data():
    db.insert_log(user_id=1, back_pain=5, water_amount=8, smoke_count=2,
                  food_details="rice", sleep_hours=7.5)
    logs = db.get_recent_logs(10, user_id=1)
    text = reports.generate_daily_summary(logs, [], [])
    assert "خلاصه امروز" in text
    assert "کمردرد" in text
    assert "rice" in text


def test_daily_summary_with_meds_and_exercises():
    db.insert_log(user_id=1, back_pain=3)
    db.insert_medication(user_id=1, name="Ibuprofen")
    db.insert_exercise(user_id=1, exercise_type="Walking", duration_minutes=30)
    logs = db.get_recent_logs(10, user_id=1)
    meds = db.get_recent_medications(10, user_id=1)
    exs = db.get_recent_exercises(10, user_id=1)
    text = reports.generate_daily_summary(logs, meds, exs)
    assert "دارو" in text
    assert "ورزش" in text


# ── compute_correlations ──────────────────────────────────────────────────────

def test_correlations_too_few_days():
    for i in range(3):
        db.insert_log(user_id=1, back_pain=5, sitting_hours=8,
                      timestamp=datetime(2026, 3, i + 1, 12, 0))
    logs = db.get_recent_logs(50, user_id=1)
    insights = reports.compute_correlations(logs)
    assert any("۷ روز" in i for i in insights)


def test_correlations_finds_pattern():
    for i in range(10):
        sitting = 9 if i % 2 == 0 else 2
        pain = 8 if i % 2 == 0 else 2
        db.insert_log(
            user_id=1,
            back_pain=pain,
            sitting_hours=sitting,
            timestamp=datetime(2026, 3, i + 1, 12, 0),
        )
    logs = db.get_recent_logs(50, user_id=1)
    insights = reports.compute_correlations(logs)
    found_sitting = any("نشستن" in i for i in insights)
    assert found_sitting or any("الگو" in i or "🤔" in i for i in insights)


def test_correlations_no_pattern():
    for i in range(10):
        db.insert_log(
            user_id=1,
            back_pain=5,
            sitting_hours=5,
            sleep_quality=5,
            headache=5,
            timestamp=datetime(2026, 3, i + 1, 12, 0),
        )
    logs = db.get_recent_logs(50, user_id=1)
    insights = reports.compute_correlations(logs)
    assert len(insights) >= 1


# ── _pearson_r ────────────────────────────────────────────────────────────────

def test_pearson_r_perfect_positive():
    r = reports._pearson_r([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
    assert r == 1.0


def test_pearson_r_perfect_negative():
    r = reports._pearson_r([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])
    assert r == -1.0


def test_pearson_r_too_few():
    r = reports._pearson_r([1, 2], [3, 4])
    assert r is None


def test_pearson_r_constant_returns_none():
    r = reports._pearson_r([5, 5, 5, 5, 5], [1, 2, 3, 4, 5])
    assert r is None


# ── compute_med_effectiveness ─────────────────────────────────────────────────

def test_med_effectiveness_insufficient_data():
    text = reports.compute_med_effectiveness([], [])
    assert "داده کافی نیست" in text


def test_med_effectiveness_with_data():
    for i in range(10):
        bp = 3 if i % 2 == 0 else 7
        db.insert_log(user_id=1, back_pain=bp, headache=bp,
                      timestamp=datetime(2026, 3, i + 1, 12, 0))
    for i in range(0, 10, 2):
        db.insert_medication(user_id=1, name="Ibuprofen",
                             timestamp=datetime(2026, 3, i + 1, 12, 0))
    logs = db.get_recent_logs(50, user_id=1)
    meds = db.get_recent_medications(50, user_id=1)
    text = reports.compute_med_effectiveness(logs, meds)
    assert "Ibuprofen" in text
    assert "کمردرد" in text
