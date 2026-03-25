#!/usr/bin/env python3
"""
Health Tracker Telegram Bot
- Whitelist: only ADMIN_IDS from .env may use the bot.
- Scheduled prompts (configurable per-user times & timezone).
- Flows: unified log, pain_now, medication, exercise, cigarette count.
- Reports: daily summary, weekly/monthly report, trend charts, correlation insights.
- Resilient session state persisted to SQLite.
"""
import io
import os
import logging
import tempfile
from datetime import datetime, timedelta, date
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

import telebot
from telebot import types
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

import db as database
import reports

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip()]

DEFAULT_TZ = os.getenv("TIMEZONE", "UTC")
REMINDER_NOON = os.getenv("REMINDER_NOON", "12:00")
REMINDER_NIGHT = os.getenv("REMINDER_NIGHT", "21:00")

# pyTelegramBotAPI >=4.20 validates token format at init; use a placeholder
# so the module can still be imported for testing when BOT_TOKEN is unset.
_token_for_init = BOT_TOKEN if ":" in BOT_TOKEN else "0:placeholder"
bot = telebot.TeleBot(_token_for_init, parse_mode="HTML")

# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------

def _get_tz(user_id: int = 0):
    """Return pytz timezone for user, falling back to env default."""
    if user_id:
        settings = database.get_user_settings(user_id)
        tz_name = settings.get("timezone", DEFAULT_TZ)
    else:
        tz_name = DEFAULT_TZ
    try:
        return pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        return pytz.UTC


def _now_local(user_id: int = 0) -> datetime:
    return datetime.now(_get_tz(user_id))


def _format_ts(ts_str: str, user_id: int = 0) -> str:
    """Convert UTC timestamp string to user's local time display."""
    try:
        utc_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.UTC)
        local_dt = utc_dt.astimezone(_get_tz(user_id))
        return local_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return ts_str


def _today_str(user_id: int = 0) -> str:
    """Today's date string in user's timezone."""
    return _now_local(user_id).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Flow definitions
# ---------------------------------------------------------------------------

user_states: dict = {}

FLOWS: dict[str, list[str]] = {
    "log": [
        "sleep_quality", "sleep_hours", "back_pain", "headache",
        "peace_level",
        "water_amount", "food_details", "caffeine_amount",
        "phone_hours", "computer_hours", "sitting_hours", "knitting_hours", "notes",
    ],
    "medication": ["med_name", "med_dosage"],
    "exercise": ["exercise_type", "exercise_duration"],
    "pain_now": ["back_pain", "headache"],
    "heater": ["heater_hours"],
    "massage": ["massage_type"],
    "lifting": ["lifting_weight"],
    "period": ["period_status", "ovulation_status"],
}

# After answering the last core step in the "log" flow, the user is offered
# a shortcut to finish early instead of continuing through all optional steps.
LOG_CORE_LAST_STEP = "peace_level"

# Valid numeric ranges for callback values, used to reject spoofed data.
STEP_VALID_RANGE: dict[str, tuple[float, float]] = {
    "sleep_quality": (1, 10),
    "back_pain": (1, 10),
    "headache": (1, 10),
    "peace_level": (1, 10),
    "sleep_hours": (0, 24),
    "water_amount": (0, 50),
    "caffeine_amount": (0, 20),
    "phone_hours": (0, 24),
    "computer_hours": (0, 24),
    "sitting_hours": (0, 24),
    "knitting_hours": (0, 24),
    "heater_hours": (0, 24),
    "exercise_duration": (0, 600),
    "lifting_weight": (0, 200),
    "period_status": (0, 1),
    "ovulation_status": (0, 1),
}

QUESTIONS: dict[str, str] = {
    "sleep_quality":    "😴 <b>کیفیت خوابت دیشب چطور بود؟</b>\n(۱ = خیلی بد، ۱۰ = عالی)",
    "sleep_hours":      "⏰ <b>دیشب چند ساعت خوابیدی؟</b>",
    "back_pain":        "🦴 <b>الان کمردردت چقدره؟</b>\n(۱ = بدون درد، ۱۰ = خیلی شدید)",
    "headache":         "🤕 <b>الان سردرد داری؟</b>\n(۱ = ندارم، ۱۰ = خیلی شدید)",
    "peace_level":      "🧘 <b>حس آرامشت الان چقدره؟</b>\n(۱ = اصلاً، ۱۰ = خیلی زیاد)",
    "water_amount":     "💧 <b>امروز چند لیوان آب خوردی؟</b>",
    "food_details":     "🍽 <b>امروز چی خوردی؟</b>\n(خلاصه بنویس یا رد شو)",
    "caffeine_amount":  "☕ <b>چقدر کافئین مصرف کردی؟</b>\n(۰=هیچ، ۱=یه فنجون چای/قهوه، ۲=دوتا، ...)",
    "phone_hours":      "📱 <b>چند ساعت گوشی دستت بوده؟</b>",
    "computer_hours":   "💻 <b>چند ساعت پای سیستم بودی؟</b>",
    "sitting_hours":    "🪑 <b>چند ساعت نشستی؟</b>",
    "knitting_hours":   "🧶 <b>چند ساعت بافتنی کردی؟</b>",
    "period_status":    "🔴 <b>پریود هستی؟</b>",
    "ovulation_status": "🥚 <b>تخمک‌گذاری داری؟</b>",
    "notes":            "📝 <b>یادداشت یا نکته‌ای داری؟</b>\n(بنویس یا رد شو)",
    "med_name":         "💊 <b>چه دارویی مصرف کردی؟</b>",
    "med_dosage":       "💊 <b>دوز / توضیحات؟</b>\n(بنویس یا رد شو)",
    "exercise_type":    "🏃 <b>چه ورزشی انجام دادی؟</b>",
    "exercise_duration": "⏱ <b>چند دقیقه؟</b>",
    "heater_hours":     "🔌 <b>چند ساعت گرمکن برقی استفاده کردی؟</b>",
    "massage_type":     "💆 <b>ماساژ چطور بود؟</b>",
    "lifting_weight":   "🏋️ <b>تقریباً چند کیلو بلند کردی؟</b>",
}

STEP_LABELS: dict[str, str] = {
    "sleep_quality": "😴 خواب",
    "sleep_hours": "⏰ مدت خواب",
    "back_pain": "🦴 کمردرد",
    "headache": "🤕 سردرد",
    "peace_level": "🧘 آرامش",
    "water_amount": "💧 آب",
    "food_details": "🍽 غذا",
    "caffeine_amount": "☕ کافئین",
    "phone_hours": "📱 گوشی",
    "computer_hours": "💻 سیستم",
    "sitting_hours": "🪑 نشستن",
    "knitting_hours": "🧶 بافتنی",
    "period_status": "🔴 پریود",
    "ovulation_status": "🥚 تخمک‌گذاری",
    "notes": "📝 یادداشت",
    "heater_hours": "🔌 گرمکن",
    "massage_type": "💆 ماساژ",
    "lifting_weight": "🏋️ سنگین",
}

