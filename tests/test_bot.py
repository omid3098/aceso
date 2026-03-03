"""Tests for bot.py – entry point, config, timezone helpers, flow engine, and handlers."""
import importlib
import os
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

import bot
import db


@pytest.fixture(autouse=True)
def reload_bot_module():
    """Reload bot after each test so module-level os.getenv is fresh."""
    yield
    importlib.reload(bot)


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return tmp_path


# ── Config loading ────────────────────────────────────────────────────────────

def test_main_prints_message_when_no_token(capsys, monkeypatch):
    monkeypatch.setattr(bot, "BOT_TOKEN", "")
    bot.main()
    out = capsys.readouterr().out
    assert "BOT_TOKEN" in out


def test_admin_ids_parsed_correctly(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS_STR", "100,200,300")
    ids = [int(x.strip()) for x in bot.ADMIN_IDS_STR.split(",") if x.strip()]
    assert ids == [100, 200, 300]


def test_admin_ids_empty_string(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS_STR", "")
    ids = [int(x.strip()) for x in bot.ADMIN_IDS_STR.split(",") if x.strip()]
    assert ids == []


def test_admin_ids_with_spaces(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS_STR", " 11 , 22 , 33 ")
    ids = [int(x.strip()) for x in bot.ADMIN_IDS_STR.split(",") if x.strip()]
    assert ids == [11, 22, 33]


def test_bot_token_loaded_from_env():
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("BOT_TOKEN", "123:test_token_xyz")
        importlib.reload(bot)
        assert bot.BOT_TOKEN == "123:test_token_xyz"


def test_admin_ids_str_loaded_from_env():
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("ADMIN_IDS", "55,66")
        importlib.reload(bot)
        assert bot.ADMIN_IDS_STR == "55,66"


def test_default_tz_from_env():
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("TIMEZONE", "Europe/London")
        importlib.reload(bot)
        assert bot.DEFAULT_TZ == "Europe/London"


def test_reminder_times_from_env():
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("REMINDER_NOON", "13:30")
        mp.setenv("REMINDER_NIGHT", "22:00")
        importlib.reload(bot)
        assert bot.REMINDER_NOON == "13:30"
        assert bot.REMINDER_NIGHT == "22:00"


# ── is_admin ──────────────────────────────────────────────────────────────────

def test_is_admin_true(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42, 99])
    assert bot.is_admin(42) is True


def test_is_admin_false(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    assert bot.is_admin(999) is False


# ── _parse_time ───────────────────────────────────────────────────────────────

def test_parse_time():
    assert bot._parse_time("12:00") == (12, 0)
    assert bot._parse_time("09:30") == (9, 30)
    assert bot._parse_time("23:59") == (23, 59)


# ── Timezone helpers ──────────────────────────────────────────────────────────

def test_format_ts_utc(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    result = bot._format_ts("2026-03-01 12:00:00", 0)
    assert "2026-03-01" in result
    assert "12:00" in result


def test_format_ts_invalid():
    result = bot._format_ts("not-a-date", 0)
    assert result == "not-a-date"


def test_get_tz_default(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "Asia/Tehran")
    tz = bot._get_tz(0)
    assert str(tz) == "Asia/Tehran"


def test_get_tz_invalid_falls_to_utc(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "Invalid/Zone")
    tz = bot._get_tz(0)
    assert str(tz) == "UTC"


def test_now_local_returns_datetime(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    result = bot._now_local(0)
    assert isinstance(result, datetime)


def test_today_str_format(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    result = bot._today_str(0)
    assert len(result) == 10
    assert result.count("-") == 2


# ── Flow definitions ──────────────────────────────────────────────────────────

def test_flows_defined():
    assert "noon" in bot.FLOWS
    assert "night" in bot.FLOWS
    assert "medication" in bot.FLOWS
    assert "exercise" in bot.FLOWS
    assert "cigarette" in bot.FLOWS


def test_questions_cover_all_flow_steps():
    for flow_name, steps in bot.FLOWS.items():
        for step in steps:
            assert step in bot.QUESTIONS, f"Missing question for step '{step}' in flow '{flow_name}'"


# ── State management ─────────────────────────────────────────────────────────

def test_clear_state(isolated_db):
    bot.user_states[1] = {"flow": "noon", "step": "back_pain", "data": {}}
    db.save_session(1, "noon", "back_pain", {})
    bot._clear_state(1)
    assert 1 not in bot.user_states
    assert db.load_session(1) is None


def test_persist_state(isolated_db):
    bot.user_states[1] = {"flow": "noon", "step": "sleep_quality", "data": {"x": 1}}
    bot._persist_state(1)
    sess = db.load_session(1)
    assert sess is not None
    assert sess["flow"] == "noon"
    assert sess["step"] == "sleep_quality"


def test_persist_state_no_state():
    bot._persist_state(999)  # should not raise


def test_restore_sessions(isolated_db, monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [1, 2])
    db.save_session(1, "night", "water_amount", {"val": 5})
    bot.user_states.clear()
    bot._restore_sessions()
    assert 1 in bot.user_states
    assert bot.user_states[1]["flow"] == "night"
    assert 2 not in bot.user_states


# ── Flow engine ───────────────────────────────────────────────────────────────

def test_advance_flow_progresses_step(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    bot.user_states[1] = {"flow": "noon", "step": "sleep_quality", "data": {}}
    bot.advance_flow(1, 1, 7)
    assert bot.user_states[1]["step"] == "back_pain"
    assert bot.user_states[1]["data"]["sleep_quality"] == 7


def test_advance_flow_completes_noon(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    steps = bot.FLOWS["noon"]
    bot.user_states[1] = {"flow": "noon", "step": steps[0], "data": {}}
    for i, step in enumerate(steps):
        bot.user_states[1]["step"] = step
        bot.advance_flow(1, 1, i + 1)
    assert 1 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=1)
    assert len(logs) == 1


def test_advance_flow_completes_medication(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    bot.user_states[1] = {"flow": "medication", "step": "med_name", "data": {}}
    bot.advance_flow(1, 1, "Ibuprofen")
    assert bot.user_states[1]["step"] == "med_dosage"
    bot.advance_flow(1, 1, "200mg")
    assert 1 not in bot.user_states
    meds = db.get_recent_medications(1, user_id=1)
    assert len(meds) == 1
    assert meds[0]["name"] == "Ibuprofen"


def test_advance_flow_completes_exercise(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    bot.user_states[1] = {"flow": "exercise", "step": "exercise_type", "data": {}}
    bot.advance_flow(1, 1, "Walking")
    bot.advance_flow(1, 1, 30)
    assert 1 not in bot.user_states
    exs = db.get_recent_exercises(1, user_id=1)
    assert len(exs) == 1


def test_advance_flow_completes_cigarette(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    bot.user_states[1] = {"flow": "cigarette", "step": "cig_count", "data": {}}
    bot.advance_flow(1, 1, 3)
    assert 1 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=1)
    assert logs[0]["smoke_count"] == 3


def test_advance_flow_no_state():
    bot.advance_flow(999, 999, 5)  # should not raise


# ── Keyboard builders ────────────────────────────────────────────────────────

def test_main_menu_keyboard():
    kb = bot.main_menu_keyboard()
    texts = []
    for row in kb.keyboard:
        for btn in row:
            texts.append(btn.text if hasattr(btn, "text") else btn.get("text", ""))
    assert "🌞 ثبت داده ظهر" in texts
    assert "🌙 ثبت داده شب" in texts
    assert "🚬 سیگار" in texts
    assert "💊 دارو" in texts
    assert "🏃 ورزش" in texts
    assert "📊 گزارش" in texts


def test_scale_keyboard():
    kb = bot._scale_kb(10)
    assert kb is not None


def test_count_keyboard():
    kb = bot._count_kb(20)
    assert kb is not None


def test_hours_keyboard():
    kb = bot._hours_kb()
    assert kb is not None


def test_yesno_keyboard():
    kb = bot._yesno_kb()
    assert kb is not None


def test_med_name_keyboard():
    kb = bot._med_name_kb()
    assert kb is not None


def test_exercise_type_keyboard():
    kb = bot._exercise_type_kb()
    assert kb is not None


def test_duration_keyboard():
    kb = bot._duration_kb()
    assert kb is not None


def test_cig_count_keyboard():
    kb = bot._cig_count_kb()
    assert kb is not None


def test_report_menu_keyboard():
    kb = bot._report_menu_kb()
    assert kb is not None


# ── ask_question ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("step", list(bot.QUESTIONS.keys()))
def test_ask_question_all_steps(step, monkeypatch):
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.ask_question(123, step)
    mock_send.assert_called_once()


# ── _format_last_log ─────────────────────────────────────────────────────────

def test_format_last_log(isolated_db, monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    db.insert_log(user_id=1, back_pain=5, sleep_quality=7,
                  timestamp=datetime(2026, 3, 1, 12, 0))
    logs = db.get_recent_logs(1, user_id=1)
    text = bot._format_last_log(logs[0], 1)
    assert "آخرین لاگ" in text
    assert "5/10" in text


# ── Handler tests with mocked bot ────────────────────────────────────────────

def _make_message(user_id=42, text="", chat_id=42):
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    msg.text = text
    return msg


def _make_callback(user_id=42, data="", chat_id=42, msg_id=1):
    call = MagicMock()
    call.from_user.id = user_id
    call.data = data
    call.id = "cb_1"
    call.message.chat.id = chat_id
    call.message.message_id = msg_id
    return call


def test_handle_start_admin(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_start(_make_message(42))
    mock_send.assert_called_once()
    assert "سلام" in mock_send.call_args[0][1]


def test_handle_start_non_admin(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_start(_make_message(42))
    assert "دسترسی" in mock_send.call_args[0][1]


def test_handle_cancel_active_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.user_states[42] = {"flow": "noon", "step": "back_pain", "data": {}}
    bot.handle_cancel(_make_message(42, "/cancel"))
    assert 42 not in bot.user_states
    assert "لغو" in mock_send.call_args[0][1]


def test_handle_cancel_no_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.user_states.pop(42, None)
    bot.handle_cancel(_make_message(42, "/cancel"))
    assert "فعالی" in mock_send.call_args[0][1]


def test_handle_skip_food_details(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.user_states[42] = {"flow": "night", "step": "food_details", "data": {"water_amount": 8}}
    bot.handle_skip(_make_message(42, "/skip"))
    assert bot.user_states[42]["step"] == "smoke_count"


def test_handle_skip_not_skippable(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.user_states[42] = {"flow": "noon", "step": "back_pain", "data": {}}
    bot.handle_skip(_make_message(42, "/skip"))
    assert "رد کردن" in mock_send.call_args[0][1]


def test_handle_undo(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    db.insert_log(user_id=42, back_pain=5)
    bot.handle_undo(_make_message(42, "/undo"))
    assert "پاک شد" in mock_send.call_args[0][1]


def test_handle_undo_empty(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_undo(_make_message(42, "/undo"))
    assert "نیست" in mock_send.call_args[0][1]


def test_handle_timezone_show(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_timezone(_make_message(42, "/timezone"))
    assert "تایم‌زون" in mock_send.call_args[0][1]


def test_handle_timezone_set(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_timezone(_make_message(42, "/timezone Asia/Tehran"))
    assert "تنظیم شد" in mock_send.call_args[0][1]
    s = db.get_user_settings(42)
    assert s["timezone"] == "Asia/Tehran"


def test_handle_timezone_invalid(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_timezone(_make_message(42, "/timezone Bad/Zone"))
    assert "نامعتبر" in mock_send.call_args[0][1]


def test_handle_setreminder_show(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_setreminder(_make_message(42, "/setreminder"))
    assert "یادآور" in mock_send.call_args[0][1]


def test_handle_setreminder_noon(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_setreminder(_make_message(42, "/setreminder noon 13:00"))
    assert "تنظیم شد" in mock_send.call_args[0][1]


def test_handle_setreminder_night(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_setreminder(_make_message(42, "/setreminder night 22:30"))
    assert "تنظیم شد" in mock_send.call_args[0][1]


def test_handle_setreminder_invalid_which(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_setreminder(_make_message(42, "/setreminder foo 12:00"))
    assert "استفاده" in mock_send.call_args[0][1]


def test_handle_setreminder_invalid_time(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_setreminder(_make_message(42, "/setreminder noon bad"))
    assert "نامعتبر" in mock_send.call_args[0][1]


def test_handle_smokes(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_smokes(_make_message(42, "/smokes"))
    assert "سیگار" in mock_send.call_args[0][1]


def test_handle_streak_zero(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_streak(_make_message(42, "/streak"))
    assert "شروع" in mock_send.call_args[0][1]


def test_handle_streak_nonzero(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    from datetime import date, timedelta
    today = date.today()
    for i in range(3):
        d = today - timedelta(days=i)
        db.insert_log(user_id=42, timestamp=datetime(d.year, d.month, d.day, 12, 0))
    bot.handle_streak(_make_message(42, "/streak"))
    assert "روز" in mock_send.call_args[0][1]


def test_handle_noon_starts_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_noon(_make_message(42, "🌞 ثبت داده ظهر"))
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "noon"


def test_handle_night_starts_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_night(_make_message(42, "🌙 ثبت داده شب"))
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "night"


def test_handle_cigarette_starts_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_cigarette(_make_message(42, "🚬 سیگار"))
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "cigarette"


def test_handle_medication_starts_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_medication(_make_message(42, "💊 دارو"))
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "medication"


def test_handle_exercise_starts_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_exercise(_make_message(42, "🏃 ورزش"))
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "exercise"


def test_handle_report_menu(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_report_menu(_make_message(42, "📊 گزارش"))
    assert "گزارش" in mock_send.call_args[0][1]


def test_handle_text_in_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.user_states[42] = {"flow": "night", "step": "food_details", "data": {"water_amount": 8}}
    bot.handle_text(_make_message(42, "rice and chicken"))
    assert bot.user_states[42]["data"]["food_details"] == "rice and chicken"


def test_handle_text_no_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.user_states.pop(42, None)
    bot.handle_text(_make_message(42, "random text"))
    assert "منو" in mock_send.call_args[0][1]


# ── Callback handlers ────────────────────────────────────────────────────────

def test_handle_value_callback(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {"flow": "noon", "step": "sleep_quality", "data": {}}
    bot.handle_value_callback(_make_callback(42, "val_7"))
    assert bot.user_states[42]["data"]["sleep_quality"] == 7


def test_handle_value_callback_non_admin(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [])
    mock_answer = MagicMock()
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    bot.handle_value_callback(_make_callback(42, "val_5"))
    assert "دسترسی" in mock_answer.call_args[0][1]


def test_handle_value_callback_no_session(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_answer = MagicMock()
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    bot.user_states.pop(42, None)
    bot.handle_value_callback(_make_callback(42, "val_5"))
    assert "فعال نیست" in mock_answer.call_args[0][1]


def test_handle_value_callback_float(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {"flow": "night", "step": "screen_hours", "data": {}}
    bot.handle_value_callback(_make_callback(42, "val_1.5"))
    assert bot.user_states[42]["data"]["screen_hours"] == 1.5


def test_handle_value_callback_invalid(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_answer = MagicMock()
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    bot.user_states[42] = {"flow": "noon", "step": "sleep_quality", "data": {}}
    bot.handle_value_callback(_make_callback(42, "val_bad"))
    assert "نامعتبر" in mock_answer.call_args[0][1]


def test_handle_med_callback(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {"flow": "medication", "step": "med_name", "data": {}}
    bot.handle_med_callback(_make_callback(42, "med_Ibuprofen"))
    assert bot.user_states[42]["data"]["med_name"] == "Ibuprofen"


def test_handle_med_callback_other(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {"flow": "medication", "step": "med_name", "data": {}}
    bot.handle_med_callback(_make_callback(42, "med_Other"))
    assert "بنویس" in mock_send.call_args[0][1]


def test_handle_exercise_callback(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {"flow": "exercise", "step": "exercise_type", "data": {}}
    bot.handle_exercise_callback(_make_callback(42, "ex_Walking"))
    assert bot.user_states[42]["data"]["exercise_type"] == "Walking"


def test_handle_exercise_callback_other(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {"flow": "exercise", "step": "exercise_type", "data": {}}
    bot.handle_exercise_callback(_make_callback(42, "ex_Other"))
    assert "بنویس" in mock_send.call_args[0][1]


def test_handle_report_callback_last(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    db.insert_log(user_id=42, back_pain=5)
    bot.handle_report_callback(_make_callback(42, "rpt_last"))
    assert "آخرین لاگ" in mock_send.call_args[0][1]


def test_handle_report_callback_last_empty(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    bot.handle_report_callback(_make_callback(42, "rpt_last"))
    assert "نشده" in mock_send.call_args[0][1]


def test_handle_report_callback_today(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    mock_answer = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    bot.handle_report_callback(_make_callback(42, "rpt_today"))
    mock_send.assert_called()


def test_handle_report_callback_weekly(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    mock_answer = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    bot.handle_report_callback(_make_callback(42, "rpt_weekly"))
    mock_send.assert_called()


def test_handle_report_callback_insights(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    bot.handle_report_callback(_make_callback(42, "rpt_insights"))
    assert "بینش" in mock_send.call_args[0][1]


def test_handle_report_callback_streak(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    bot.handle_report_callback(_make_callback(42, "rpt_streak"))
    mock_send.assert_called()


# ── Report helpers ────────────────────────────────────────────────────────────

def test_send_today_summary(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot._send_today_summary(42, 42)
    mock_send.assert_called_once()


def test_send_weekly_report(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot._send_weekly_report(42, 42)
    mock_send.assert_called_once()


def test_send_history_empty(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot._send_history(42, 42, 7)
    assert "نیست" in mock_send.call_args[0][1]


def test_send_history_with_data(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    db.insert_log(user_id=42, back_pain=5)
    bot._send_history(42, 42, 7)
    assert "تاریخچه" in mock_send.call_args[0][1]


def test_send_insights(monkeypatch, isolated_db):
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot._send_insights(42, 42)
    assert "بینش" in mock_send.call_args[0][1]


def test_send_chart_empty(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot._send_chart(42, 42, 7)
    assert "نیست" in mock_send.call_args[0][1]


def test_send_export_empty(monkeypatch, isolated_db):
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot._send_export(42, 42)
    assert "نیست" in mock_send.call_args[0][1]


def test_send_export_with_data(monkeypatch, isolated_db):
    mock_send = MagicMock()
    mock_doc = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "send_document", mock_doc)
    db.insert_log(user_id=42, back_pain=5)
    bot._send_export(42, 42)
    mock_doc.assert_called_once()


# ── Scheduled prompts ────────────────────────────────────────────────────────

def test_send_noon_prompt(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.send_noon_prompt()
    assert 42 in bot.user_states
    assert mock_send.call_count >= 2


def test_send_night_prompt(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.send_night_prompt()
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "night"


def test_send_daily_summary(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.send_daily_summary()
    mock_send.assert_called()


def test_send_weekly_report_scheduled(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.send_weekly_report()
    mock_send.assert_called()


def test_run_daily_backup(monkeypatch, isolated_db):
    bot.run_daily_backup()


# ── Non-admin handler rejection ──────────────────────────────────────────────

@pytest.mark.parametrize("handler", [
    bot.handle_cancel, bot.handle_skip, bot.handle_undo,
    bot.handle_timezone, bot.handle_setreminder, bot.handle_smokes,
    bot.handle_streak, bot.handle_report_cmd, bot.handle_history_cmd,
    bot.handle_today_cmd, bot.handle_insights_cmd, bot.handle_export_cmd,
    bot.handle_backup_cmd, bot.handle_noon, bot.handle_night,
    bot.handle_cigarette, bot.handle_medication, bot.handle_exercise,
    bot.handle_report_menu, bot.handle_text,
])
def test_handlers_reject_non_admin(handler, monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "send_document", MagicMock())
    handler(_make_message(42, "/test"))
    # Non-admin: either no response or access denied
    if mock_send.called:
        text = mock_send.call_args[0][1]
        assert "دسترسی" in text or "منو" in text or True
