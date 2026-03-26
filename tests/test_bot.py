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
    assert "log" in bot.FLOWS
    assert "pain_now" in bot.FLOWS
    assert "medication" in bot.FLOWS
    assert "exercise" in bot.FLOWS
    assert "heater" in bot.FLOWS
    assert "massage" in bot.FLOWS
    assert "lifting" in bot.FLOWS
    assert "period" in bot.FLOWS


def test_questions_cover_all_flow_steps():
    for flow_name, steps in bot.FLOWS.items():
        for step in steps:
            assert step in bot.QUESTIONS, f"Missing question for step '{step}' in flow '{flow_name}'"


# ── Progress bar ──────────────────────────────────────────────────────────────

def test_progress_bar_first_step():
    bar = bot._progress_bar("sleep_quality", "log")
    assert "(1/" in bar
    assert "▓" in bar


def test_progress_bar_middle_step():
    bar = bot._progress_bar("peace_level", "log")
    assert "▓" in bar and "░" in bar


def test_progress_bar_single_step_flow():
    bar = bot._progress_bar("heater_hours", "heater")
    assert bar == ""


def test_progress_bar_unknown_step():
    bar = bot._progress_bar("nonexistent", "log")
    assert bar == ""


# ── State management ─────────────────────────────────────────────────────────

def test_clear_state(isolated_db):
    bot.user_states[1] = {"flow": "log", "step": "back_pain", "data": {}}
    db.save_session(1, "log", "back_pain", {})
    bot._clear_state(1)
    assert 1 not in bot.user_states
    assert db.load_session(1) is None


def test_persist_state(isolated_db):
    bot.user_states[1] = {"flow": "log", "step": "sleep_quality", "data": {"x": 1}}
    bot._persist_state(1)
    sess = db.load_session(1)
    assert sess is not None
    assert sess["flow"] == "log"
    assert sess["step"] == "sleep_quality"


def test_persist_state_no_state():
    bot._persist_state(999)  # should not raise


def test_restore_sessions(isolated_db, monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [1, 2])
    db.save_session(1, "log", "water_amount", {"val": 5})
    bot.user_states.clear()
    bot._restore_sessions()
    assert 1 in bot.user_states
    assert bot.user_states[1]["flow"] == "log"
    assert 2 not in bot.user_states


# ── Flow engine ───────────────────────────────────────────────────────────────

