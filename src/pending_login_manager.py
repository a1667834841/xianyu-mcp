from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class PendingLoginManager:
    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], dict[str, Any]] = {}

    def create_session(
        self,
        t: str,
        ck: str,
        qr_code_url: str,
        expires_at: datetime,
    ) -> dict[str, Any]:
        payload = {
            "t": t,
            "ck": ck,
            "qr_code_url": qr_code_url,
            "expires_at": self._normalize_expires_at(expires_at),
            "phase": "login_required",
        }
        self._sessions[(t, ck)] = payload.copy()
        return payload.copy()

    def get_session(self, t: str, ck: str) -> dict[str, Any]:
        session = self._sessions.get((t, ck))
        if session is None:
            raise ValueError("pending login session not found")

        if self._is_expired(session["expires_at"]):
            self.delete_session(t, ck)
            raise ValueError("pending login session expired")

        return session.copy()

    def delete_session(self, t: str, ck: str) -> None:
        self._sessions.pop((t, ck), None)

    def _normalize_expires_at(self, expires_at: datetime) -> str:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at.astimezone(timezone.utc).isoformat()

    def _is_expired(self, expires_at: str) -> bool:
        return datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc)