STEP_UNITS: dict[str, str] = {
    "sleep_quality": "/10",
    "sleep_hours": " ساعت",
    "back_pain": "/10",
    "headache": "/10",
    "peace_level": "/10",
    "water_amount": " لیوان",
    "caffeine_amount": "",
    "phone_hours": " ساعت",
    "computer_hours": " ساعت",
    "sitting_hours": " ساعت",
    "heater_hours": " ساعت",
    "lifting_weight": " کیلو",
}


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

def _skip_row() -> list[types.InlineKeyboardButton]:
    """Single skip button to append as a row to any inline keyboard."""
    return [types.InlineKeyboardButton("⏭ رد شدن", callback_data="val_skip")]


def _scale_kb(max_val: int = 10, row_size: int = 5) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=row_size)
    buttons = [types.InlineKeyboardButton(str(i), callback_data=f"val_{i}") for i in range(1, max_val + 1)]
    markup.add(*buttons)
    markup.row(*_skip_row())
    return markup


def _count_kb(max_val: int = 20, row_size: int = 7) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=row_size)
    buttons = [types.InlineKeyboardButton(str(i), callback_data=f"val_{i}") for i in range(0, max_val + 1)]
    markup.add(*buttons)
    markup.row(*_skip_row())
    return markup


def _hours_kb() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=6)
    options = [0, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    buttons = [types.InlineKeyboardButton(str(h), callback_data=f"val_{h}") for h in options]
    markup.add(*buttons)
    markup.row(*_skip_row())
    return markup


def _sleep_hours_kb() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=6)
    options = [3, 4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 10, 11, 12]
    buttons = [types.InlineKeyboardButton(str(h), callback_data=f"val_{h}") for h in options]
    markup.add(*buttons)
    markup.row(*_skip_row())
    return markup


def _yesno_kb() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("بله", callback_data="val_1"),
        types.InlineKeyboardButton("نه", callback_data="val_0"),
    )
    markup.row(*_skip_row())
    return markup


def _med_name_kb() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    meds = [
        ("ایبوپروفن", "med_Ibuprofen"),
        ("استامینوفن", "med_Acetaminophen"),
        ("آسپرین", "med_Aspirin"),
        ("سایر", "med_Other"),
    ]
    for label, data in meds:
        markup.add(types.InlineKeyboardButton(label, callback_data=data))
    return markup


def _exercise_type_kb() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    exercises = [
        ("🚶 پیاده‌روی", "ex_Walking"),
        ("🤸 کشش", "ex_Stretching"),
        ("🏋️ باشگاه", "ex_Gym"),
        ("🏊 شنا", "ex_Swimming"),
        ("🚴 دوچرخه", "ex_Cycling"),
        ("🏃 دویدن", "ex_Running"),
        ("سایر", "ex_Other"),
    ]
    for label, data in exercises:
        markup.add(types.InlineKeyboardButton(label, callback_data=data))
    return markup


def _duration_kb() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=5)
    options = [10, 15, 20, 30, 45, 60, 90, 120]
    buttons = [types.InlineKeyboardButton(f"{m}m", callback_data=f"val_{m}") for m in options]
    markup.add(*buttons)
    markup.row(*_skip_row())
    return markup


def _massage_type_kb() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("💪 محکم", callback_data="val_firm"),
        types.InlineKeyboardButton("🤲 آروم", callback_data="val_gentle"),
        types.InlineKeyboardButton("❌ نبوده", callback_data="val_none"),
    )
    return markup


def _lifting_kb() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=5)
    options = [1, 2, 3, 5, 10, 15, 20, 25, 30]
    buttons = [types.InlineKeyboardButton(f"{w}kg", callback_data=f"val_{w}") for w in options]
    markup.add(*buttons)
    return markup


def _more_menu_kb() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔌 گرمکن برقی", callback_data="more_heater"),
        types.InlineKeyboardButton("💆 ماساژ", callback_data="more_massage"),
        types.InlineKeyboardButton("🏋️ بلند کردن سنگین", callback_data="more_lifting"),
        types.InlineKeyboardButton("🔴 پریود / تخمک‌گذاری", callback_data="more_period"),
        types.InlineKeyboardButton("🩹 چسب کمر", callback_data="more_patch"),
        types.InlineKeyboardButton("💊 دارو", callback_data="more_medication"),
    )
    return markup


def _confirm_kb() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ ثبت", callback_data="flow_confirm"),
        types.InlineKeyboardButton("❌ لغو", callback_data="flow_cancel"),
    )
    return markup


def _more_or_finish_kb() -> types.InlineKeyboardMarkup:
    """Offer the user a choice to log more details or finish early."""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ همینا کافیه", callback_data="flow_finish_early"),
        types.InlineKeyboardButton("📝 ادامه بدم", callback_data="flow_continue"),
    )
    return markup


def _report_menu_kb() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 آخرین لاگ", callback_data="rpt_last"),
        types.InlineKeyboardButton("📅 امروز", callback_data="rpt_today"),
        types.InlineKeyboardButton("📊 هفتگی", callback_data="rpt_weekly"),
        types.InlineKeyboardButton("📆 ماهانه", callback_data="rpt_monthly"),
        types.InlineKeyboardButton("📈 نمودار", callback_data="rpt_chart"),
        types.InlineKeyboardButton("🔍 بینش‌ها", callback_data="rpt_insights"),
        types.InlineKeyboardButton("💊 اثربخشی دارو", callback_data="rpt_medeff"),
        types.InlineKeyboardButton("📤 خروجی CSV", callback_data="rpt_export"),
        types.InlineKeyboardButton("🔥 استریک", callback_data="rpt_streak"),
    )
    return markup


def main_menu_keyboard() -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("📝 ثبت داده"))
    markup.row(types.KeyboardButton("📊 گزارش"))
    markup.row(
        types.KeyboardButton("🔥 درد الان"),
        types.KeyboardButton("🚬 سیگار"),
    )
    markup.row(
        types.KeyboardButton("🍵 چای"),
        types.KeyboardButton("💧 آب"),
        types.KeyboardButton("🏃 ورزش"),
    )
    markup.row(types.KeyboardButton("📋 بیشتر"))
    return markup


# ---------------------------------------------------------------------------
# Flow engine
# ---------------------------------------------------------------------------

def _persist_state(user_id: int) -> None:
    state = user_states.get(user_id)
    if state:
        database.save_session(user_id, state["flow"], state["step"], state["data"])


def _clear_state(user_id: int) -> None:
    user_states.pop(user_id, None)
    database.delete_session(user_id)


def _restore_sessions() -> None:
    """Load persisted sessions into memory on bot startup."""
    for uid in ADMIN_IDS:
        sess = database.load_session(uid)
        if sess:
            user_states[uid] = sess
            logger.info("Restored session for user %s (flow=%s, step=%s)", uid, sess["flow"], sess["step"])


