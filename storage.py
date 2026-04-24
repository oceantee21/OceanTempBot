from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock


@dataclass
class Mailbox:
    address: str
    password: str
    account_id: str | None = None
    created_at: str | None = None


@dataclass
class UserRecord:
    telegram_user_id: int
    telegram_chat_id: int
    username: str | None = None
    first_name: str | None = None
    mailboxes: list[Mailbox] = field(default_factory=list)


class JsonStorage:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.lock = Lock()
        if not self.path.exists():
            self.path.write_text(json.dumps({"users": {}}, indent=2), encoding="utf-8")

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, payload: dict) -> None:
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def ensure_user(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        username: str | None,
        first_name: str | None,
    ) -> tuple[UserRecord, bool]:
        user_key = str(telegram_user_id)
        with self.lock:
            db = self._read()
            created = False
            users = db.setdefault("users", {})
            if user_key not in users:
                users[user_key] = asdict(
                    UserRecord(
                        telegram_user_id=telegram_user_id,
                        telegram_chat_id=telegram_chat_id,
                        username=username,
                        first_name=first_name,
                    )
                )
                created = True
            else:
                users[user_key]["telegram_chat_id"] = telegram_chat_id
                users[user_key]["username"] = username
                users[user_key]["first_name"] = first_name
            self._write(db)
            return self._to_user(users[user_key]), created

    def get_user(self, telegram_user_id: int) -> UserRecord | None:
        with self.lock:
            db = self._read()
            data = db.get("users", {}).get(str(telegram_user_id))
            if not data:
                return None
            return self._to_user(data)

    def add_mailbox(self, telegram_user_id: int, mailbox: Mailbox) -> UserRecord:
        with self.lock:
            db = self._read()
            users = db.setdefault("users", {})
            user = users[str(telegram_user_id)]
            user.setdefault("mailboxes", []).append(asdict(mailbox))
            self._write(db)
            return self._to_user(user)

    def delete_mailbox(self, telegram_user_id: int, address: str) -> Mailbox | None:
        with self.lock:
            db = self._read()
            users = db.get("users", {})
            user = users.get(str(telegram_user_id))
            if not user:
                return None
            items = user.get("mailboxes", [])
            for idx, mailbox in enumerate(items):
                if mailbox["address"].lower() == address.lower():
                    removed = items.pop(idx)
                    self._write(db)
                    return Mailbox(**removed)
            return None

    @staticmethod
    def _to_user(raw: dict) -> UserRecord:
        return UserRecord(
            telegram_user_id=raw["telegram_user_id"],
            telegram_chat_id=raw["telegram_chat_id"],
            username=raw.get("username"),
            first_name=raw.get("first_name"),
            mailboxes=[Mailbox(**m) for m in raw.get("mailboxes", [])],
        )
