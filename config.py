from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    database_path: str
    mail_tm_base_url: str


def load_config(config_path: str = "config.json") -> Config:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found at '{config_path}'. "
            "Copy config.example.json to config.json and add your Telegram bot token."
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
