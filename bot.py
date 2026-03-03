#!/usr/bin/env python3
"""
Health Tracker Telegram Bot
- Whitelist: only ADMIN_IDS from .env may use the bot.
- Scheduled prompts: Noon (sleep, back pain, headache, peace), Night (water, food, smoke, caffeine, screen, sitting, peace, notes).
- On-demand: noon/night flows and quick cigarette log via reply keyboard.
"""
import os
import logging
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip()]

TZ = pytz.timezone("Asia/Tehran")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# user_states[user_id] = {"flow": str, "step": str, "data": dict}
user_states: dict = {}

FLOWS: dict[str, list[str]] = {
    "noon": ["sleep_quality", "back_pain", "headache", "peace_level"],
    "night": ["water_amount", "food_details", "smoke_count", "caffeine_amount", "screen_hours", "sitting_hours", "peace_level", "notes"],
}

QUESTIONS: dict[str, str] = {
    "sleep_quality":  "😴 <b>کیفیت خوابت دیشب چطور بود؟</b>\n(۱ = خیلی بد، ۱۰ = عالی)",
    "back_pain":      "🦴 <b>الان کمردردت چقدره؟</b>\n(۱ = بدون درد، ۱۰ = خیلی شدید)",
    "headache":       "🤕 <b>الان سردرد داری؟</b>\n(۱ = ندارم، ۱۰ = خیلی شدید)",
    "peace_level":    "🧘 <b>حس آرامشت الان چقدره؟</b>\n(۱ = اصلاً، ۱۰ = خیلی زیاد)",
    "water_amount":   "💧 <b>امروز چند لیوان آب خوردی؟</b>",
    "food_details":   "🍽 <b>امروز چی خوردی؟</b>\n(خلاصه بنویس یا بزن /skip)",
    "smoke_count":    "🚬 <b>چند نخ سیگار کشیدی امروز؟</b>",
    "caffeine_amount": "☕ <b>چقدر کافئین مصرف کردی؟</b>\n(۰=هیچ، ۱=یه فنجون چای/قهوه، ۲=دوتا، ...)",
    "screen_hours":   "📱 <b>چند ساعت پشت صفحه‌نمایش بودی؟</b>",
    "sitting_hours":  "🪑 <b>چند ساعت نشستی؟</b>",
    "notes":          "📝 <b>یادداشت یا نکته‌ای داری؟</b>\n(بزن /skip اگه نداری)",
}


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

def make_scale_keyboard(max_val: int = 10, row_size: int = 5) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=row_size)
    buttons = [types.InlineKeyboardButton(str(i), callback_data=f"val_{i}") for i in range(1, max_val + 1)]
    markup.add(*buttons)
    return markup


def make_count_keyboard(max_val: int = 20, row_size: int = 7) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=row_size)
    buttons = [types.InlineKeyboardButton(str(i), callback_data=f"val_{i}") for i in range(0, max_val + 1)]
    markup.add(*buttons)
    return markup


def make_hours_keyboard() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=6)
    options = [0, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    buttons = [types.InlineKeyboardButton(str(h), callback_data=f"val_{h}") for h in options]
    markup.add(*buttons)
    return markup


def main_menu_keyboard() -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🌞 ثبت داده ظهر"),
        types.KeyboardButton("🌙 ثبت داده شب"),
        types.KeyboardButton("🚬 ثبت سیگار"),
        types.KeyboardButton("📊 آخرین لاگ"),
    )
    return markup


# ---------------------------------------------------------------------------
# Flow engine
# ---------------------------------------------------------------------------

