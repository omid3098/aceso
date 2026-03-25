# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Aceso is a personal health-tracking Telegram bot for chronic back pain, headaches, and lifestyle habits. It stores data in SQLite (`tracker.db`) and provides a Rich-based TUI (`manage.py`) for server management. The bot UI is in Farsi; the TUI and code are in English.

## Commands

### Run tests
```bash
pytest                        # all tests with coverage (must be >=85%)
pytest tests/test_db.py       # single test file
pytest tests/test_db.py::test_insert_log_defaults -v  # single test
```

### Run the bot
```bash
python bot.py
```

### Run the management TUI
```bash
python manage.py
```

### Install dependencies
```bash
pip install -r requirements.txt
```

## Architecture

**Four source modules, no package structure — all imports are top-level:**

- **`db.py`** — SQLite schema, migrations, and all data access (logs, medications, exercises, user settings, sessions). Uses `_MIGRATIONS` dict for schema evolution via `ALTER TABLE`. The `sessions` table persists bot conversation state so multi-step flows survive restarts.

- **`bot.py`** — Telegram bot using pyTelegramBotAPI. Implements a state-machine flow engine (`FLOWS` dict maps flow names to ordered lists of steps; `user_states` tracks in-progress flows). Handlers use inline keyboards and callback queries. Scheduled reminders via APScheduler. Whitelist-only access via `ADMIN_IDS` from `.env`.

- **`reports.py`** — Analytics: daily/weekly/monthly summaries, matplotlib trend charts, Pearson correlation analysis between lifestyle factors and pain outcomes, medication effectiveness comparison.

- **`manage.py`** — Server management TUI using Rich. Handles deps install, `.env` config, systemd service control, log viewing, git updates.

## Key Patterns

- **Test isolation**: Every test file uses an `isolated_db` fixture that monkeypatches `db.DB_PATH` to a temp directory. No test touches the real database.
- **Bot testability**: `bot.py` uses a placeholder token (`"0:placeholder"`) when `BOT_TOKEN` is unset so the module can be imported in tests without a valid Telegram token.
- **Flow engine**: Bot conversation flows are defined declaratively in `FLOWS` dict. Each flow is a list of step names. The `_advance_flow` function drives step progression, and `STEP_CONFIG` maps step names to prompts/keyboards/handlers.
- **Coverage**: pytest is configured with `--cov-fail-under=85` — tests must maintain at least 85% coverage.
- **Timestamps**: Stored as UTC strings (`"%Y-%m-%d %H:%M:%S"`) in the DB. Converted to user-local time for display using per-user timezone settings.
