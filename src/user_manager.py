from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


IMMUTABLE_FIELDS = {"user_id", "created_at", "updated_at"}
MUTABLE_FIELDS = {
    "username",
    "status",
    "last_login_at",
    "last_keepalive_at",
    "keepalive_enabled",
}
TIMESTAMP_FIELDS = {"created_at", "updated_at", "last_login_at", "last_keepalive_at"}

logger = logging.getLogger(__name__)

SHANGHAI_TZ = timezone(timedelta(hours=8))


class UserManager:
    def __init__(self, data_root: Path | str):
        self._data_root = Path(data_root)

    def add_user(self, user_id: str, username: str) -> dict[str, Any]:
        self._validate_user_id(user_id)
        user_path = self._user_metadata_path(user_id)
        if user_path.exists():
            existing = self.get_user(user_id)
            if existing.get("status") != "disabled":
                raise ValueError(f"User '{user_id}' already exists")

        now = self._now_iso()
        payload = {
            "user_id": user_id,
            "username": username,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
            "last_keepalive_at": None,
            "keepalive_enabled": True,
        }
        self._write_user(user_id, payload)
        return payload

    def list_users(self) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        if not self._data_root.exists():
            return users

        for child in self._data_root.iterdir():
            if not child.is_dir():
                continue
            metadata_path = child / "user.json"
            if not metadata_path.exists():
                continue
            try:
                users.append(self._read_user_metadata(child.name, metadata_path))
            except ValueError as exc:
                logger.warning("Skipping invalid user metadata: %s", exc)

        return sorted(users, key=self._sort_key)

    def get_default_user(self) -> dict[str, Any]:
        for user in self.list_users():
            if user.get("status") == "active":
                return user
        raise ValueError("No active user found")

    def get_user(self, user_id: str) -> dict[str, Any]:
        self._validate_user_id(user_id)
        metadata_path = self._user_metadata_path(user_id)
        if not metadata_path.exists():
            raise ValueError(f"User '{user_id}' not found")
        return self._read_user_metadata(user_id, metadata_path)

    def update_user(self, target_user_id: str, **changes: Any) -> dict[str, Any]:
        self._validate_user_id(target_user_id)
        self._validate_update_fields(changes)
        payload = self.get_user(target_user_id)
        payload.update(changes)
        payload["updated_at"] = self._now_iso()
        self._write_user(target_user_id, payload)
        return payload

    def disable_user(self, user_id: str) -> dict[str, Any]:
        self._validate_user_id(user_id)
        return self.update_user(user_id, status="disabled")

    def _user_metadata_path(self, user_id: str) -> Path:
        return self._data_root / user_id / "user.json"

    def _write_user(self, user_id: str, payload: dict[str, Any]) -> None:
        metadata_path = self._user_metadata_path(user_id)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _read_user_metadata(self, user_id: str, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid user metadata for '{user_id}' at '{path}': {exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid user metadata for '{user_id}' at '{path}': root must be an object")
        for field in TIMESTAMP_FIELDS:
            payload[field] = self._format_timestamp(payload.get(field))
        return payload

    def _validate_user_id(self, user_id: str) -> None:
        if not isinstance(user_id, str):
            raise ValueError("Invalid user_id: must be a non-empty string")
        if not user_id.strip():
            raise ValueError("Invalid user_id: must not be blank")
        if user_id in {".", ".."}:
            raise ValueError("Invalid user_id: reserved path segment")
        if ".." in user_id or "/" in user_id or "\\" in user_id:
            raise ValueError("Invalid user_id: must not contain path separators or '..'")

    def _validate_update_fields(self, changes: dict[str, Any]) -> None:
        for field in changes:
            if field in IMMUTABLE_FIELDS or field not in MUTABLE_FIELDS:
                raise ValueError(f"Cannot update field '{field}'")

    def _sort_key(self, user: dict[str, Any]) -> tuple[int, datetime, str, str]:
        created_at = user.get("created_at")
        parsed = self._parse_timestamp(created_at)
        if parsed is not None:
            return (0, parsed, user.get("user_id") or "", created_at or "")
        return (1, datetime.max.replace(tzinfo=timezone.utc), user.get("user_id") or "", created_at or "")

    def _parse_timestamp(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _format_timestamp(self, value: Any) -> Any:
        parsed = self._parse_timestamp(value)
        if parsed is None:
            return value
        return parsed.strftime("%Y-%m-%d %H:%M:%S")

    def _now_iso(self) -> str:
        return datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")
