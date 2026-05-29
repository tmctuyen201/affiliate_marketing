from dataclasses import dataclass
import os
from typing import Callable


@dataclass(frozen=True)
class Settings:
    app_env: str
    event_bus_url: str
    postgres_dsn: str
    redis_url: str
    secret_provider: str
    telegram_bot_token: str | None


SecretReader = Callable[[str], str]


def load_settings(secret_reader: SecretReader | None = None) -> Settings:
    def get_value(name: str) -> str | None:
        value = os.getenv(name)
        if value:
            return value
        secret_ref = os.getenv(f"{name}_SECRET")
        if secret_ref and secret_reader:
            return secret_reader(secret_ref)
        return None

    return Settings(
        app_env=os.getenv("APP_ENV", "dev"),
        event_bus_url=os.getenv("EVENT_BUS_URL", "nats://localhost:4222"),
        postgres_dsn=os.getenv("POSTGRES_DSN", "postgresql://localhost:5432/app"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        secret_provider=os.getenv("SECRET_PROVIDER", "env"),
        telegram_bot_token=get_value("TELEGRAM_BOT_TOKEN"),
    )
