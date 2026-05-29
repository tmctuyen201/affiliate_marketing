from dataclasses import dataclass
import os
from typing import Callable


@dataclass(frozen=True)
class Settings:
    app_env: str = "dev"
    event_bus_url: str = ""
    postgres_dsn: str = ""
    redis_url: str = ""
    secret_provider: str = "env"
    telegram_bot_token: str | None = None


SecretReader = Callable[[str], str]


def load_settings(secret_reader: SecretReader | None = None) -> Settings:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    secret_ref = os.getenv("TELEGRAM_BOT_TOKEN_SECRET")
    if bot_token is None and secret_ref and secret_reader:
        bot_token = secret_reader(secret_ref)

    return Settings(
        app_env=os.getenv("APP_ENV", "dev"),
        event_bus_url=os.getenv("EVENT_BUS_URL", ""),
        postgres_dsn=os.getenv("POSTGRES_DSN", ""),
        redis_url=os.getenv("REDIS_URL", ""),
        secret_provider=os.getenv("SECRET_PROVIDER", "env"),
        telegram_bot_token=bot_token,
    )
