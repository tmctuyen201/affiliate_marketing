import os

from affiliate_agent.config import Settings, load_settings


def test_load_settings_prefers_direct_env_values(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("EVENT_BUS_URL", "nats://localhost:4222")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:pass@localhost:5432/app")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("SECRET_PROVIDER", "env")

    settings = load_settings()

    assert settings == Settings(
        app_env="test",
        event_bus_url="nats://localhost:4222",
        postgres_dsn="postgresql://user:pass@localhost:5432/app",
        redis_url="redis://localhost:6379/0",
        secret_provider="env",
        telegram_bot_token=None,
    )


def test_load_settings_uses_secret_reference_when_value_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_SECRET", "projects/demo/secrets/telegram-token")

    settings = load_settings(secret_reader=lambda ref: f"secret://{ref}")

    assert settings.telegram_bot_token == "secret://projects/demo/secrets/telegram-token"