def _progress_bar(step: str, flow: str) -> str:
    """Return a text progress indicator like ▓▓░░ (2/4)."""
    flow_steps = FLOWS.get(flow, [])
    if len(flow_steps) <= 1:
        return ""
    try:
        idx = flow_steps.index(step)
    except ValueError:
        return ""
    total = len(flow_steps)
    filled = "▓" * (idx + 1)
    empty = "░" * (total - idx - 1)
    return f"{filled}{empty}  ({idx + 1}/{total})\n\n"


def ask_question(chat_id: int, step: str, user_id: int = 0) -> None:
    progress = ""
    if user_id and user_id in user_states:
        flow = user_states[user_id]["flow"]
        progress = _progress_bar(step, flow)
    question = progress + QUESTIONS.get(step, "")

    if step in ("sleep_quality", "back_pain", "headache", "peace_level"):
        bot.send_message(chat_id, question, reply_markup=_scale_kb(10))
    elif step == "sleep_hours":
        bot.send_message(chat_id, question, reply_markup=_sleep_hours_kb())
    elif step == "caffeine_amount":
        bot.send_message(chat_id, question, reply_markup=_count_kb(10))
    elif step == "water_amount":
        bot.send_message(chat_id, question, reply_markup=_count_kb(20))
    elif step in ("phone_hours", "computer_hours", "sitting_hours", "knitting_hours", "heater_hours"):
        bot.send_message(chat_id, question, reply_markup=_hours_kb())
    elif step in ("period_status", "ovulation_status"):
        bot.send_message(chat_id, question, reply_markup=_yesno_kb())
    elif step == "med_name":
        bot.send_message(chat_id, question, reply_markup=_med_name_kb())
    elif step == "exercise_type":
        bot.send_message(chat_id, question, reply_markup=_exercise_type_kb())
    elif step == "exercise_duration":
        bot.send_message(chat_id, question, reply_markup=_duration_kb())
    elif step == "massage_type":
        bot.send_message(chat_id, question, reply_markup=_massage_type_kb())
    elif step == "lifting_weight":
        bot.send_message(chat_id, question, reply_markup=_lifting_kb())
    else:
        skip_kb = types.InlineKeyboardMarkup()
        skip_kb.row(*_skip_row())
        bot.send_message(chat_id, question, reply_markup=skip_kb)


_MASSAGE_DISPLAY = {"firm": "💪 محکم", "gentle": "🤲 آروم", "none": "❌ نبوده"}


def _format_confirmation(data: dict, flow: str) -> str:
    """Build a summary of collected data for user confirmation."""
    steps = FLOWS.get(flow, [])
    lines = ["📋 <b>خلاصه داده‌ها:</b>\n"]
    for step in steps:
        label = STEP_LABELS.get(step, step)
        val = data.get(step)
        if step in ("period_status", "ovulation_status"):
            display = "بله" if val == 1 else ("نه" if val == 0 else "—")
            lines.append(f"{label}: {display}")
        elif step == "massage_type":
            display = _MASSAGE_DISPLAY.get(val, "—")
            lines.append(f"{label}: {display}")
        elif step in ("food_details", "notes"):
            lines.append(f"{label}: {val or '—'}")
        else:
            unit = STEP_UNITS.get(step, "")
            lines.append(f"{label}: {val}{unit}" if val is not None else f"{label}: —")
    return "\n".join(lines)


