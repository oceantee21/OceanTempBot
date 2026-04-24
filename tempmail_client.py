from __future__ import annotations

import random
import re
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp


class TempMailError(Exception):
    pass


@dataclass
class InboxMessage:
    id: str
    sender: str
    subject: str
    intro: str
    created_at: str


@dataclass
class MessageDetails:
    id: str
    sender: str
    subject: str
    text: str
    html: str
    created_at: str
    links: list[str]


class MailTmClient:
    def __init__(self, base_url: str = "https://api.mail.tm") -> None:
        self.base_url = base_url.rstrip("/")

    async def get_domains(self) -> list[str]:
        data = await self._request("GET", "/domains?page=1")
        members = data.get("hydra:member", [])
        return [item["domain"] for item in members if item.get("isActive")]

    async def create_account(
        self, preferred_username: str | None = None
    ) -> tuple[str, str, str | None]:
        domains = await self.get_domains()
        if not domains:
            raise TempMailError("No active temp mail domains are available right now.")
        domain = random.choice(domains)
        username = self._sanitize_username(preferred_username) or self._pretty_username()
        address = f"{username}@{domain}"
        password = self._strong_password()

        payload = {"address": address, "password": password}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/accounts",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                if response.status in (200, 201):
                    data = await response.json()
                    return address, password, data.get("id")
                if response.status == 422:
                    # Username collision: retry once with a fresh generated username.
                    retry_address = f"{self._pretty_username()}@{domain}"
                    retry_payload = {"address": retry_address, "password": password}
                    async with session.post(
                        f"{self.base_url}/accounts",
                        json=retry_payload,
                        timeout=aiohttp.ClientTimeout(total=20),
                    ) as retry_response:
                        if retry_response.status in (200, 201):
                            retry_data = await retry_response.json()
                            return retry_address, password, retry_data.get("id")
                body = await response.text()
                raise TempMailError(
                    f"Failed to create temp mailbox (HTTP {response.status}): {body}"
                )

    async def list_messages(self, address: str, password: str) -> list[InboxMessage]:
        token = await self._token(address, password)
        data = await self._request("GET", "/messages?page=1", token=token)
        members = data.get("hydra:member", [])
        return [
            InboxMessage(
                id=msg["id"],
                sender=msg.get("from", {}).get("address", "unknown"),
                subject=msg.get("subject", "(no subject)"),
                intro=msg.get("intro", ""),
                created_at=msg.get("createdAt", ""),
            )
            for msg in members
        ]

    async def get_message(
        self, address: str, password: str, message_id: str
    ) -> MessageDetails:
        token = await self._token(address, password)
        data = await self._request("GET", f"/messages/{message_id}", token=token)

        text = self._normalize_body(data.get("text", ""))
        html = self._normalize_body(data.get("html", ""))
        links = self._extract_links(text + "\n" + html)

        return MessageDetails(
            id=data["id"],
            sender=data.get("from", {}).get("address", "unknown"),
            subject=data.get("subject", "(no subject)"),
            text=text,
            html=html,
            created_at=data.get("createdAt", ""),
            links=links,
        )

    async def delete_account(self, address: str, password: str, account_id: str) -> None:
        token = await self._token(address, password)
        await self._request("DELETE", f"/accounts/{account_id}", token=token)

    async def _token(self, address: str, password: str) -> str:
        data = await self._request(
            "POST", "/token", json_payload={"address": address, "password": password}
        )
        token = data.get("token")
        if not token:
            raise TempMailError("Could not retrieve access token for mailbox.")
        return token

    async def _request(
        self,
        method: str,
        path: str,
        token: str | None = None,
        json_payload: dict | None = None,
    ) -> dict:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                json=json_payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                if response.status >= 400:
                    body = await response.text()
                    raise TempMailError(
                        f"Temp mail API request failed (HTTP {response.status}): {body}"
                    )
                if response.status == 204:
                    return {}
                return await response.json()

    @staticmethod
    def _pretty_username() -> str:
        adjectives = [
            "calm",
            "bright",
            "swift",
            "lucky",
            "cosmic",
            "silent",
            "golden",
            "fresh",
        ]
        nouns = [
            "otter",
            "falcon",
            "spark",
            "river",
            "pixel",
            "comet",
            "leaf",
            "cloud",
        ]
        suffix = datetime.now(timezone.utc).strftime("%H%M%S")
        random_piece = secrets.choice(string.ascii_lowercase + string.digits)
        return f"{random.choice(adjectives)}{random.choice(nouns)}{suffix}{random_piece}"

    @staticmethod
    def _strong_password(length: int = 20) -> str:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def _sanitize_username(raw: str | None) -> str | None:
        if not raw:
            return None
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "", raw).lower()
        if len(cleaned) < 3:
            return None
        return cleaned[:24]

    @staticmethod
    def _extract_links(content: str) -> list[str]:
        if not content:
            return []
        found = re.findall(r"https?://[^\s\"'<>]+", content)
        unique = []
        seen: set[str] = set()
        for link in found:
            if link not in seen:
                seen.add(link)
                unique.append(link)
        return unique[:10]

    @staticmethod
    def _normalize_body(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(str(item) for item in value if item is not None)
        return str(value)