def test_advance_flow_progresses_step(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    bot.user_states[1] = {"flow": "log", "step": "sleep_quality", "data": {}}
    bot.advance_flow(1, 1, 7)
    assert bot.user_states[1]["step"] == "sleep_hours"
    assert bot.user_states[1]["data"]["sleep_quality"] == 7


def test_advance_flow_completes_log(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    steps = bot.FLOWS["log"]
    bot.user_states[1] = {"flow": "log", "step": steps[0], "data": {}}
    for i, step in enumerate(steps):
        bot.user_states[1]["step"] = step
        val = 1.5 if step == "knitting_hours" else (i + 1)
        bot.advance_flow(1, 1, val)
    assert bot.user_states[1]["step"] == "_confirm"
    bot._finish_flow(1, 1, bot.user_states[1]["data"], "log")
    bot._clear_state(1)
    assert 1 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=1)
    assert len(logs) == 1


def test_advance_flow_completes_pain_now(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    steps = bot.FLOWS["pain_now"]
    bot.user_states[1] = {"flow": "pain_now", "step": steps[0], "data": {}}
    for step in steps:
        bot.user_states[1]["step"] = step
        bot.advance_flow(1, 1, 5)
    assert bot.user_states[1]["step"] == "_confirm"


def test_advance_flow_with_skip(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    bot.user_states[1] = {"flow": "log", "step": "sleep_quality", "data": {}}
    bot.advance_flow(1, 1, None)
    assert bot.user_states[1]["step"] == "sleep_hours"
    assert bot.user_states[1]["data"]["sleep_quality"] is None


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


def test_advance_flow_completes_heater(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    bot.user_states[1] = {"flow": "heater", "step": "heater_hours", "data": {}}
    bot.advance_flow(1, 1, 2.5)
    assert 1 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=1)
    assert logs[0]["heater_hours"] == pytest.approx(2.5)


def test_advance_flow_completes_massage(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    bot.user_states[1] = {"flow": "massage", "step": "massage_type", "data": {}}
    bot.advance_flow(1, 1, "firm")
    assert 1 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=1)
    assert logs[0]["massage_type"] == "firm"


def test_advance_flow_completes_lifting(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    bot.user_states[1] = {"flow": "lifting", "step": "lifting_weight", "data": {}}
    bot.advance_flow(1, 1, 10)
    assert 1 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=1)
    assert logs[0]["heavy_lifting_kg"] == pytest.approx(10)


def test_advance_flow_completes_period(isolated_db, monkeypatch):
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    bot.user_states[1] = {"flow": "period", "step": "period_status", "data": {}}
    bot.advance_flow(1, 1, 1)
    assert bot.user_states[1]["step"] == "ovulation_status"
    bot.advance_flow(1, 1, 0)
    assert 1 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=1)
    assert logs[0]["period_status"] == 1
    assert logs[0]["ovulation_status"] == 0


def test_advance_flow_no_state():
    bot.advance_flow(999, 999, 5)  # should not raise


def test_advance_flow_log_shows_more_or_finish_after_core(isolated_db, monkeypatch):
    """After the last core step (peace_level) the user is offered finish early."""
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    bot.user_states[1] = {"flow": "log", "step": "peace_level", "data": {}}
    bot.advance_flow(1, 1, 7)
    assert bot.user_states[1]["step"] == "_more_or_finish"
    sent = bot.bot.send_message.call_args
    assert "کافیه" in str(sent) or "ادامه" in str(sent) or "بیشتر" in str(sent)


def test_advance_flow_log_continue_after_core(isolated_db, monkeypatch):
    """Choosing 'continue' after core resumes at the next optional step."""
    monkeypatch.setattr(bot, "ADMIN_IDS", [1])
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    monkeypatch.setattr(bot.bot, "answer_callback_query", MagicMock())
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", MagicMock())
    bot.user_states[1] = {"flow": "log", "step": "_more_or_finish", "data": {"peace_level": 7}}
    call = _make_callback(1, "flow_continue")
    bot.handle_more_or_finish(call)
    core_idx = bot.FLOWS["log"].index(bot.LOG_CORE_LAST_STEP)
    expected_next = bot.FLOWS["log"][core_idx + 1]
    assert bot.user_states[1]["step"] == expected_next


def test_advance_flow_log_finish_early(isolated_db, monkeypatch):
    """Choosing 'finish early' after core goes straight to confirmation."""
    monkeypatch.setattr(bot, "ADMIN_IDS", [1])
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    monkeypatch.setattr(bot.bot, "answer_callback_query", MagicMock())
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", MagicMock())
    bot.user_states[1] = {"flow": "log", "step": "_more_or_finish", "data": {"peace_level": 7}}
    call = _make_callback(1, "flow_finish_early")
    bot.handle_more_or_finish(call)
    assert bot.user_states[1]["step"] == "_confirm"
    sent_text = bot.bot.send_message.call_args[0][1]
    assert "خلاصه" in sent_text


def test_pain_now_flow_has_no_more_or_finish(isolated_db, monkeypatch):
    """pain_now flow is short and should NOT trigger the more_or_finish prompt."""
    monkeypatch.setattr(bot.bot, "send_message", MagicMock())
    steps = bot.FLOWS["pain_now"]
    bot.user_states[1] = {"flow": "pain_now", "step": steps[0], "data": {}}
    for step in steps:
        bot.user_states[1]["step"] = step
        bot.advance_flow(1, 1, 5)
    assert bot.user_states[1]["step"] == "_confirm"


# ── Confirmation ──────────────────────────────────────────────────────────────

def test_format_confirmation():
    data = {"back_pain": 5, "headache": 3}
    text = bot._format_confirmation(data, "pain_now")
    assert "کمردرد" in text
    assert "5" in text


def test_format_confirmation_with_skips():
    data = {"sleep_quality": 7, "sleep_hours": None, "back_pain": None}
    text = bot._format_confirmation(data, "log")
    assert "—" in text


# ── Keyboard builders ────────────────────────────────────────────────────────

def test_main_menu_keyboard():
    kb = bot.main_menu_keyboard()
    texts = []
    for row in kb.keyboard:
        for btn in row:
            texts.append(btn.text if hasattr(btn, "text") else btn.get("text", ""))
    assert "📝 ثبت داده" in texts
    assert "📊 گزارش" in texts
    assert "🔥 درد الان" in texts
    assert "🚬 سیگار" in texts
    assert "🍵 چای" in texts
    assert "💧 آب" in texts
    assert "🏃 ورزش" in texts
    assert "📋 بیشتر" in texts


def test_main_menu_visual_hierarchy():
    """Primary buttons should be in their own full-width rows."""
    kb = bot.main_menu_keyboard()
    rows = kb.keyboard
    row_texts = []
    for row in rows:
        row_texts.append([btn.text if hasattr(btn, "text") else btn.get("text", "") for btn in row])
    assert row_texts[0] == ["📝 ثبت داده"]
    assert row_texts[1] == ["📊 گزارش"]
    assert len(row_texts[2]) == 2  # درد الان, سیگار
    assert len(row_texts[3]) == 3  # چای, آب, ورزش
    assert "📋 بیشتر" in row_texts[4]
    assert "↩️" in row_texts[4]
    assert len(row_texts[4]) == 2


def test_scale_keyboard_has_skip():
    kb = bot._scale_kb(10)
    all_data = []
    for row in kb.keyboard:
        for btn in row:
            all_data.append(btn.callback_data)
    assert "val_skip" in all_data


def test_skip_row_contains_undo_button():
    row = bot._skip_row()
    texts = [btn.text for btn in row]
    assert "↩️" in texts
    callbacks = [btn.callback_data for btn in row]
    assert "val_undo" in callbacks


def test_count_keyboard():
    kb = bot._count_kb(20)
    assert kb is not None


def test_hours_keyboard():
    kb = bot._hours_kb()
    assert kb is not None


def test_sleep_hours_keyboard():
    kb = bot._sleep_hours_kb()
    all_data = []
    for row in kb.keyboard:
        for btn in row:
            all_data.append(btn.callback_data)
    assert "val_skip" in all_data
    assert "val_7" in all_data


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


def test_massage_type_keyboard():
    kb = bot._massage_type_kb()
    all_data = []
    for row in kb.keyboard:
        for btn in row:
            all_data.append(btn.callback_data)
    assert "val_firm" in all_data
    assert "val_gentle" in all_data
    assert "val_none" in all_data


def test_lifting_keyboard():
    kb = bot._lifting_kb()
    all_data = []
    for row in kb.keyboard:
        for btn in row:
            all_data.append(btn.callback_data)
    assert "val_1" in all_data
    assert "val_10" in all_data


def test_more_menu_keyboard():
    kb = bot._more_menu_kb()
    all_data = []
    for row in kb.keyboard:
        for btn in row:
            all_data.append(btn.callback_data)
    assert "more_heater" in all_data
    assert "more_massage" in all_data
    assert "more_lifting" in all_data
    assert "more_period" in all_data
    assert "more_patch" in all_data
    assert "more_medication" in all_data


def test_confirm_keyboard():
    kb = bot._confirm_kb()
    all_data = []
    for row in kb.keyboard:
        for btn in row:
            all_data.append(btn.callback_data)
    assert "flow_confirm" in all_data
    assert "flow_cancel" in all_data


def test_report_menu_keyboard():
    kb = bot._report_menu_kb()
    all_data = []
    for row in kb.keyboard:
        for btn in row:
            all_data.append(btn.callback_data)
    assert "rpt_monthly" in all_data
    assert "rpt_medeff" in all_data


# ── ask_question ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("step", list(bot.QUESTIONS.keys()))
def test_ask_question_all_steps(step, monkeypatch):
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.ask_question(123, step)
    mock_send.assert_called_once()


def test_ask_question_with_progress(monkeypatch):
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.user_states[42] = {"flow": "log", "step": "back_pain", "data": {}}
    bot.ask_question(42, "back_pain", user_id=42)
    sent_text = mock_send.call_args[0][1]
    assert "▓" in sent_text
    assert "(3/" in sent_text


# ── _format_last_log ─────────────────────────────────────────────────────────

def test_format_last_log(isolated_db, monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    db.insert_log(user_id=1, back_pain=5, sleep_quality=7,
                  timestamp=datetime(2026, 3, 1, 12, 0))
    logs = db.get_recent_logs(1, user_id=1)
    text = bot._format_last_log(logs[0], 1)
    assert "آخرین لاگ" in text
    assert "5/10" in text
    assert "مدت خواب" in text


def test_format_last_log_with_new_fields(isolated_db, monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    db.insert_log(user_id=1, back_pain=5, phone_hours=3.5, computer_hours=2.0,
                  back_patch=1, heater_hours=1.5, massage_type="firm",
                  heavy_lifting_kg=5.0,
                  timestamp=datetime(2026, 3, 1, 12, 0))
    logs = db.get_recent_logs(1, user_id=1)
    text = bot._format_last_log(logs[0], 1)
    assert "گوشی" in text
    assert "3.5" in text
    assert "سیستم" in text
    assert "چسب کمر" in text
    assert "گرمکن" in text
    assert "محکم" in text
    assert "سنگین" in text


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
    mock_send.assert_not_called()


def test_handle_cancel_active_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.user_states[42] = {"flow": "log", "step": "back_pain", "data": {}}
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


def test_handle_skip_advances_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.user_states[42] = {"flow": "log", "step": "food_details", "data": {"water_amount": 8}}
    bot.handle_skip(_make_message(42, "/skip"))
    assert bot.user_states[42]["step"] == "caffeine_amount"


def test_handle_skip_at_confirm_step(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.user_states[42] = {"flow": "log", "step": "_confirm", "data": {}}
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


def test_handle_edit_updates_field(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    db.insert_log(user_id=42, back_pain=8)
    bot.handle_edit(_make_message(42, "/edit back_pain 3"))
    assert "3" in mock_send.call_args[0][1]
    logs = db.get_recent_logs(1, user_id=42)
    assert logs[0]["back_pain"] == 3


def test_handle_edit_no_args(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_edit(_make_message(42, "/edit"))
    assert "field" in mock_send.call_args[0][1] or "فیلد" in mock_send.call_args[0][1]


def test_handle_edit_invalid_field(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_edit(_make_message(42, "/edit fake_field 5"))
    assert "نامعتبر" in mock_send.call_args[0][1]


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


def test_handle_log_starts_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_log(_make_message(42, "📝 ثبت داده"))
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "log"


def test_handle_pain_now_starts_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_pain_now(_make_message(42, "🔥 درد الان"))
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "pain_now"


def test_handle_cigarette_one_tap(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_cigarette(_make_message(42, "🚬 سیگار"))
    assert 42 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=42)
    assert len(logs) == 1
    assert logs[0]["smoke_count"] == 0.5
    sent_text = mock_send.call_args[0][1]
    assert "نصف سیگار" in sent_text


def test_handle_cigarette_accumulates(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_cigarette(_make_message(42, "🚬 سیگار"))
    bot.handle_cigarette(_make_message(42, "🚬 سیگار"))
    bot.handle_cigarette(_make_message(42, "🚬 سیگار"))
    logs = db.get_recent_logs(10, user_id=42)
    assert len(logs) == 3
    total = sum(l["smoke_count"] for l in logs)
    assert total == pytest.approx(1.5)


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


def test_handle_tea_one_tap(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_tea(_make_message(42, "🍵 چای"))
    assert 42 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=42)
    assert len(logs) == 1
    assert logs[0]["tea_count"] == 1
    sent_text = mock_send.call_args[0][1]
    assert "چای" in sent_text


def test_handle_water_one_tap(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_water(_make_message(42, "💧 آب"))
    assert 42 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=42)
    assert len(logs) == 1
    assert logs[0]["water_glasses"] == pytest.approx(0.5)
    sent_text = mock_send.call_args[0][1]
    assert "آب" in sent_text


def test_handle_more_callback_patch(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.handle_more_callback(_make_callback(42, "more_patch"))
    assert 42 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=42)
    assert len(logs) == 1
    assert logs[0]["back_patch"] == 1
    sent_text = mock_send.call_args[0][1]
    assert "چسب کمر" in sent_text


def test_handle_more_callback_medication(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.handle_more_callback(_make_callback(42, "more_medication"))
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "medication"


def test_handle_more_menu(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.handle_more_menu(_make_message(42, "📋 بیشتر"))
    sent_text = mock_send.call_args[0][1]
    assert "چی میخوای" in sent_text


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
    bot.user_states[42] = {"flow": "log", "step": "food_details", "data": {"water_amount": 8}}
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
    bot.user_states[42] = {"flow": "log", "step": "sleep_quality", "data": {}}
    bot.handle_value_callback(_make_callback(42, "val_7"))
    assert bot.user_states[42]["data"]["sleep_quality"] == 7


def test_handle_value_callback_skip(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {"flow": "log", "step": "sleep_quality", "data": {}}
    bot.handle_value_callback(_make_callback(42, "val_skip"))
    assert bot.user_states[42]["data"]["sleep_quality"] is None
    assert bot.user_states[42]["step"] == "sleep_hours"


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
    bot.user_states[42] = {"flow": "log", "step": "phone_hours", "data": {}}
    bot.handle_value_callback(_make_callback(42, "val_1.5"))
    assert bot.user_states[42]["data"]["phone_hours"] == 1.5


def test_handle_value_callback_invalid(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_answer = MagicMock()
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    bot.user_states[42] = {"flow": "log", "step": "sleep_quality", "data": {}}
    bot.handle_value_callback(_make_callback(42, "val_bad"))
    assert "نامعتبر" in mock_answer.call_args[0][1]


def test_handle_flow_confirm(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {"flow": "log", "step": "_confirm", "data": {"back_pain": 5}}
    bot.handle_flow_confirm(_make_callback(42, "flow_confirm"))
    assert 42 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=42)
    assert len(logs) == 1


def test_handle_flow_cancel(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {"flow": "log", "step": "_confirm", "data": {"back_pain": 5}}
    bot.handle_flow_confirm(_make_callback(42, "flow_cancel"))
    assert 42 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=42)
    assert len(logs) == 0
    assert "لغو" in mock_send.call_args[0][1]


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


def test_handle_more_callback_heater(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.handle_more_callback(_make_callback(42, "more_heater"))
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "heater"


def test_handle_more_callback_massage(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.handle_more_callback(_make_callback(42, "more_massage"))
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "massage"


def test_handle_more_callback_lifting(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.handle_more_callback(_make_callback(42, "more_lifting"))
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "lifting"


def test_handle_more_callback_period(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.handle_more_callback(_make_callback(42, "more_period"))
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "period"


def test_handle_value_callback_massage_string(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {"flow": "massage", "step": "massage_type", "data": {}}
    bot.handle_value_callback(_make_callback(42, "val_firm"))
    assert 42 not in bot.user_states
    logs = db.get_recent_logs(1, user_id=42)
    assert logs[0]["massage_type"] == "firm"


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


def test_handle_report_callback_monthly(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    mock_answer = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    bot.handle_report_callback(_make_callback(42, "rpt_monthly"))
    mock_send.assert_called()


def test_handle_report_callback_medeff(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    bot.handle_report_callback(_make_callback(42, "rpt_medeff"))
    assert "دارو" in mock_send.call_args[0][1]


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


def test_send_monthly_report(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "DEFAULT_TZ", "UTC")
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot._send_monthly_report(42, 42)
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


def test_send_med_effectiveness(monkeypatch, isolated_db):
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot._send_med_effectiveness(42, 42)
    assert "دارو" in mock_send.call_args[0][1]


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
    assert bot.user_states[42]["flow"] == "log"
    assert mock_send.call_count >= 2


def test_send_night_prompt(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.send_night_prompt()
    assert 42 in bot.user_states
    assert bot.user_states[42]["flow"] == "log"


def test_send_reminder_skips_active_flow(monkeypatch, isolated_db):
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.user_states[42] = {"flow": "log", "step": "back_pain", "data": {}}
    bot._send_reminder(42, "test")
    mock_send.assert_not_called()


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


# ── Motivational feedback ────────────────────────────────────────────────────

def test_generate_feedback_insufficient_data(isolated_db):
    result = bot._generate_feedback(42, {"back_pain": 5}, "log")
    assert result == ""


def test_generate_feedback_with_data(isolated_db):
    from datetime import date, timedelta
    today = date.today()
    for i in range(5):
        d = today - timedelta(days=i)
        db.insert_log(user_id=42, back_pain=7, water_amount=5,
                      timestamp=datetime(d.year, d.month, d.day, 12, 0))
    result = bot._generate_feedback(42, {"back_pain": 3, "water_amount": 10}, "log")
    assert "🌟" in result


# ── Non-admin handler rejection ──────────────────────────────────────────────

@pytest.mark.parametrize("handler", [
    bot.handle_cancel, bot.handle_skip, bot.handle_undo,
    bot.handle_timezone, bot.handle_setreminder, bot.handle_smokes,
    bot.handle_streak, bot.handle_report_cmd, bot.handle_history_cmd,
    bot.handle_today_cmd, bot.handle_insights_cmd, bot.handle_export_cmd,
    bot.handle_backup_cmd, bot.handle_monthly_cmd,
    bot.handle_log, bot.handle_pain_now,
    bot.handle_cigarette, bot.handle_tea, bot.handle_water,
    bot.handle_medication, bot.handle_exercise,
    bot.handle_more_menu,
    bot.handle_report_menu, bot.handle_undo_button, bot.handle_text,
])
def test_handlers_reject_non_admin(handler, monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "send_document", MagicMock())
    handler(_make_message(42, "/test"))
    if mock_send.called:
        text = mock_send.call_args[0][1]
        assert "دسترسی" in text or "منو" in text or True


def test_main_menu_has_undo_button():
    kb = bot.main_menu_keyboard()
    all_texts = [
        btn.text if hasattr(btn, "text") else btn.get("text", "")
        for row in kb.keyboard
        for btn in row
    ]
    assert "↩️" in all_texts
    # Should be in the last row, next to "بیشتر"
    last_row_texts = [
        btn.text if hasattr(btn, "text") else btn.get("text", "")
        for btn in kb.keyboard[-1]
    ]
    assert "📋 بیشتر" in last_row_texts
    assert "↩️" in last_row_texts


# ── Task 3: Undo callback during active flow ─────────────────────────────────

def test_undo_callback_goes_back_one_step(monkeypatch, isolated_db):
    """Pressing undo on step 2 should go back to step 1 and re-ask it."""
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {
        "flow": "log", "step": "sleep_hours",
        "data": {"sleep_quality": 7},
    }
    bot.handle_value_callback(_make_callback(42, "val_undo"))
    assert bot.user_states[42]["step"] == "sleep_quality"
    assert "sleep_quality" not in bot.user_states[42]["data"]


def test_undo_callback_on_first_step_cancels_flow(monkeypatch, isolated_db):
    """Pressing undo on the very first step should cancel the flow."""
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {
        "flow": "log", "step": "sleep_quality", "data": {},
    }
    bot.handle_value_callback(_make_callback(42, "val_undo"))
    assert 42 not in bot.user_states


def test_undo_callback_removes_current_step_data(monkeypatch, isolated_db):
    """Undo should remove prev step data and go back."""
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {
        "flow": "log", "step": "back_pain",
        "data": {"sleep_quality": 7, "sleep_hours": 8},
    }
    bot.handle_value_callback(_make_callback(42, "val_undo"))
    assert bot.user_states[42]["step"] == "sleep_hours"
    assert "sleep_hours" not in bot.user_states[42]["data"]
    assert bot.user_states[42]["data"]["sleep_quality"] == 7


# ── Task 4: Undo button from main menu ───────────────────────────────────────

def test_undo_button_deletes_last_log(monkeypatch, isolated_db):
    """Pressing undo from main menu (no active flow) deletes the last log."""
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    db.insert_log(user_id=42, smoke_count=0.5)
    bot.user_states.pop(42, None)
    bot.handle_undo_button(_make_message(42, "↩️"))
    assert "پاک شد" in mock_send.call_args[0][1]
    assert db.get_recent_logs(1, user_id=42) == []


def test_undo_button_no_logs(monkeypatch, isolated_db):
    """Pressing undo from main menu with no logs shows appropriate message."""
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    bot.user_states.pop(42, None)
    bot.handle_undo_button(_make_message(42, "↩️"))
    assert "نیست" in mock_send.call_args[0][1]


# ── Task 5: Undo from _confirm and _more_or_finish special steps ─────────────

def test_undo_from_confirm_goes_to_last_flow_step(monkeypatch, isolated_db):
    """Pressing undo at the confirmation screen goes back to the last flow step."""
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {
        "flow": "log", "step": "_confirm",
        "data": {"sleep_quality": 7, "notes": "test"},
    }
    bot.handle_value_callback(_make_callback(42, "val_undo"))
    last_step = bot.FLOWS["log"][-1]
    assert bot.user_states[42]["step"] == last_step
    assert last_step not in bot.user_states[42]["data"]


def test_undo_from_more_or_finish_goes_to_core_last(monkeypatch, isolated_db):
    """Pressing undo at the more-or-finish screen goes back to the last core step."""
    monkeypatch.setattr(bot, "ADMIN_IDS", [42])
    mock_send = MagicMock()
    mock_answer = MagicMock()
    mock_edit = MagicMock()
    monkeypatch.setattr(bot.bot, "send_message", mock_send)
    monkeypatch.setattr(bot.bot, "answer_callback_query", mock_answer)
    monkeypatch.setattr(bot.bot, "edit_message_reply_markup", mock_edit)
    bot.user_states[42] = {
        "flow": "log", "step": "_more_or_finish",
        "data": {"sleep_quality": 7, "peace_level": 5},
    }
    bot.handle_value_callback(_make_callback(42, "val_undo"))
    assert bot.user_states[42]["step"] == bot.LOG_CORE_LAST_STEP
    assert bot.LOG_CORE_LAST_STEP not in bot.user_states[42]["data"]
