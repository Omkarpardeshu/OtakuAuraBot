from app.config import Settings


def test_single_gemini_key_remains_supported(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("GEMINI_API_KEY", "primary-key")
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)

    settings = Settings.from_env()

    assert settings.gemini_api_key == "primary-key"
    assert settings.gemini_api_keys == ("primary-key",)
    settings.validate()


def test_future_comma_separated_keys_are_deduplicated(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("GEMINI_API_KEY", "primary-key")
    monkeypatch.setenv("GEMINI_API_KEYS", "second-key, primary-key, third-key")

    settings = Settings.from_env()

    assert settings.gemini_api_keys == ("primary-key", "second-key", "third-key")
    settings.validate()
