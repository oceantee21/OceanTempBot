from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    database_path: str
    mail_tm_base_url: str


def load_config(config_path: str = "config.json") -> Config:
    path = Path(config_path)
    env_token = (
        os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        or os.getenv("BOT_TOKEN", "").strip()
        or os.getenv("TOKEN", "").strip()
    )
    env_db_path = os.getenv("DATABASE_PATH", "bot_data.json").strip() or "bot_data.json"
    env_base_url = os.getenv("MAIL_TM_BASE_URL", "https://api.mail.tm").strip() or "https://api.mail.tm"

    # Cloud-friendly mode: allow running fully from environment variables.
    if env_token:
        return Config(
            telegram_bot_token=env_token,
            database_path=env_db_path,
            mail_tm_base_url=env_base_url,
        )

    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found at '{config_path}'. "
            "Either create config.json or set TELEGRAM_BOT_TOKEN (or BOT_TOKEN/TOKEN) environment variable."
        )

    raw = json.loads(path.read_text(encoding="utf-8"))
    token = raw.get("telegram_bot_token", "").strip()
    if not token or token == "PUT_YOUR_BOT_TOKEN_HERE":
        raise ValueError(
            "telegram_bot_token is missing or still set to placeholder in config.json."
        )

    return Config(
        telegram_bot_token=token,
        database_path=raw.get("database_path", "bot_data.json"),
        mail_tm_base_url=raw.get("mail_tm_base_url", "https://api.mail.tm"),
    )
