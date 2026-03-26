#!/usr/bin/env python3
"""
TUI for Health Tracker Bot: install deps, config, systemd, view logs, git update.
English only. Uses rich for UI.
"""
import io
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
SERVICE_NAME = "health-bot.service"

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False


def main():
    if not sys.stdin.isatty():
        try:
            sys.stdin = open("/dev/tty", "r")
        except OSError:
            print("ERROR: No interactive terminal found. Run manage.py directly:", file=sys.stderr)
            print(f"  cd {PROJECT_ROOT} && source venv/bin/activate && python manage.py", file=sys.stderr)
            sys.exit(1)

    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(errors='replace')
    elif sys.stdin.encoding != 'utf-8':
        sys.stdin = io.TextIOWrapper(
            sys.stdin.buffer, encoding='utf-8', errors='replace'
        )

    if not _RICH_AVAILABLE:
        print("Missing dependency: run  pip install rich  then run this script again.", file=sys.stderr)
        sys.exit(1)

    console = Console()

    while True:
        console.print(Panel("[bold]Health Tracker Bot - Management[/bold]", title="Menu"))
        console.print("  1. Install dependencies")
        console.print("  2. Update Bot Token & Admin IDs")
        console.print("  3. Manage systemd service (Start / Stop / Restart / Status)")
        console.print("  4. View live logs")
        console.print("  5. Update from Git")
        console.print("  0. Exit")
        try:
            choice = Prompt.ask("\nChoice", default="0").strip()
        except UnicodeDecodeError:
            console.print("[red]Input error (encoding issue). Try again.[/red]")
            continue

        if choice == "0":
            console.print("Goodbye.")
            break
        if choice == "1":
            do_install_deps(console)
        elif choice == "2":
            do_update_config(console)
        elif choice == "3":
            do_systemd(console)
        elif choice == "4":
            do_view_logs(console)
        elif choice == "5":
            do_git_update(console)
        else:
            console.print("[red]Invalid option.[/red]")


def get_venv_python() -> Optional[Path]:
    """Return path to Python in venv if we're in one or venv exists in project."""
    if os.environ.get("VIRTUAL_ENV"):
        base = Path(os.environ["VIRTUAL_ENV"])
        exe = base / "bin" / "python"
        if not exe.exists():
            exe = base / "Scripts" / "python.exe"
        return exe if exe.exists() else None
    venv_dir = PROJECT_ROOT / "venv"
    if venv_dir.is_dir():
        for name in ("bin/python", "Scripts/python.exe"):
            p = venv_dir / name
            if p.exists():
                return p
    return None


def do_install_deps(console):
    """Run pip install -r requirements.txt in project venv."""
    console.print("[bold]Install dependencies[/bold]")
    py = get_venv_python()
    if not py:
        console.print("[yellow]No venv detected. Using current interpreter.[/yellow]")
        py = Path(sys.executable)
    req = REQUIREMENTS
    if not req.exists():
        console.print(f"[red]Not found: {req}[/red]")
        return
    try:
        subprocess.run(
            [str(py), "-m", "pip", "install", "-r", str(req)],
            cwd=PROJECT_ROOT,
            check=True,
        )
        console.print("[green]Dependencies installed successfully.[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Install failed: {e}[/red]")


def load_env() -> dict[str, str]:
    """Read .env into a dict. Create from .env.example if missing."""
    if not ENV_FILE.exists() and ENV_EXAMPLE.exists():
        ENV_FILE.write_text(ENV_EXAMPLE.read_text())
    out = {}
    if not ENV_FILE.exists():
        return out
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def save_env(data: dict[str, str]) -> None:
    """Write .env from dict. Preserve BOT_TOKEN and ADMIN_IDS keys."""
    lines = []
    for k, v in data.items():
        if " " in str(v) or "\n" in str(v):
            v = f'"{v}"'
        lines.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(lines) + "\n")
    try:
        ENV_FILE.chmod(0o600)
    except OSError:
        pass  # Windows or other platforms without chmod support