def ask_question(chat_id: int, step: str) -> None:
    question = QUESTIONS.get(step, "")
    if step in ("sleep_quality", "back_pain", "headache", "peace_level"):
        bot.send_message(chat_id, question, reply_markup=make_scale_keyboard(10))
    elif step in ("smoke_count",):
        bot.send_message(chat_id, question, reply_markup=make_count_keyboard(30))
    elif step in ("caffeine_amount",):
        bot.send_message(chat_id, question, reply_markup=make_count_keyboard(10))
    elif step in ("water_amount",):
        bot.send_message(chat_id, question, reply_markup=make_count_keyboard(20))
    elif step in ("screen_hours", "sitting_hours"):
        bot.send_message(chat_id, question, reply_markup=make_hours_keyboard())
    else:
        bot.send_message(chat_id, question)


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
        next_step = flow_steps[current_idx + 1]
        state["step"] = next_step
        ask_question(chat_id, next_step)
    else:
        data = state["data"]
        database.insert_log(
            user_id=user_id,
            back_pain=data.get("back_pain"),
            headache=data.get("headache"),
            peace_level=data.get("peace_level"),
            sleep_quality=data.get("sleep_quality"),
            water_amount=data.get("water_amount"),
            smoke_count=data.get("smoke_count"),
            caffeine_amount=data.get("caffeine_amount"),
            sitting_hours=data.get("sitting_hours"),
            screen_hours=data.get("screen_hours"),
            food_details=data.get("food_details"),
            notes=data.get("notes"),
        )
        del user_states[user_id]
        bot.send_message(chat_id, "✅ <b>داده‌ها ثبت شدن!</b> ممنون. 🙏", reply_markup=main_menu_keyboard())


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@bot.message_handler(commands=["start"])
def handle_start(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ دسترسی نداری.")
        return
    bot.send_message(
        message.chat.id,
        "سلام! 👋 <b>بات ردیابی سلامت</b> آماده‌ست.\nاز منوی پایین استفاده کن:",
        reply_markup=main_menu_keyboard(),
    )


@bot.message_handler(commands=["skip"])
def handle_skip(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    state = user_states.get(message.from_user.id)
    if state and state["step"] in ("food_details", "notes"):
        advance_flow(message.from_user.id, message.chat.id, None)
    else:
        bot.send_message(message.chat.id, "الان چیزی برای رد کردن نداری.")


@bot.message_handler(func=lambda m: m.text == "🌞 ثبت داده ظهر")
def handle_noon(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    user_states[message.from_user.id] = {"flow": "noon", "step": "sleep_quality", "data": {}}
    ask_question(message.chat.id, "sleep_quality")


@bot.message_handler(func=lambda m: m.text == "🌙 ثبت داده شب")
def handle_night(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    user_states[message.from_user.id] = {"flow": "night", "step": "water_amount", "data": {}}
    ask_question(message.chat.id, "water_amount")


@bot.message_handler(func=lambda m: m.text == "🚬 ثبت سیگار")
def handle_cigarette(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    database.insert_log(user_id=message.from_user.id, smoke_count=1)
    bot.send_message(message.chat.id, "🚬 یه نخ سیگار ثبت شد.", reply_markup=main_menu_keyboard())


@bot.message_handler(func=lambda m: m.text == "📊 آخرین لاگ")
def handle_last_log(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    logs = database.get_recent_logs(1)
    if not logs:
        bot.send_message(message.chat.id, "هنوز لاگی ثبت نشده.")
        return
    row = logs[0]
    text = (
        f"📊 <b>آخرین لاگ</b>\n"
        f"🕐 {row['timestamp']}\n\n"
        f"😴 کیفیت خواب: {row['sleep_quality'] or '—'}/10\n"
        f"🦴 کمردرد: {row['back_pain'] or '—'}/10\n"
        f"🤕 سردرد: {row['headache'] or '—'}/10\n"
        f"🧘 آرامش: {row['peace_level'] or '—'}/10\n\n"
        f"💧 آب: {row['water_amount'] or '—'} لیوان\n"
        f"🚬 سیگار: {row['smoke_count'] or '—'} نخ\n"
        f"☕ کافئین: {row['caffeine_amount'] or '—'}\n"
        f"📱 صفحه: {row['screen_hours'] or '—'} ساعت\n"
        f"🪑 نشستن: {row['sitting_hours'] or '—'} ساعت\n"
        f"🍽 غذا: {row['food_details'] or '—'}\n"
        f"📝 یادداشت: {row['notes'] or '—'}"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu_keyboard())


@bot.message_handler(func=lambda m: True)
def handle_text(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    state = user_states.get(message.from_user.id)
    if state and state["step"] in ("food_details", "notes"):
        advance_flow(message.from_user.id, message.chat.id, message.text)
    else:
        bot.send_message(
            message.chat.id,
            "از منوی پایین یه گزینه انتخاب کن 👇",
            reply_markup=main_menu_keyboard(),
        )


@bot.callback_query_handler(func=lambda c: c.data.startswith("val_"))
def handle_callback(call: types.CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "دسترسی نداری.")
        return

    state = user_states.get(call.from_user.id)
    if not state:
        bot.answer_callback_query(call.id, "جلسه‌ای فعال نیست. از منو شروع کن.")
        return

    raw = call.data[4:]
    try:
        value = float(raw) if "." in raw else int(raw)
    except ValueError:
        bot.answer_callback_query(call.id, "مقدار نامعتبر.")
        return

    bot.answer_callback_query(call.id, f"✅ {value} ثبت شد")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    advance_flow(call.from_user.id, call.message.chat.id, value)


# ---------------------------------------------------------------------------
# Scheduled prompts
# ---------------------------------------------------------------------------

def send_noon_prompt() -> None:
    for uid in ADMIN_IDS:
        try:
            user_states[uid] = {"flow": "noon", "step": "sleep_quality", "data": {}}
            bot.send_message(uid, "🌞 <b>وقت ثبت داده ظهره!</b>")
            ask_question(uid, "sleep_quality")
        except Exception as e:
            logger.error("Noon prompt error for %s: %s", uid, e)


def send_night_prompt() -> None:
    for uid in ADMIN_IDS:
        try:
            user_states[uid] = {"flow": "night", "step": "water_amount", "data": {}}
            bot.send_message(uid, "🌙 <b>وقت ثبت داده شبه!</b>")
            ask_question(uid, "water_amount")
        except Exception as e:
            logger.error("Night prompt error for %s: %s", uid, e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if not BOT_TOKEN:
        print("Set BOT_TOKEN in .env to run the bot.")
        return

    database.init_db()
    logger.info("DB initialized. Admin IDs: %s", ADMIN_IDS)

    scheduler = BackgroundScheduler(timezone=TZ)
    scheduler.add_job(send_noon_prompt, "cron", hour=12, minute=0)
    scheduler.add_job(send_night_prompt, "cron", hour=21, minute=0)
    scheduler.start()
    logger.info("Scheduler started — noon=12:00, night=21:00 (Tehran time).")

    logger.info("Bot polling started.")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)


if __name__ == "__main__":
    main()
