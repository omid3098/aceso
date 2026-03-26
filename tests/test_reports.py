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
        "phone_hours": None, "computer_hours": None,
        "sitting_hours": None, "smoke_count": 3,
    })]
    prev_week = [_make_row({
        "back_pain": 4, "headache": None, "peace_level": None,
        "sleep_quality": 8, "sleep_hours": 8.0,
        "water_amount": None, "caffeine_amount": None,
        "phone_hours": None, "computer_hours": None,
        "sitting_hours": None, "smoke_count": 1,
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


# ── Daily summary with new fields ────────────────────────────────────────────

def test_daily_summary_with_phone_computer_hours():
    db.insert_log(user_id=1, phone_hours=3.5, computer_hours=6.0, back_pain=5)
    logs = db.get_recent_logs(10, user_id=1)
    text = reports.generate_daily_summary(logs, [], [])
    assert "گوشی" in text
    assert "3.5" in text
    assert "سیستم" in text
    assert "6.0" in text


def test_daily_summary_uses_latest_for_time_fields():
    """Multiple logs per day: sitting_hours etc. use the latest value (user re-enters total)."""
    db.insert_log(user_id=1, sitting_hours=4, phone_hours=2, computer_hours=3,
                  timestamp=datetime(2026, 3, 1, 12, 0))
    db.insert_log(user_id=1, sitting_hours=8, phone_hours=4, computer_hours=6,
                  timestamp=datetime(2026, 3, 1, 18, 0))
    logs = db.get_logs_by_date_range(1, "2026-03-01", "2026-03-02")
    text = reports.generate_daily_summary(logs, [], [])
    assert "8" in text   # sitting: latest = 8
    assert "4" in text   # phone: latest = 4
    assert "6" in text   # computer: latest = 6


def test_daily_summary_with_back_patch():
    db.insert_log(user_id=1, back_patch=1)
    db.insert_log(user_id=1, back_patch=1)
    logs = db.get_recent_logs(10, user_id=1)
    text = reports.generate_daily_summary(logs, [], [])
    assert "چسب کمر" in text
    assert "2" in text


def test_daily_summary_with_massage():
    db.insert_log(user_id=1, massage_type="gentle")
    logs = db.get_recent_logs(10, user_id=1)
    text = reports.generate_daily_summary(logs, [], [])
    assert "ماساژ" in text
    assert "آروم" in text


def test_daily_summary_with_heater():
    db.insert_log(user_id=1, heater_hours=2.5)
    logs = db.get_recent_logs(10, user_id=1)
    text = reports.generate_daily_summary(logs, [], [])
    assert "گرمکن" in text
    assert "2.5" in text


def test_daily_summary_with_lifting():
    db.insert_log(user_id=1, heavy_lifting_kg=10.0)
    logs = db.get_recent_logs(10, user_id=1)
    text = reports.generate_daily_summary(logs, [], [])
    assert "سنگین" in text
    assert "10" in text


def test_daily_summary_half_smoke_count():
    db.insert_log(user_id=1, smoke_count=0.5)
    db.insert_log(user_id=1, smoke_count=0.5)
    db.insert_log(user_id=1, smoke_count=0.5)
    logs = db.get_recent_logs(10, user_id=1)
    text = reports.generate_daily_summary(logs, [], [])
    assert "سیگار" in text
    assert "1.5" in text


# ── Weekly/monthly reports with decimal smoke count ──────────────────────────

def test_weekly_report_half_smoke_display():
    db.insert_log(user_id=1, smoke_count=0.5, back_pain=5)
    db.insert_log(user_id=1, smoke_count=0.5)
    logs = db.get_recent_logs(50, user_id=1)
    text = reports.generate_weekly_report(logs, [], [], [])
    assert "1 نخ" in text


def test_weekly_report_with_phone_hours():
    db.insert_log(user_id=1, phone_hours=4.0, computer_hours=6.0)
    logs = db.get_recent_logs(50, user_id=1)
    text = reports.generate_weekly_report(logs, [], [], [])
    assert "گوشی" in text
    assert "سیستم" in text


def test_weekly_report_averages_time_fields():
    """With 2 logs of 4h each, weekly report averages them (4)."""
    db.insert_log(user_id=1, sitting_hours=4, timestamp=datetime(2026, 3, 1, 10, 0))
    db.insert_log(user_id=1, sitting_hours=4, timestamp=datetime(2026, 3, 1, 18, 0))
    logs = db.get_logs_by_date_range(1, "2026-03-01", "2026-03-10")
    text = reports.generate_weekly_report(logs, [], [], [])
    assert "نشستن" in text or "🪑" in text
    assert "4" in text  # avg of 4 and 4 = 4


# ── Correlations with new fields ─────────────────────────────────────────────

def test_correlations_with_phone_hours():
    for i in range(10):
        phone = 8 if i % 2 == 0 else 1
        headache = 9 if i % 2 == 0 else 1
        db.insert_log(
            user_id=1,
            phone_hours=phone,
            headache=headache,
            timestamp=datetime(2026, 3, i + 1, 12, 0),
        )
    logs = db.get_recent_logs(50, user_id=1)
    insights = reports.compute_correlations(logs)
    found_phone = any("گوشی" in i for i in insights)
    assert found_phone or any("الگو" in i or "🤔" in i for i in insights)


# ── Chart generation with new fields ─────────────────────────────────────────

def test_generate_trend_chart_with_phone_hours():
    db.insert_log(user_id=1, phone_hours=3.0, timestamp=datetime(2026, 3, 1, 12, 0))
    db.insert_log(user_id=1, phone_hours=5.0, timestamp=datetime(2026, 3, 2, 12, 0))
    logs = db.get_logs_by_date_range(1, "2026-03-01", "2026-03-03")
    result = reports.generate_trend_chart(logs, ["phone_hours"])
    if reports.MATPLOTLIB_AVAILABLE:
        assert isinstance(result, bytes)


# ── Task 6: Beverage section in daily summary ─────────────────────────────────

def test_daily_summary_shows_beverages():
    beverages = [
        {"beverage_id": "tea", "servings": 2, "water_ml": 248, "caffeine_mg": 52, "sugar_g": 0, "calories": 2},
        {"beverage_id": "water", "servings": 4, "water_ml": 500, "caffeine_mg": 0, "sugar_g": 0, "calories": 0},
        {"beverage_id": "coffee", "servings": 1, "water_ml": 124, "caffeine_mg": 50, "sugar_g": 0, "calories": 1},
    ]
    result = reports.generate_daily_summary([], [], [], beverages=beverages)
    assert "نوشیدنی" in result
    assert "چای" in result
    assert "آب" in result
    assert "قهوه" in result


def test_daily_summary_no_beverages():
    result = reports.generate_daily_summary([], [], [])
    assert "نوشیدنی" not in result


# ── Task 7: Weekly/monthly reports and correlations with beverages ─────────────

def test_weekly_report_with_beverage_totals():
    logs = [{"timestamp": "2026-03-20 12:00:00", "back_pain": 3, "headache": 2,
             "sleep_quality": 7, "peace_level": 6, "sleep_hours": 7,
             "phone_hours": 2, "computer_hours": 4, "sitting_hours": 6,
             "smoke_count": None, "knitting_hours": None,
             "water_amount": None, "caffeine_amount": None,
             "tea_count": None, "water_glasses": None}]
    bev_totals = {"total_water_ml": 5000, "total_caffeine_mg": 300, "total_sugar_g": 50}
    prev_bev = {"total_water_ml": 4000, "total_caffeine_mg": 250, "total_sugar_g": 40}
    result = reports.generate_weekly_report(logs, [], [], [],
                                            beverage_totals=bev_totals, prev_beverage_totals=prev_bev)
    assert "آب" in result
    assert "کافئین" in result
    assert "قند" in result


def test_correlations_with_beverage_data():
    daily_bev = {}
    logs = []
    for i in range(8):
        day = f"2026-03-{10+i:02d}"
        daily_bev[day] = {"total_water_ml": 500 + i * 100, "total_caffeine_mg": 50 + i * 20, "total_sugar_g": 10 + i * 5}
        logs.append({"timestamp": f"{day} 12:00:00", "headache": max(1, 8 - i), "back_pain": 5})
    result = reports.compute_correlations(logs, daily_beverage=daily_bev)
    assert isinstance(result, list)
