#!/usr/bin/env python3
"""
Health Tracker Telegram Bot (stub).
- Whitelist: only ADMIN_IDS from .env may use the bot.
- Scheduled prompts: Noon (sleep, pain, peace), Night (water/food/smoke, screen, peace).
- On-demand: "Log Cigarette", "Log All Data" via menu.
"""
from pathlib import Path

# Load .env so token and admin IDs are available for real implementation
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")


def main():
    admin_ids = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip()]
    if not BOT_TOKEN:
        print("Set BOT_TOKEN in .env to run the bot.")
        return
    print("Bot placeholder: token and admin IDs loaded.")
    print("Admin IDs:", admin_ids)
    # TODO: telebot, scheduler, handlers, db.insert_log


if __name__ == "__main__":
    main()