def do_update_config(console):
    """Prompt for BOT_TOKEN, ADMIN_IDS, TIMEZONE, and reminder times."""
    console.print("[bold]Update Bot Token & Admin IDs[/bold]")
    env = load_env()
    token = Prompt.ask("Bot Token", default=env.get("BOT_TOKEN", "")).strip()
    admin_ids = Prompt.ask("Admin User IDs (comma-separated)", default=env.get("ADMIN_IDS", "")).strip()
    timezone = Prompt.ask("Timezone (e.g. Asia/Tehran, UTC)", default=env.get("TIMEZONE", "UTC")).strip()
    reminder_noon = Prompt.ask("Noon reminder (HH:MM)", default=env.get("REMINDER_NOON", "12:00")).strip()
    reminder_night = Prompt.ask("Night reminder (HH:MM)", default=env.get("REMINDER_NIGHT", "21:00")).strip()
    env["BOT_TOKEN"] = token
    env["ADMIN_IDS"] = admin_ids
    env["TIMEZONE"] = timezone
    env["REMINDER_NOON"] = reminder_noon
    env["REMINDER_NIGHT"] = reminder_night
    save_env(env)
    console.print("[green]Config saved to .env[/green]")


def systemctl_available() -> bool:
    """True if systemctl is on PATH (Linux with systemd)."""
    try:
        subprocess.run(["systemctl", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def do_systemd(console):
    """Submenu: Start, Stop, Restart, Status for health-bot.service."""
    if not systemctl_available():
        console.print("[yellow]systemctl not available (e.g. not Linux or no systemd).[/yellow]")
        console.print("Install the service file and run the bot manually or via cron.")
        return
    console.print("[bold]Manage systemd service[/bold]")
    console.print("  a. Start   b. Stop   c. Restart   d. Status   x. Back")
    action = Prompt.ask("Action", default="x").strip().lower()
    if action == "x":
        return
    cmd_map = {"a": "start", "b": "stop", "c": "restart", "d": "status"}
    if action not in cmd_map:
        console.print("[red]Invalid action.[/red]")
        return
    cmd = ["systemctl", cmd_map[action], SERVICE_NAME]
    if getattr(os, "getuid", lambda: -1)() != 0:
        cmd = ["systemctl", "--user", cmd_map[action], SERVICE_NAME]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.stdout:
            console.print(result.stdout)
        if result.stderr:
            console.print(result.stderr)
        if result.returncode == 0:
            console.print("[green]Done.[/green]")
        else:
            console.print("[red]Command failed.[/red]")
    except subprocess.TimeoutExpired:
        console.print("[red]Command timed out.[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def do_view_logs(console):
    """Show last 50 logs in a rich table."""
    console.print("[bold]View live logs[/bold]")
    try:
        import db
        db.init_db()
        rows = db.get_recent_logs(50)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return
    if not rows:
        console.print("No logs yet.")
        return
    table = Table(show_header=True, header_style="bold")
    keys = [
        "id", "timestamp", "user_id", "back_pain", "headache", "peace_level",
        "sleep_quality", "stress_level", "anxiety_level", "water_amount",
        "smoke_count", "caffeine_amount", "sitting_hours", "screen_hours",
        "food_details", "period_status", "notes",
    ]
    for k in keys:
        table.add_column(k, overflow="fold")
    for row in rows:
        table.add_row(*[str(row[k]) if row[k] is not None else "" for k in keys])
    console.print(table)
    console.print(f"[dim]Showing last {len(rows)} entries. Re-open this menu to refresh.[/dim]")


def do_git_update(console):
    """git pull in project root then restart health-bot.service."""
    console.print("[bold]Update from Git[/bold]")
    if not (PROJECT_ROOT / ".git").exists():
        console.print("[red]Not a git repository.[/red]")
        return
    try:
        subprocess.run(["git", "pull"], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)
        console.print("[green]Git pull succeeded.[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Git pull failed: {e}[/red]")
        return
    if not systemctl_available():
        console.print("[yellow]systemctl not available; skip restart.[/yellow]")
        return
    cmd = ["systemctl", "--user", "restart", SERVICE_NAME]
    if getattr(os, "getuid", lambda: -1)() == 0:
        cmd = ["systemctl", "restart", SERVICE_NAME]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        console.print("[green]Service restarted.[/green]")
    except subprocess.CalledProcessError:
        console.print("[yellow]Restart failed (service may not be installed).[/yellow]")


if __name__ == "__main__":
    main()
