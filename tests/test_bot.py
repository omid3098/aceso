"""Tests for bot.py – entry point and config loading."""
import importlib
import os

import pytest

import bot


@pytest.fixture(autouse=True)
def reload_bot_module():
    """Reload bot after each test so module-level os.getenv is fresh."""
    yield
    importlib.reload(bot)


def test_main_prints_message_when_no_token(capsys, monkeypatch):
    monkeypatch.setattr(bot, "BOT_TOKEN", "")
    bot.main()
    out = capsys.readouterr().out
    assert "BOT_TOKEN" in out


def test_main_prints_placeholder_when_token_set(capsys, monkeypatch):
    monkeypatch.setattr(bot, "BOT_TOKEN", "abc:123")
    monkeypatch.setattr(bot, "ADMIN_IDS_STR", "42")
    bot.main()
    out = capsys.readouterr().out
    assert "placeholder" in out.lower() or "token" in out.lower()


def test_main_prints_admin_ids(capsys, monkeypatch):
    monkeypatch.setattr(bot, "BOT_TOKEN", "tok")
    monkeypatch.setattr(bot, "ADMIN_IDS_STR", "10,20")
    bot.main()
    out = capsys.readouterr().out
    assert "10" in out
    assert "20" in out


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
        mp.setenv("BOT_TOKEN", "test_token_xyz")
        importlib.reload(bot)
        assert bot.BOT_TOKEN == "test_token_xyz"


def test_admin_ids_str_loaded_from_env():
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("ADMIN_IDS", "55,66")
        importlib.reload(bot)
        assert bot.ADMIN_IDS_STR == "55,66"