def _generate_feedback(user_id: int, data: dict, flow: str) -> str:
    """Generate motivational feedback comparing today's log to recent averages."""
    if flow not in ("log", "pain_now"):
        return ""

    recent_logs = database.get_recent_logs(30, user_id=user_id)
    if len(recent_logs) < 3:
        return ""

    feedback_parts: list[str] = []

    def _recent_avg(field):
        vals = [r[field] for r in recent_logs if r[field] is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    bp = data.get("back_pain")
    if bp is not None:
        avg = _recent_avg("back_pain")
        if avg and bp < avg - 1:
            feedback_parts.append(f"کمردردت از میانگینت ({avg}) کمتره! 💪")
        elif avg is not None and bp <= 2:
            feedback_parts.append("کمردرد خیلی کمه، عالیه! 🎉")

    wa = data.get("water_amount")
    if wa is not None:
        avg = _recent_avg("water_amount")
        if avg and wa > avg + 1:
            feedback_parts.append(f"آب بیشتری از میانگینت ({avg}) خوردی! 💧👏")

    sq = data.get("sleep_quality")
    if sq is not None and sq >= 8:
        feedback_parts.append("کیفیت خوابت عالی بوده! 😴✨")

    streak = database.get_logging_streak(user_id)
    if streak >= 7:
        feedback_parts.append(f"🔥 {streak} روز پشت سرهم ثبت داده! ادامه بده!")
    elif streak >= 3:
        feedback_parts.append(f"🔥 {streak} روز استریک!")

    if not feedback_parts:
        return ""

    return "\n\n🌟 " + "\n🌟 ".join(feedback_parts)


def _finish_flow(user_id: int, chat_id: int, data: dict, flow: str) -> None:
    """Save the completed flow data to the database."""
    if flow in ("log", "pain_now"):
        database.insert_log(
            user_id=user_id,
            back_pain=data.get("back_pain"),
            headache=data.get("headache"),
            peace_level=data.get("peace_level"),
            sleep_quality=data.get("sleep_quality"),
            sleep_hours=data.get("sleep_hours"),
            water_amount=data.get("water_amount"),
            caffeine_amount=data.get("caffeine_amount"),
            sitting_hours=data.get("sitting_hours"),
            phone_hours=data.get("phone_hours"),
            computer_hours=data.get("computer_hours"),
            knitting_hours=data.get("knitting_hours"),
            food_details=data.get("food_details"),
            period_status=data.get("period_status"),
            ovulation_status=data.get("ovulation_status"),
            notes=data.get("notes"),
        )
        feedback = _generate_feedback(user_id, data, flow)
        msg = "✅ <b>داده‌ها ثبت شدن!</b> ممنون. 🙏"
        if feedback:
            msg += feedback
        bot.send_message(chat_id, msg, reply_markup=main_menu_keyboard())
    elif flow == "medication":
        database.insert_medication(
            user_id=user_id,
            name=data.get("med_name", ""),
            dosage=data.get("med_dosage"),
        )
        bot.send_message(chat_id, "💊 <b>دارو ثبت شد!</b>", reply_markup=main_menu_keyboard())
    elif flow == "exercise":
        database.insert_exercise(
            user_id=user_id,
            exercise_type=data.get("exercise_type", ""),
            duration_minutes=data.get("exercise_duration"),
        )
        bot.send_message(chat_id, "🏃 <b>ورزش ثبت شد!</b>", reply_markup=main_menu_keyboard())
    elif flow == "heater":
        hours = data.get("heater_hours")
        database.insert_log(user_id=user_id, heater_hours=hours)
        bot.send_message(
            chat_id,
            f"🔌 <b>گرمکن برقی ثبت شد: {hours} ساعت</b>",
            reply_markup=main_menu_keyboard(),
        )
    elif flow == "massage":
        mtype = data.get("massage_type", "none")
        database.insert_log(user_id=user_id, massage_type=mtype)
        display = _MASSAGE_DISPLAY.get(mtype, mtype)
        bot.send_message(
            chat_id,
            f"💆 <b>ماساژ ثبت شد: {display}</b>",
            reply_markup=main_menu_keyboard(),
        )
    elif flow == "lifting":
        kg = data.get("lifting_weight")
        database.insert_log(user_id=user_id, heavy_lifting_kg=kg)
        bot.send_message(
            chat_id,
            f"🏋️ <b>بلند کردن سنگین ثبت شد: {kg} کیلو</b>",
            reply_markup=main_menu_keyboard(),
        )
    elif flow == "period":
        period_val = data.get("period_status")
        ovul_val = data.get("ovulation_status")
        database.insert_log(user_id=user_id, period_status=period_val, ovulation_status=ovul_val)
        period_display = "بله" if period_val == 1 else "نه"
        ovul_display = "بله" if ovul_val == 1 else ("نه" if ovul_val == 0 else "—")
        bot.send_message(
            chat_id,
            f"🔴 <b>پریود ثبت شد: {period_display}</b>\n🥚 <b>تخمک‌گذاری: {ovul_display}</b>",
            reply_markup=main_menu_keyboard(),
        )


def advance_flow(user_id: int, chat_id: int, value) -> None:
    state = user_states.get(user_id)
    if not state:
        return

    step = state["step"]
    state["data"][step] = value

    flow_steps = FLOWS[state["flow"]]
    try:
        current_idx = flow_steps.index(step)
    except ValueError:
        return

    if current_idx + 1 < len(flow_steps):
        # After the last core step in the "log" flow, offer a shortcut to finish early
        if state["flow"] == "log" and step == LOG_CORE_LAST_STEP:
            state["step"] = "_more_or_finish"
            _persist_state(user_id)
            bot.send_message(
                chat_id,
                "✅ سؤالات اصلی تموم شد!\nمیخوای جزئیات بیشتر وارد کنی؟",
                reply_markup=_more_or_finish_kb(),
            )
            return
        next_step = flow_steps[current_idx + 1]
        state["step"] = next_step
        _persist_state(user_id)
        ask_question(chat_id, next_step, user_id)
    else:
        flow = state["flow"]
        if flow in ("log", "pain_now"):
            state["step"] = "_confirm"
            _persist_state(user_id)
            summary = _format_confirmation(state["data"], flow)
            bot.send_message(chat_id, summary, reply_markup=_confirm_kb())
        else:
            _finish_flow(user_id, chat_id, state["data"], flow)
            _clear_state(user_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _format_last_log(row, user_id: int) -> str:
    def _v(key):
        try:
            return row[key]
        except (IndexError, KeyError):
            return None

    period_display = "بله" if _v("period_status") == 1 else ("نه" if _v("period_status") == 0 else "—")
    ovul = _v("ovulation_status")
    ovulation_display = "بله" if ovul == 1 else ("نه" if ovul == 0 else "—")

    phone = _v("phone_hours")
    computer = _v("computer_hours")
    screen = _v("screen_hours")
    back_patch = _v("back_patch")
    heater = _v("heater_hours")
    massage = _v("massage_type")
    lifting = _v("heavy_lifting_kg")

    lines = [
        f"📊 <b>آخرین لاگ</b>",
        f"🕐 {_format_ts(row['timestamp'], user_id)}\n",
        f"😴 کیفیت خواب: {row['sleep_quality'] or '—'}/10",
        f"⏰ مدت خواب: {row['sleep_hours'] or '—'} ساعت",
        f"🦴 کمردرد: {row['back_pain'] or '—'}/10",
        f"🤕 سردرد: {row['headache'] or '—'}/10",
        f"🧘 آرامش: {row['peace_level'] or '—'}/10\n",
        f"💧 آب: {row['water_amount'] or '—'} لیوان",
        f"🍵 چای: {_v('tea_count') or '—'} لیوان",
        f"🚬 سیگار: {row['smoke_count'] or '—'} نخ",
        f"☕ کافئین: {row['caffeine_amount'] or '—'}",
    ]

    if phone is not None or computer is not None:
        lines.append(f"📱 گوشی: {phone or '—'} ساعت")
        lines.append(f"💻 سیستم: {computer or '—'} ساعت")
    elif screen is not None:
        lines.append(f"📱 صفحه‌نمایش: {screen} ساعت")

    lines.append(f"🪑 نشستن: {row['sitting_hours'] or '—'} ساعت")
    knitting = _v("knitting_hours")
    if knitting is not None:
        lines.append(f"🧶 بافتنی: {knitting} ساعت")
    lines.append(f"🍽 غذا: {row['food_details'] or '—'}")
    lines.append(f"🔴 پریود: {period_display}")
    lines.append(f"🥚 تخمک‌گذاری: {ovulation_display}")

    if back_patch:
        lines.append(f"🩹 چسب کمر: {back_patch} بار")
    if heater is not None:
        lines.append(f"🔌 گرمکن: {heater} ساعت")
    if massage:
        lines.append(f"💆 ماساژ: {_MASSAGE_DISPLAY.get(massage, massage)}")
    if lifting is not None:
        lines.append(f"🏋️ سنگین: {lifting} کیلو")

    lines.append(f"📝 یادداشت: {row['notes'] or '—'}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

@bot.message_handler(commands=["start"])
def handle_start(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "سلام! 👋 <b>بات ردیابی سلامت</b> آماده‌ست.\nاز منوی پایین استفاده کن:",
        reply_markup=main_menu_keyboard(),
    )


@bot.message_handler(commands=["cancel"])
def handle_cancel(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    uid = message.from_user.id
    if uid in user_states:
        _clear_state(uid)
        bot.send_message(message.chat.id, "❌ عملیات لغو شد.", reply_markup=main_menu_keyboard())
    else:
        bot.send_message(message.chat.id, "الان عملیات فعالی نداری.", reply_markup=main_menu_keyboard())


@bot.message_handler(commands=["skip"])
def handle_skip(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    state = user_states.get(message.from_user.id)
    if state and state["step"] != "_confirm":
        advance_flow(message.from_user.id, message.chat.id, None)
    else:
        bot.send_message(message.chat.id, "الان چیزی برای رد کردن نداری.")


@bot.message_handler(commands=["undo"])
def handle_undo(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    if database.delete_last_log(message.from_user.id):
        bot.send_message(message.chat.id, "↩️ آخرین لاگ پاک شد.", reply_markup=main_menu_keyboard())
    else:
        bot.send_message(message.chat.id, "لاگی برای حذف نیست.")


_EDITABLE_FIELDS = {
    "back_pain", "headache", "peace_level", "sleep_quality", "sleep_hours",
    "water_amount", "caffeine_amount", "sitting_hours", "phone_hours",
    "computer_hours", "knitting_hours", "smoke_count",
}


@bot.message_handler(commands=["edit"])
def handle_edit(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        field_list = ", ".join(sorted(_EDITABLE_FIELDS))
        bot.send_message(
            message.chat.id,
            f"✏️ <b>ویرایش آخرین لاگ</b>\n\n"
            f"استفاده: <code>/edit field value</code>\n"
            f"مثال: <code>/edit back_pain 3</code>\n\n"
            f"فیلدها: <code>{field_list}</code>",
        )
        return
    field = parts[1].lower()
    if field not in _EDITABLE_FIELDS:
        bot.send_message(message.chat.id, f"❌ فیلد نامعتبر: {field}")
        return
    try:
        value = float(parts[2]) if "." in parts[2] else int(parts[2])
    except ValueError:
        bot.send_message(message.chat.id, "❌ مقدار باید عدد باشه.")
        return
    logs = database.get_recent_logs(1, user_id=message.from_user.id)
    if not logs:
        bot.send_message(message.chat.id, "لاگی برای ویرایش نیست.")
        return
    if database.update_log(logs[0]["id"], **{field: value}):
        label = STEP_LABELS.get(field, field)
        bot.send_message(
            message.chat.id,
            f"✏️ <b>{label}</b> به <b>{value}</b> تغییر کرد.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        bot.send_message(message.chat.id, "❌ ویرایش انجام نشد.")


@bot.message_handler(commands=["timezone"])
def handle_timezone(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        current = database.get_user_settings(message.from_user.id).get("timezone", DEFAULT_TZ)
        bot.send_message(
            message.chat.id,
            f"🕐 تایم‌زون فعلی: <b>{current}</b>\n\n"
            "برای تغییر: <code>/timezone Asia/Tehran</code>",
        )
        return
    tz_name = parts[1].strip()
    try:
        pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        bot.send_message(message.chat.id, f"❌ تایم‌زون نامعتبر: {tz_name}")
        return
    database.set_user_settings(message.from_user.id, timezone=tz_name)
    bot.send_message(message.chat.id, f"✅ تایم‌زون تنظیم شد: <b>{tz_name}</b>")


@bot.message_handler(commands=["setreminder"])
def handle_setreminder(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        settings = database.get_user_settings(message.from_user.id)
        bot.send_message(
            message.chat.id,
            f"⏰ یادآور ظهر: <b>{settings.get('reminder_noon', REMINDER_NOON)}</b>\n"
            f"⏰ یادآور شب: <b>{settings.get('reminder_night', REMINDER_NIGHT)}</b>\n\n"
            "تغییر: <code>/setreminder noon 13:00</code>\n"
            "یا: <code>/setreminder night 22:30</code>",
        )
        return
    which = parts[1].lower()
    time_str = parts[2].strip()
    try:
        h, m = time_str.split(":")
        int(h)
        int(m)
    except (ValueError, IndexError):
        bot.send_message(message.chat.id, "❌ فرمت نامعتبر. مثال: 13:00")
        return
    if which == "noon":
        database.set_user_settings(message.from_user.id, reminder_noon=time_str)
        bot.send_message(message.chat.id, f"✅ یادآور ظهر تنظیم شد: <b>{time_str}</b>")
    elif which == "night":
        database.set_user_settings(message.from_user.id, reminder_night=time_str)
        bot.send_message(message.chat.id, f"✅ یادآور شب تنظیم شد: <b>{time_str}</b>")
    else:
        bot.send_message(message.chat.id, "❌ استفاده: /setreminder noon|night HH:MM")


@bot.message_handler(commands=["smokes"])
def handle_smokes(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    total = database.get_today_smoke_count(message.from_user.id, _today_str(message.from_user.id))
    display = int(total) if total == int(total) else total
    bot.send_message(message.chat.id, f"🚬 سیگار امروز: <b>{display} نخ</b>")


@bot.message_handler(commands=["streak"])
def handle_streak(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    streak = database.get_logging_streak(message.from_user.id)
    if streak == 0:
        bot.send_message(message.chat.id, "🔥 هنوز استریکی نداری. شروع کن!")
    else:
        bot.send_message(message.chat.id, f"🔥 استریک: <b>{streak} روز</b> پشت سرهم!")


@bot.message_handler(commands=["report"])
def handle_report_cmd(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    days = 7
    if len(parts) > 1:
        try:
            days = int(parts[1])
        except ValueError:
            pass
    _send_chart(message.chat.id, message.from_user.id, days)


@bot.message_handler(commands=["history"])
def handle_history_cmd(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    days = 7
    if len(parts) > 1:
        try:
            days = int(parts[1])
        except ValueError:
            pass
    _send_history(message.chat.id, message.from_user.id, days)


@bot.message_handler(commands=["today"])
def handle_today_cmd(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    _send_today_summary(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["insights"])
def handle_insights_cmd(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    _send_insights(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["export"])
def handle_export_cmd(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    _send_export(message.chat.id, message.from_user.id, message.text)


@bot.message_handler(commands=["backup"])
def handle_backup_cmd(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ بله، ارسال کن", callback_data="backup_confirm"),
        types.InlineKeyboardButton("❌ لغو", callback_data="backup_cancel"),
    )
    bot.send_message(
        message.chat.id,
        "⚠️ <b>فایل کامل دیتابیس از طریق تلگرام ارسال میشه.</b>\nمطمئنی؟",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda c: c.data in ("backup_confirm", "backup_cancel"))
def handle_backup_confirm(call: types.CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "دسترسی نداری.")
        return
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    if call.data == "backup_cancel":
        bot.answer_callback_query(call.id, "❌ لغو شد")
        return
    bot.answer_callback_query(call.id, "💾 در حال بکاپ...")
    try:
        path = database.backup_db()
        with open(path, "rb") as f:
            bot.send_document(call.message.chat.id, f, caption="💾 بکاپ دیتابیس")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ خطا در بکاپ: {e}")


@bot.message_handler(commands=["monthly"])
def handle_monthly_cmd(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    _send_monthly_report(message.chat.id, message.from_user.id)


# ---------------------------------------------------------------------------
# Reply keyboard handlers
# ---------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "📝 ثبت داده")
def handle_log(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    uid = message.from_user.id
    first_step = FLOWS["log"][0]
    user_states[uid] = {"flow": "log", "step": first_step, "data": {}}
    _persist_state(uid)
    ask_question(message.chat.id, first_step, uid)


@bot.message_handler(func=lambda m: m.text == "🔥 درد الان")
def handle_pain_now(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    uid = message.from_user.id
    first_step = FLOWS["pain_now"][0]
    user_states[uid] = {"flow": "pain_now", "step": first_step, "data": {}}
    _persist_state(uid)
    ask_question(message.chat.id, first_step, uid)


@bot.message_handler(func=lambda m: m.text == "🚬 سیگار")
def handle_cigarette(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    uid = message.from_user.id
    database.insert_log(user_id=uid, smoke_count=0.5)
    today_total = database.get_today_smoke_count(uid, _today_str(uid))
    display = int(today_total) if today_total == int(today_total) else today_total
    bot.send_message(
        message.chat.id,
        f"🚬 <b>نصف سیگار ثبت شد.</b>\nامروز: {display} نخ",
        reply_markup=main_menu_keyboard(),
    )


@bot.message_handler(func=lambda m: m.text == "🍵 چای")
def handle_tea(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    uid = message.from_user.id
    database.insert_log(user_id=uid, tea_count=1)
    today_total = database.get_today_tea_count(uid, _today_str(uid))
    bot.send_message(
        message.chat.id,
        f"🍵 <b>یک لیوان چای ثبت شد.</b>\nامروز: {today_total} لیوان",
        reply_markup=main_menu_keyboard(),
    )


@bot.message_handler(func=lambda m: m.text == "💧 آب")
def handle_water(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    uid = message.from_user.id
    database.insert_log(user_id=uid, water_glasses=0.5)
    today_total = database.get_today_water_glasses(uid, _today_str(uid))
    display = int(today_total) if today_total == int(today_total) else today_total
    bot.send_message(
        message.chat.id,
        f"💧 <b>نیم لیوان آب ثبت شد.</b>\nامروز: {display} لیوان",
        reply_markup=main_menu_keyboard(),
    )


@bot.message_handler(func=lambda m: m.text == "💊 دارو")
def handle_medication(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    user_states[message.from_user.id] = {"flow": "medication", "step": "med_name", "data": {}}
    _persist_state(message.from_user.id)
    ask_question(message.chat.id, "med_name", message.from_user.id)


@bot.message_handler(func=lambda m: m.text == "🏃 ورزش")
def handle_exercise(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    user_states[message.from_user.id] = {"flow": "exercise", "step": "exercise_type", "data": {}}
    _persist_state(message.from_user.id)
    ask_question(message.chat.id, "exercise_type", message.from_user.id)


@bot.message_handler(func=lambda m: m.text == "📋 بیشتر")
def handle_more_menu(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "📋 <b>چی میخوای ثبت کنی؟</b>",
        reply_markup=_more_menu_kb(),
    )


@bot.message_handler(func=lambda m: m.text == "📊 گزارش")
def handle_report_menu(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "📊 <b>چه گزارشی میخوای؟</b>",
        reply_markup=_report_menu_kb(),
    )


@bot.message_handler(func=lambda m: True)
def handle_text(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    state = user_states.get(message.from_user.id)
    text_steps = ("food_details", "notes", "med_dosage", "med_name",
                  "exercise_type")
    if state and state["step"] in text_steps:
        advance_flow(message.from_user.id, message.chat.id, message.text)
    else:
        bot.send_message(
            message.chat.id,
            "از منوی پایین یه گزینه انتخاب کن 👇",
            reply_markup=main_menu_keyboard(),
        )


# ---------------------------------------------------------------------------
# Callback handlers
# ---------------------------------------------------------------------------

@bot.callback_query_handler(func=lambda c: c.data.startswith("val_"))
def handle_value_callback(call: types.CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "دسترسی نداری.")
        return

    state = user_states.get(call.from_user.id)
    if not state:
        bot.answer_callback_query(call.id, "جلسه‌ای فعال نیست. از منو شروع کن.")
        return

    raw = call.data[4:]

    if raw == "skip":
        bot.answer_callback_query(call.id, "⏭ رد شد")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        advance_flow(call.from_user.id, call.message.chat.id, None)
        return

    step = state.get("step", "")
    if step == "massage_type":
        if raw not in ("firm", "gentle", "none"):
            bot.answer_callback_query(call.id, "مقدار نامعتبر.")
            return
        value = raw
    else:
        try:
            value = float(raw) if "." in raw else int(raw)
        except ValueError:
            bot.answer_callback_query(call.id, "مقدار نامعتبر.")
            return
        bounds = STEP_VALID_RANGE.get(step)
        if bounds and not (bounds[0] <= value <= bounds[1]):
            bot.answer_callback_query(call.id, "مقدار خارج از محدوده.")
            return

    bot.answer_callback_query(call.id, f"✅ {value} ثبت شد")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    advance_flow(call.from_user.id, call.message.chat.id, value)


@bot.callback_query_handler(func=lambda c: c.data in ("flow_confirm", "flow_cancel"))
def handle_flow_confirm(call: types.CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "دسترسی نداری.")
        return

    state = user_states.get(call.from_user.id)
    if not state or state["step"] != "_confirm":
        bot.answer_callback_query(call.id, "جلسه‌ای فعال نیست.")
        return

    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    if call.data == "flow_confirm":
        bot.answer_callback_query(call.id, "✅ ثبت شد")
        _finish_flow(call.from_user.id, call.message.chat.id, state["data"], state["flow"])
        _clear_state(call.from_user.id)
    else:
        bot.answer_callback_query(call.id, "❌ لغو شد")
        _clear_state(call.from_user.id)
        bot.send_message(call.message.chat.id, "❌ عملیات لغو شد.", reply_markup=main_menu_keyboard())


@bot.callback_query_handler(func=lambda c: c.data in ("flow_finish_early", "flow_continue"))
def handle_more_or_finish(call: types.CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "دسترسی نداری.")
        return

    state = user_states.get(call.from_user.id)
    if not state or state["step"] != "_more_or_finish":
        bot.answer_callback_query(call.id, "جلسه‌ای فعال نیست.")
        return

    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    if call.data == "flow_finish_early":
        bot.answer_callback_query(call.id, "✅")
        state["step"] = "_confirm"
        _persist_state(call.from_user.id)
        summary = _format_confirmation(state["data"], state["flow"])
        bot.send_message(call.message.chat.id, summary, reply_markup=_confirm_kb())
    else:
        bot.answer_callback_query(call.id, "📝 ادامه...")
        flow_steps = FLOWS[state["flow"]]
        core_idx = flow_steps.index(LOG_CORE_LAST_STEP)
        next_step = flow_steps[core_idx + 1]
        state["step"] = next_step
        _persist_state(call.from_user.id)
        ask_question(call.message.chat.id, next_step, call.from_user.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("med_"))
def handle_med_callback(call: types.CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "دسترسی نداری.")
        return

    state = user_states.get(call.from_user.id)
    if not state or state["step"] != "med_name":
        bot.answer_callback_query(call.id, "جلسه‌ای فعال نیست.")
        return

    med_name = call.data[4:]
    if med_name not in ("Ibuprofen", "Acetaminophen", "Aspirin", "Other"):
        bot.answer_callback_query(call.id, "مقدار نامعتبر.")
        return
    bot.answer_callback_query(call.id, f"✅ {med_name}")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    if med_name == "Other":
        bot.send_message(call.message.chat.id, "💊 <b>اسم دارو رو بنویس:</b>")
    else:
        advance_flow(call.from_user.id, call.message.chat.id, med_name)


@bot.callback_query_handler(func=lambda c: c.data.startswith("ex_"))
def handle_exercise_callback(call: types.CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "دسترسی نداری.")
        return

    state = user_states.get(call.from_user.id)
    if not state or state["step"] != "exercise_type":
        bot.answer_callback_query(call.id, "جلسه‌ای فعال نیست.")
        return

    ex_type = call.data[3:]
    if ex_type not in ("Walking", "Stretching", "Gym", "Swimming", "Cycling", "Running", "Other"):
        bot.answer_callback_query(call.id, "مقدار نامعتبر.")
        return
    bot.answer_callback_query(call.id, f"✅ {ex_type}")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    if ex_type == "Other":
        bot.send_message(call.message.chat.id, "🏃 <b>نوع ورزش رو بنویس:</b>")
    else:
        advance_flow(call.from_user.id, call.message.chat.id, ex_type)


@bot.callback_query_handler(func=lambda c: c.data.startswith("more_"))
def handle_more_callback(call: types.CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "دسترسی نداری.")
        return

    uid = call.from_user.id
    cid = call.message.chat.id
    action = call.data[5:]
    bot.answer_callback_query(call.id)

    try:
        bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    flow_map = {
        "heater": ("heater", "heater_hours"),
        "massage": ("massage", "massage_type"),
        "lifting": ("lifting", "lifting_weight"),
        "period": ("period", "period_status"),
        "medication": ("medication", "med_name"),
    }

    if action == "patch":
        database.insert_log(user_id=uid, back_patch=1)
        today_total = database.get_today_patch_count(uid, _today_str(uid))
        bot.send_message(
            cid,
            f"🩹 <b>چسب کمر ثبت شد.</b>\nامروز: {today_total} بار",
            reply_markup=main_menu_keyboard(),
        )
    elif action in flow_map:
        flow_name, first_step = flow_map[action]
        user_states[uid] = {"flow": flow_name, "step": first_step, "data": {}}
        _persist_state(uid)
        ask_question(cid, first_step, uid)


@bot.callback_query_handler(func=lambda c: c.data.startswith("rpt_"))
def handle_report_callback(call: types.CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "دسترسی نداری.")
        return

    action = call.data[4:]
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    cid = call.message.chat.id

    if action == "last":
        logs = database.get_recent_logs(1, user_id=uid)
        if not logs:
            bot.send_message(cid, "هنوز لاگی ثبت نشده.")
        else:
            bot.send_message(cid, _format_last_log(logs[0], uid), reply_markup=main_menu_keyboard())
    elif action == "today":
        _send_today_summary(cid, uid)
    elif action == "weekly":
        _send_weekly_report(cid, uid)
    elif action == "monthly":
        _send_monthly_report(cid, uid)
    elif action == "chart":
        _send_chart(cid, uid, 7)
    elif action == "insights":
        _send_insights(cid, uid)
    elif action == "medeff":
        _send_med_effectiveness(cid, uid)
    elif action == "export":
        _send_export(cid, uid)
    elif action == "streak":
        streak = database.get_logging_streak(uid)
        if streak == 0:
            bot.send_message(cid, "🔥 هنوز استریکی نداری. شروع کن!")
        else:
            bot.send_message(cid, f"🔥 استریک: <b>{streak} روز</b> پشت سرهم!")


# ---------------------------------------------------------------------------
# Report helper functions
# ---------------------------------------------------------------------------

def _send_today_summary(chat_id: int, user_id: int) -> None:
    today = _today_str(user_id)
    tomorrow = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    logs = database.get_logs_by_date_range(user_id, today, tomorrow)
    meds = database.get_medications_by_date_range(user_id, today, tomorrow)
    exercises = database.get_recent_exercises(50, user_id=user_id)
    today_exercises = [
        e for e in exercises
        if e["timestamp"][:10] == today
    ]
    text = reports.generate_daily_summary(logs, meds, today_exercises)
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())


def _send_weekly_report(chat_id: int, user_id: int) -> None:
    today = _now_local(user_id).date()
    week_start = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    week_end = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    prev_start = (today - timedelta(days=13)).strftime("%Y-%m-%d")

    logs = database.get_logs_by_date_range(user_id, week_start, week_end)
    prev_logs = database.get_logs_by_date_range(user_id, prev_start, week_start)
    meds = database.get_medications_by_date_range(user_id, week_start, week_end)
    exercises = database.get_recent_exercises(100, user_id=user_id)
    week_exercises = [e for e in exercises if e["timestamp"][:10] >= week_start]

    text = reports.generate_weekly_report(logs, prev_logs, meds, week_exercises)
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())


def _send_monthly_report(chat_id: int, user_id: int) -> None:
    today = _now_local(user_id).date()
    month_start = today.replace(day=1).strftime("%Y-%m-%d")
    month_end = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    prev_month_end = today.replace(day=1)
    prev_month_start = (prev_month_end - timedelta(days=1)).replace(day=1).strftime("%Y-%m-%d")
    prev_month_end_str = prev_month_end.strftime("%Y-%m-%d")

    logs = database.get_logs_by_date_range(user_id, month_start, month_end)
    prev_logs = database.get_logs_by_date_range(user_id, prev_month_start, prev_month_end_str)
    meds = database.get_medications_by_date_range(user_id, month_start, month_end)
    exercises = database.get_recent_exercises(200, user_id=user_id)
    month_exercises = [e for e in exercises if e["timestamp"][:10] >= month_start]

    text = reports.generate_monthly_report(logs, prev_logs, meds, month_exercises)
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())


def _send_chart(chat_id: int, user_id: int, days: int = 7) -> None:
    today = _now_local(user_id).date()
    start = (today - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    end = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    logs = database.get_logs_by_date_range(user_id, start, end)

    if not logs:
        bot.send_message(chat_id, "📈 داده‌ای برای نمودار نیست.")
        return

    pain_chart = reports.generate_trend_chart(
        logs,
        ["back_pain", "headache", "sleep_quality"],
        title=f"Pain & Sleep — last {days} days",
    )
    mood_chart = reports.generate_trend_chart(
        logs,
        ["peace_level", "sleep_hours"],
        title=f"Peace & Sleep Duration — last {days} days",
    )
    lifestyle_chart = reports.generate_trend_chart(
        logs,
        ["phone_hours", "computer_hours", "sitting_hours", "water_amount", "knitting_hours"],
        title=f"Lifestyle — last {days} days",
    )

    for chart_bytes in (pain_chart, mood_chart, lifestyle_chart):
        if chart_bytes:
            bot.send_photo(chat_id, chart_bytes)

    if not any((pain_chart, mood_chart, lifestyle_chart)):
        bot.send_message(chat_id, "📈 داده کافی برای نمودار نیست.")


def _send_history(chat_id: int, user_id: int, days: int = 7) -> None:
    today = _now_local(user_id).date()
    start = (today - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    end = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    logs = database.get_logs_by_date_range(user_id, start, end)

    if not logs:
        bot.send_message(chat_id, f"📅 لاگی در {days} روز اخیر نیست.")
        return

    lines = [f"📅 <b>تاریخچه {days} روز اخیر</b>\n"]
    def _hv(log, key):
        try:
            return log[key]
        except (IndexError, KeyError):
            return None

    for log in logs:
        ts = _format_ts(log["timestamp"], user_id)
        parts = []
        if log["back_pain"] is not None:
            parts.append(f"🦴{log['back_pain']}")
        if log["headache"] is not None:
            parts.append(f"🤕{log['headache']}")
        if log["sleep_quality"] is not None:
            parts.append(f"😴{log['sleep_quality']}")
        if log["peace_level"] is not None:
            parts.append(f"🧘{log['peace_level']}")
        if log["smoke_count"] is not None:
            parts.append(f"🚬{log['smoke_count']}")
        if log["water_amount"] is not None:
            parts.append(f"💧{log['water_amount']}")
        if _hv(log, "tea_count"):
            parts.append(f"🍵{_hv(log, 'tea_count')}")
        if _hv(log, "water_glasses") is not None:
            parts.append(f"💧+{_hv(log, 'water_glasses')}")
        if _hv(log, "knitting_hours") is not None:
            parts.append(f"🧶{_hv(log, 'knitting_hours')}")
        if _hv(log, "back_patch"):
            parts.append("🩹")
        if _hv(log, "massage_type"):
            parts.append(f"💆{_hv(log, 'massage_type')}")
        if _hv(log, "heavy_lifting_kg") is not None:
            parts.append(f"🏋️{_hv(log, 'heavy_lifting_kg')}kg")
        detail = " ".join(parts) if parts else "—"
        lines.append(f"<code>{ts}</code>  {detail}")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())


def _send_insights(chat_id: int, user_id: int) -> None:
    logs = database.get_recent_logs(200, user_id=user_id)
    insights = reports.compute_correlations(logs)
    text = "🔍 <b>بینش‌ها</b>\n\n" + "\n\n".join(insights)
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())


def _send_med_effectiveness(chat_id: int, user_id: int) -> None:
    logs = database.get_recent_logs(200, user_id=user_id)
    meds = database.get_recent_medications(200, user_id=user_id)
    text = reports.compute_med_effectiveness(logs, meds)
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())


def _send_export(chat_id: int, user_id: int, text: str = "") -> None:
    parts = text.split() if text else []
    start_date = parts[1] if len(parts) > 1 else None
    end_date = parts[2] if len(parts) > 2 else None
    csv_str = database.export_logs_csv(user_id, start_date, end_date)
    if not csv_str:
        bot.send_message(chat_id, "📤 داده‌ای برای خروجی نیست.")
        return
    buf = io.BytesIO(csv_str.encode("utf-8"))
    buf.name = "health_logs.csv"
    bot.send_document(chat_id, buf, caption="📤 خروجی CSV")


# ---------------------------------------------------------------------------
# Scheduled prompts
# ---------------------------------------------------------------------------

def _send_reminder(uid: int, greeting: str) -> None:
    """Start the unified log flow for a user via scheduled reminder."""
    if uid in user_states:
        logger.info("Skipping reminder for user %s — already in a flow.", uid)
        return
    try:
        first_step = FLOWS["log"][0]
        user_states[uid] = {"flow": "log", "step": first_step, "data": {}}
        _persist_state(uid)
        bot.send_message(uid, greeting)
        ask_question(uid, first_step, uid)
    except Exception as e:
        logger.error("Reminder error for %s: %s", uid, e)


def send_noon_prompt() -> None:
    for uid in ADMIN_IDS:
        _send_reminder(uid, "🌞 <b>وقت ثبت داده‌ست!</b>")


def send_night_prompt() -> None:
    for uid in ADMIN_IDS:
        _send_reminder(uid, "🌙 <b>وقت ثبت داده شبه!</b>")


def send_daily_summary() -> None:
    for uid in ADMIN_IDS:
        try:
            _send_today_summary(uid, uid)
        except Exception as e:
            logger.error("Daily summary error for %s: %s", uid, e)


def send_weekly_report() -> None:
    for uid in ADMIN_IDS:
        try:
            _send_weekly_report(uid, uid)
        except Exception as e:
            logger.error("Weekly report error for %s: %s", uid, e)


def run_daily_backup() -> None:
    try:
        database.backup_db()
        logger.info("Daily backup completed.")
    except Exception as e:
        logger.error("Backup error: %s", e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_time(time_str: str) -> tuple[int, int]:
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])


def _schedule_user_reminders(scheduler, uid: int) -> None:
    """Schedule reminders using per-user settings from DB, with env defaults as fallback."""
    settings = database.get_user_settings(uid)
    noon_time = settings.get("reminder_noon", REMINDER_NOON)
    night_time = settings.get("reminder_night", REMINDER_NIGHT)
    user_tz = _get_tz(uid)
    noon_h, noon_m = _parse_time(noon_time)
    night_h, night_m = _parse_time(night_time)

    scheduler.add_job(
        _send_reminder, "cron",
        args=[uid, "🌞 <b>وقت ثبت داده‌ست!</b>"],
        hour=noon_h, minute=noon_m, timezone=user_tz,
        id=f"noon_{uid}", replace_existing=True,
    )
    scheduler.add_job(
        _send_reminder, "cron",
        args=[uid, "🌙 <b>وقت ثبت داده شبه!</b>"],
        hour=night_h, minute=night_m, timezone=user_tz,
        id=f"night_{uid}", replace_existing=True,
    )


def main() -> None:
    if not BOT_TOKEN:
        print("Set BOT_TOKEN in .env to run the bot.")
        return

    database.init_db()
    logger.info("DB initialized. Admin IDs: %s", ADMIN_IDS)

    _restore_sessions()

    tz = _get_tz()
    scheduler = BackgroundScheduler(timezone=tz)

    for uid in ADMIN_IDS:
        _schedule_user_reminders(scheduler, uid)

    scheduler.add_job(send_daily_summary, "cron", hour=23, minute=0)
    scheduler.add_job(send_weekly_report, "cron", day_of_week="sun", hour=10, minute=0)
    scheduler.add_job(run_daily_backup, "cron", hour=3, minute=0)
    scheduler.start()
    logger.info("Scheduler started with per-user reminders, tz=%s", tz)

    logger.info("Bot polling started.")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)


if __name__ == "__main__":
    main()
