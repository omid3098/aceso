# Health Tracker Telegram Bot

A personal health-tracking Telegram bot for chronic back pain, headaches, and lifestyle habits. Tracks data in SQLite and can be run on a VPS with an optional TUI for management.

## Features

- **Telegram bot**: Whitelist-only (your User IDs). Scheduled noon/night prompts and on-demand logging (Log Cigarette, Log All Data).
- **SQLite**: Local `tracker.db` — no external DB setup.
- **TUI** (`manage.py`): Install deps, set Bot Token & Admin IDs, manage systemd service, view logs, update from Git.
- **One-liner install**: Clone, venv, requirements, then launch the TUI for first-time setup.

## Quick start on a server (Linux/macOS)

One-liner (default install dir: `~/health-tracker-bot`):

```bash
curl -sSL https://raw.githubusercontent.com/omid3098/aceso/main/install.sh | bash
```

With a custom directory:

```bash
curl -sSL https://raw.githubusercontent.com/omid3098/aceso/main/install.sh | bash -s -- /opt/health-bot
```

After the script runs, the TUI opens. Use **option 2** to set your **Bot Token** (from [@BotFather](https://t.me/BotFather)) and **Admin IDs** (from [@userinfobot](https://t.me/userinfobot), comma-separated).

## Manual setup

```bash
git clone https://github.com/omid3098/aceso.git
cd aceso
python3 -m venv venv
source venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
cp .env.example .env
# Edit .env: BOT_TOKEN and ADMIN_IDS
python manage.py           # TUI: set token & IDs, install deps, view logs, etc.
python bot.py              # Run the bot (or use systemd)
```

## Config

- **`.env`** (create from `.env.example`):
  - `BOT_TOKEN` — from @BotFather
  - `ADMIN_IDS` — comma-separated Telegram user IDs

You can edit `.env` by hand or via **manage.py → option 2**.

## Systemd (run bot on the server)

1. Replace `INSTALL_DIR` in `health-bot.service` with your project path, e.g. `/home/ubuntu/aceso`:

   ```bash
   sed 's|INSTALL_DIR|/home/ubuntu/aceso|g' health-bot.service > ~/.config/systemd/user/health-bot.service
   mkdir -p ~/.config/systemd/user
   ```

2. Enable and start:

   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now health-bot.service
   systemctl --user status health-bot.service
   ```

Or use **manage.py → option 3** (Manage systemd service) for Start/Stop/Restart/Status.

## Project layout

| File / folder        | Purpose                                  |
|----------------------|------------------------------------------|
| `bot.py`             | Telegram bot (whitelist, prompts, logging) |
| `db.py`              | SQLite schema and helpers                |
| `manage.py`          | TUI: deps, config, systemd, logs, git    |
| `install.sh`         | One-liner installer                      |
| `requirements.txt`   | Python dependencies                      |
| `health-bot.service` | Systemd unit template                    |
| `.env.example`       | Example env (copy to `.env`)             |

## License

Use and modify as you like.
