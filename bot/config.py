import os
from dataclasses import dataclass

try:
    # Load variables from a local .env if present
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    # If python-dotenv is not installed, environment variables can still be set externally
    pass


@dataclass(frozen=True)
class Config:
    telegram_token: str
    gemini_api_key: str
    data_dir: str = "data"
    logs_dir: str = "logs"
    retention_days: int = 14
    idle_timeout_minutes: int = 60
    admins: tuple[str, ...] = tuple()


def load_config() -> Config:
    telegram_token = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТЕЛЕГРАМ_ТОКЕН")
    gemini_api_key = os.getenv("GEMINI_API_KEY", "ВАШ_GEMINI_API_КЛЮЧ")
    data_dir = os.getenv("DATA_DIR", "data")
    logs_dir = os.getenv("LOGS_DIR", "logs")
    retention_days = int(os.getenv("RETENTION_DAYS", "14"))
    idle_timeout_minutes = int(os.getenv("IDLE_TIMEOUT_MINUTES", "60"))
    admin_ids_raw = os.getenv("ADMIN_CHAT_IDS", "").strip()
    admins: tuple[str, ...] = tuple(
        [a for a in admin_ids_raw.split(",") if a.strip()] if admin_ids_raw else []
    )
    return Config(
        telegram_token=telegram_token,
        gemini_api_key=gemini_api_key,
        data_dir=data_dir,
        logs_dir=logs_dir,
        retention_days=retention_days,
        idle_timeout_minutes=idle_timeout_minutes,
        admins=admins,
    )


