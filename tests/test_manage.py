"""Tests for manage.py – TUI helper functions."""
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import manage


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def env_dir(tmp_path, monkeypatch):
    """Override module-level path constants to point to a temp directory."""
    env_file = tmp_path / ".env"
    env_example = tmp_path / ".env.example"
    req_file = tmp_path / "requirements.txt"
    monkeypatch.setattr(manage, "ENV_FILE", env_file)
    monkeypatch.setattr(manage, "ENV_EXAMPLE", env_example)
    monkeypatch.setattr(manage, "REQUIREMENTS", req_file)
    monkeypatch.setattr(manage, "PROJECT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture()
def mock_console():
    return MagicMock()


def printed(console) -> str:
    """Concatenate all console.print call args into a single string."""
    return " ".join(str(a) for call in console.print.call_args_list for a in call.args)


# ── load_env ──────────────────────────────────────────────────────────────────

def test_load_env_no_file_returns_empty(env_dir):
    assert manage.load_env() == {}


def test_load_env_reads_key_value(env_dir):
    manage.ENV_FILE.write_text("BOT_TOKEN=mytoken\n")
    result = manage.load_env()
    assert result["BOT_TOKEN"] == "mytoken"


def test_load_env_multiple_keys(env_dir):
    manage.ENV_FILE.write_text("A=1\nB=2\nC=3\n")
    result = manage.load_env()
    assert result == {"A": "1", "B": "2", "C": "3"}


def test_load_env_strips_double_quotes(env_dir):
    manage.ENV_FILE.write_text('KEY="hello world"\n')
    assert manage.load_env()["KEY"] == "hello world"


def test_load_env_strips_single_quotes(env_dir):
    manage.ENV_FILE.write_text("KEY='value'\n")
    assert manage.load_env()["KEY"] == "value"


def test_load_env_skips_comments(env_dir):
    manage.ENV_FILE.write_text("# comment\nKEY=val\n")
    result = manage.load_env()
    assert len(result) == 1
    assert result["KEY"] == "val"


def test_load_env_skips_blank_lines(env_dir):
    manage.ENV_FILE.write_text("\n  \nKEY=val\n\n")
    assert manage.load_env() == {"KEY": "val"}


def test_load_env_copies_example_when_env_missing(env_dir):
    manage.ENV_EXAMPLE.write_text("BOT_TOKEN=\nADMIN_IDS=\n")
    manage.load_env()
    assert manage.ENV_FILE.exists()


def test_load_env_example_contents_loaded(env_dir):
    manage.ENV_EXAMPLE.write_text("KEY=from_example\n")
    result = manage.load_env()
    assert result["KEY"] == "from_example"


def test_load_env_value_with_equals_sign(env_dir):
    manage.ENV_FILE.write_text("URL=http://host/path?a=1\n")
    assert manage.load_env()["URL"] == "http://host/path?a=1"


# ── save_env ──────────────────────────────────────────────────────────────────

def test_save_env_writes_file(env_dir):
    manage.save_env({"K": "v"})
    assert manage.ENV_FILE.exists()


def test_save_env_basic_key_value(env_dir):
    manage.save_env({"TOKEN": "abc", "IDS": "1,2"})
    content = manage.ENV_FILE.read_text()
    assert "TOKEN=abc" in content
    assert "IDS=1,2" in content


def test_save_env_wraps_value_with_space(env_dir):
    manage.save_env({"MSG": "hello world"})
    assert '"hello world"' in manage.ENV_FILE.read_text()


def test_save_env_wraps_value_with_newline(env_dir):
    manage.save_env({"K": "line1\nline2"})
    assert '"line1\nline2"' in manage.ENV_FILE.read_text()


def test_save_env_roundtrip(env_dir):
    data = {"BOT_TOKEN": "tok123", "ADMIN_IDS": "10,20,30"}
    manage.save_env(data)
    loaded = manage.load_env()
    assert loaded["BOT_TOKEN"] == "tok123"
    assert loaded["ADMIN_IDS"] == "10,20,30"


def test_save_env_ends_with_newline(env_dir):
    manage.save_env({"A": "1"})
    assert manage.ENV_FILE.read_text().endswith("\n")


# ── get_venv_python ───────────────────────────────────────────────────────────

def test_get_venv_python_from_virtual_env_bin(tmp_path, monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path))
    py = tmp_path / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.touch()
    assert manage.get_venv_python() == py


