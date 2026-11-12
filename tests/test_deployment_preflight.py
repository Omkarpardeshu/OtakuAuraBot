import os
from pathlib import Path

import pytest

from app.config import Settings
from scripts.preflight import run_preflight


def test_config_requires_webhook_secret_only_for_webhook_mode():
    settings = Settings(telegram_bot_token="token", gemini_api_key="key")
    settings.validate(require_webhook=False)
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        settings.validate(require_webhook=True)


def test_config_rejects_unsafe_prompt_limit():
    settings = Settings(telegram_bot_token="token", gemini_api_key="key", max_prompt_chars=5000)
    with pytest.raises(RuntimeError, match="MAX_PROMPT_CHARS"):
        settings.validate()


def test_preflight_checks_writable_database_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "nested" / "bot.sqlite3"))
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    messages = run_preflight()
    assert len(messages) == 3
    assert (tmp_path / "nested").is_dir()
    assert list((tmp_path / "nested").iterdir()) == []


def test_preflight_fails_when_render_webhook_secret_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "bot.sqlite3"))
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        run_preflight()