def test_get_venv_python_from_virtual_env_scripts(tmp_path, monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path))
    py = tmp_path / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True)
    py.touch()
    assert manage.get_venv_python() == py


def test_get_venv_python_virtual_env_missing_exe(tmp_path, monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path))
    assert manage.get_venv_python() is None


def test_get_venv_python_from_project_venv(tmp_path, monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr(manage, "PROJECT_ROOT", tmp_path)
    py = tmp_path / "venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.touch()
    assert manage.get_venv_python() == py


def test_get_venv_python_from_project_venv_scripts(tmp_path, monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr(manage, "PROJECT_ROOT", tmp_path)
    py = tmp_path / "venv" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True)
    py.touch()
    assert manage.get_venv_python() == py


def test_get_venv_python_returns_none_when_no_venv(tmp_path, monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr(manage, "PROJECT_ROOT", tmp_path)
    assert manage.get_venv_python() is None


# ── systemctl_available ───────────────────────────────────────────────────────

def test_systemctl_available_returns_true():
    with patch("manage.subprocess.run"):
        assert manage.systemctl_available() is True


def test_systemctl_available_file_not_found():
    with patch("manage.subprocess.run", side_effect=FileNotFoundError):
        assert manage.systemctl_available() is False


def test_systemctl_available_nonzero_exit():
    with patch("manage.subprocess.run",
               side_effect=subprocess.CalledProcessError(1, "systemctl")):
        assert manage.systemctl_available() is False


# ── do_install_deps ───────────────────────────────────────────────────────────

def test_do_install_deps_missing_requirements(env_dir, mock_console):
    manage.do_install_deps(mock_console)
    assert "Not found" in printed(mock_console)


def test_do_install_deps_success(env_dir, mock_console):
    manage.REQUIREMENTS.write_text("rich\n")
    with patch("manage.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        manage.do_install_deps(mock_console)
    assert "success" in printed(mock_console).lower()


def test_do_install_deps_failure(env_dir, mock_console):
    manage.REQUIREMENTS.write_text("rich\n")
    with patch("manage.subprocess.run",
               side_effect=subprocess.CalledProcessError(1, "pip")):
        manage.do_install_deps(mock_console)
    assert "fail" in printed(mock_console).lower()


def test_do_install_deps_no_venv_warns(env_dir, mock_console):
    manage.REQUIREMENTS.write_text("rich\n")
    with patch("manage.get_venv_python", return_value=None):
        with patch("manage.subprocess.run"):
            manage.do_install_deps(mock_console)
    assert "venv" in printed(mock_console).lower() or "interpreter" in printed(mock_console).lower()


# ── do_update_config ──────────────────────────────────────────────────────────

def test_do_update_config_saves_new_token(env_dir, mock_console):
    with patch("manage.Prompt.ask", side_effect=["newtoken", "1,2,3", "UTC", "12:00", "21:00"]):
        manage.do_update_config(mock_console)
    assert manage.load_env()["BOT_TOKEN"] == "newtoken"


def test_do_update_config_saves_admin_ids(env_dir, mock_console):
    with patch("manage.Prompt.ask", side_effect=["tok", "42,99", "UTC", "12:00", "21:00"]):
        manage.do_update_config(mock_console)
    assert manage.load_env()["ADMIN_IDS"] == "42,99"


def test_do_update_config_saves_timezone(env_dir, mock_console):
    with patch("manage.Prompt.ask", side_effect=["tok", "1", "Asia/Tehran", "12:00", "21:00"]):
        manage.do_update_config(mock_console)
    assert manage.load_env()["TIMEZONE"] == "Asia/Tehran"


def test_do_update_config_saves_reminder_times(env_dir, mock_console):
    with patch("manage.Prompt.ask", side_effect=["tok", "1", "UTC", "13:30", "22:00"]):
        manage.do_update_config(mock_console)
    env = manage.load_env()
    assert env["REMINDER_NOON"] == "13:30"
    assert env["REMINDER_NIGHT"] == "22:00"


def test_do_update_config_uses_existing_defaults(env_dir, mock_console):
    manage.ENV_FILE.write_text("BOT_TOKEN=oldtok\nADMIN_IDS=5\nTIMEZONE=UTC\nREMINDER_NOON=12:00\nREMINDER_NIGHT=21:00\n")
    with patch("manage.Prompt.ask", side_effect=["oldtok", "5", "UTC", "12:00", "21:00"]) as mock_ask:
        manage.do_update_config(mock_console)
    first_call_kwargs = mock_ask.call_args_list[0]
    assert "oldtok" in str(first_call_kwargs)


def test_do_update_config_prints_success(env_dir, mock_console):
    with patch("manage.Prompt.ask", side_effect=["t", "1", "UTC", "12:00", "21:00"]):
        manage.do_update_config(mock_console)
    assert "saved" in printed(mock_console).lower() or "config" in printed(mock_console).lower()


# ── do_systemd ────────────────────────────────────────────────────────────────

def test_do_systemd_no_systemctl(mock_console):
    with patch("manage.systemctl_available", return_value=False):
        manage.do_systemd(mock_console)
    assert "systemctl" in printed(mock_console).lower()


def test_do_systemd_back_exits_cleanly(mock_console):
    with patch("manage.systemctl_available", return_value=True):
        with patch("manage.Prompt.ask", return_value="x"):
            manage.do_systemd(mock_console)
    with patch("manage.subprocess.run") as mock_run:
        mock_run.assert_not_called()


def test_do_systemd_invalid_action(mock_console):
    with patch("manage.systemctl_available", return_value=True):
        with patch("manage.Prompt.ask", return_value="z"):
            manage.do_systemd(mock_console)
    assert "invalid" in printed(mock_console).lower()


def test_do_systemd_start_as_root(mock_console, monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: 0, raising=False)
    result = MagicMock(returncode=0, stdout="", stderr="")
    with patch("manage.systemctl_available", return_value=True):
        with patch("manage.Prompt.ask", return_value="a"):
            with patch("manage.subprocess.run", return_value=result) as mock_run:
                manage.do_systemd(mock_console)
    cmd = mock_run.call_args[0][0]
    assert "--user" not in cmd
    assert "start" in cmd


def test_do_systemd_stop_as_user(mock_console, monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: 1000, raising=False)
    result = MagicMock(returncode=0, stdout="ok", stderr="")
    with patch("manage.systemctl_available", return_value=True):
        with patch("manage.Prompt.ask", return_value="b"):
            with patch("manage.subprocess.run", return_value=result):
                manage.do_systemd(mock_console)
    assert "done" in printed(mock_console).lower()


def test_do_systemd_command_fails(mock_console, monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: 0, raising=False)
    result = MagicMock(returncode=1, stdout="", stderr="error msg")
    with patch("manage.systemctl_available", return_value=True):
        with patch("manage.Prompt.ask", return_value="c"):
            with patch("manage.subprocess.run", return_value=result):
                manage.do_systemd(mock_console)
    assert "failed" in printed(mock_console).lower()


def test_do_systemd_timeout(mock_console, monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: 0, raising=False)
    with patch("manage.systemctl_available", return_value=True):
        with patch("manage.Prompt.ask", return_value="d"):
            with patch("manage.subprocess.run",
                       side_effect=subprocess.TimeoutExpired("cmd", 10)):
                manage.do_systemd(mock_console)
    assert "timed out" in printed(mock_console).lower()


def test_do_systemd_generic_exception(mock_console, monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: 0, raising=False)
    with patch("manage.systemctl_available", return_value=True):
        with patch("manage.Prompt.ask", return_value="a"):
            with patch("manage.subprocess.run", side_effect=RuntimeError("boom")):
                manage.do_systemd(mock_console)
    assert "boom" in printed(mock_console).lower() or "error" in printed(mock_console).lower()


# ── do_git_update ─────────────────────────────────────────────────────────────

def test_do_git_update_not_a_repo(env_dir, mock_console):
    manage.do_git_update(mock_console)
    assert "git" in printed(mock_console).lower()


def test_do_git_update_pull_success_no_systemctl(tmp_path, monkeypatch, mock_console):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(manage, "PROJECT_ROOT", tmp_path)
    with patch("manage.subprocess.run", return_value=MagicMock(returncode=0)):
        with patch("manage.systemctl_available", return_value=False):
            manage.do_git_update(mock_console)
    assert "succeeded" in printed(mock_console).lower()


def test_do_git_update_pull_failed(tmp_path, monkeypatch, mock_console):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(manage, "PROJECT_ROOT", tmp_path)
    with patch("manage.subprocess.run",
               side_effect=subprocess.CalledProcessError(1, "git")):
        manage.do_git_update(mock_console)
    assert "fail" in printed(mock_console).lower()


def test_do_git_update_restart_success(tmp_path, monkeypatch, mock_console):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(manage, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(os, "getuid", lambda: 1000, raising=False)
    with patch("manage.subprocess.run",
               side_effect=[MagicMock(returncode=0), MagicMock(returncode=0)]):
        with patch("manage.systemctl_available", return_value=True):
            manage.do_git_update(mock_console)
    assert "restarted" in printed(mock_console).lower()


def test_do_git_update_restart_failed(tmp_path, monkeypatch, mock_console):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(manage, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(os, "getuid", lambda: 0, raising=False)
    with patch("manage.subprocess.run",
               side_effect=[
                   MagicMock(returncode=0),
                   subprocess.CalledProcessError(1, "systemctl"),
               ]):
        with patch("manage.systemctl_available", return_value=True):
            manage.do_git_update(mock_console)
    assert "restart" in printed(mock_console).lower()


def test_do_git_update_root_uses_system_service(tmp_path, monkeypatch, mock_console):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(manage, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(os, "getuid", lambda: 0, raising=False)
    calls = []

    def capture(*args, **kwargs):
        calls.append(args[0] if args else [])
        return MagicMock(returncode=0)

    with patch("manage.subprocess.run", side_effect=capture):
        with patch("manage.systemctl_available", return_value=True):
            manage.do_git_update(mock_console)
    restart_cmd = calls[1]
    assert "--user" not in restart_cmd


# ── do_view_logs ──────────────────────────────────────────────────────────────

class _FakeRow:
    """Minimal sqlite3.Row stand-in."""
    _KEYS = [
        "id", "timestamp", "user_id", "back_pain", "headache", "peace_level",
        "sleep_quality", "sleep_hours", "stress_level", "anxiety_level",
        "water_amount", "smoke_count", "caffeine_amount", "sitting_hours",
        "screen_hours", "food_details", "period_status", "notes",
    ]

    def __init__(self, **kwargs):
        self._data = {k: kwargs.get(k) for k in self._KEYS}

    def __getitem__(self, key):
        return self._data[key]


def test_do_view_logs_db_error(mock_console):
    import db
    with patch.object(db, "init_db", side_effect=Exception("db gone")):
        manage.do_view_logs(mock_console)
    assert "error" in printed(mock_console).lower()


def test_do_view_logs_empty(mock_console):
    import db
    with patch.object(db, "init_db"):
        with patch.object(db, "get_recent_logs", return_value=[]):
            manage.do_view_logs(mock_console)
    assert "no logs" in printed(mock_console).lower()


def test_do_view_logs_shows_rows(mock_console):
    import db
    row = _FakeRow(id=1, user_id=42, timestamp="2024-01-01 00:00:00")
    with patch.object(db, "init_db"):
        with patch.object(db, "get_recent_logs", return_value=[row]):
            manage.do_view_logs(mock_console)
    mock_console.print.assert_called()


def test_do_view_logs_shows_count(mock_console):
    import db
    rows = [_FakeRow(id=i, user_id=i) for i in range(3)]
    with patch.object(db, "init_db"):
        with patch.object(db, "get_recent_logs", return_value=rows):
            manage.do_view_logs(mock_console)
    assert "3" in printed(mock_console)


# ── main ──────────────────────────────────────────────────────────────────────

def test_main_exits_on_choice_0(monkeypatch):
    monkeypatch.setattr(sys, "stdin", MagicMock(isatty=lambda: True))
    mock_console = MagicMock()
    with patch("manage.Console", return_value=mock_console):
        with patch("manage.Prompt.ask", return_value="0"):
            manage.main()
    assert "goodbye" in printed(mock_console).lower()


def test_main_invalid_choice_shows_error(monkeypatch):
    monkeypatch.setattr(sys, "stdin", MagicMock(isatty=lambda: True))
    mock_console = MagicMock()
    with patch("manage.Console", return_value=mock_console):
        with patch("manage.Prompt.ask", side_effect=["9", "0"]):
            manage.main()
    assert "invalid" in printed(mock_console).lower()


def test_main_rich_unavailable_exits(monkeypatch):
    monkeypatch.setattr(sys, "stdin", MagicMock(isatty=lambda: True))
    monkeypatch.setattr(manage, "_RICH_AVAILABLE", False)
    with pytest.raises(SystemExit):
        manage.main()


def test_main_no_tty_opens_dev_tty(monkeypatch):
    mock_tty = MagicMock()
    monkeypatch.setattr(sys, "stdin", MagicMock(isatty=lambda: False))
    mock_console = MagicMock()
    with patch("builtins.open", return_value=mock_tty) as mock_open:
        with patch("manage.Console", return_value=mock_console):
            with patch("manage.Prompt.ask", return_value="0"):
                manage.main()
    mock_open.assert_called_with("/dev/tty", "r")


def test_main_no_tty_no_dev_tty_exits(monkeypatch):
    monkeypatch.setattr(sys, "stdin", MagicMock(isatty=lambda: False))
    with patch("builtins.open", side_effect=OSError("no tty")):
        with pytest.raises(SystemExit):
            manage.main()


def test_main_routes_to_install_deps(monkeypatch):
    monkeypatch.setattr(sys, "stdin", MagicMock(isatty=lambda: True))
    mock_console = MagicMock()
    with patch("manage.Console", return_value=mock_console):
        with patch("manage.Prompt.ask", side_effect=["1", "0"]):
            with patch("manage.do_install_deps") as mock_fn:
                manage.main()
    mock_fn.assert_called_once_with(mock_console)


def test_main_routes_to_update_config(monkeypatch):
    monkeypatch.setattr(sys, "stdin", MagicMock(isatty=lambda: True))
    mock_console = MagicMock()
    with patch("manage.Console", return_value=mock_console):
        with patch("manage.Prompt.ask", side_effect=["2", "0"]):
            with patch("manage.do_update_config") as mock_fn:
                manage.main()
    mock_fn.assert_called_once_with(mock_console)


def test_main_routes_to_systemd(monkeypatch):
    monkeypatch.setattr(sys, "stdin", MagicMock(isatty=lambda: True))
    mock_console = MagicMock()
    with patch("manage.Console", return_value=mock_console):
        with patch("manage.Prompt.ask", side_effect=["3", "0"]):
            with patch("manage.do_systemd") as mock_fn:
                manage.main()
    mock_fn.assert_called_once_with(mock_console)


def test_main_routes_to_view_logs(monkeypatch):
    monkeypatch.setattr(sys, "stdin", MagicMock(isatty=lambda: True))
    mock_console = MagicMock()
    with patch("manage.Console", return_value=mock_console):
        with patch("manage.Prompt.ask", side_effect=["4", "0"]):
            with patch("manage.do_view_logs") as mock_fn:
                manage.main()
    mock_fn.assert_called_once_with(mock_console)


def test_main_routes_to_git_update(monkeypatch):
    monkeypatch.setattr(sys, "stdin", MagicMock(isatty=lambda: True))
    mock_console = MagicMock()
    with patch("manage.Console", return_value=mock_console):
        with patch("manage.Prompt.ask", side_effect=["5", "0"]):
            with patch("manage.do_git_update") as mock_fn:
                manage.main()
    mock_fn.assert_called_once_with(mock_console)
