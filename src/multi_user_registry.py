from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .browser_pool import BrowserPoolSettings


@dataclass(frozen=True)
class UserRegistryEntry:
    user_id: str
    display_name: str
    enabled: bool
    status: str
    created_at: str
    slot_id: str
    cdp_host: str
    cdp_port: int
    chrome_user_data_dir: Path
    token_file: Path


class MultiUserRegistry:
    def __init__(
        self, pool_settings: BrowserPoolSettings, data_root: Path | None = None
    ):
        self.pool_settings = pool_settings
        self.data_root = data_root or Path("/data/users")
        self.registry_file = pool_settings.registry_file
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[UserRegistryEntry]:
        if not self.registry_file.exists():
            return []
        raw = json.loads(self.registry_file.read_text(encoding="utf-8"))
        return [
            UserRegistryEntry(
                **{
                    **item,
                    "cdp_host": self.pool_settings.cdp_host,
                    "cdp_port": self.pool_settings.start_port
                    + self._slot_index(item["slot_id"])
                    - 1,
                    "chrome_user_data_dir": self.pool_settings.profile_root
                    / item["slot_id"]
                    / "profile",
                    "token_file": Path(item["token_file"]),
                }
            )
            for item in raw
        ]

    @staticmethod
    def _slot_index(slot_id: str) -> int:
        return int(slot_id.split("-", 1)[1])

    def _save(self, entries: list[UserRegistryEntry]) -> None:
        payload = []
        for entry in entries:
            item = asdict(entry)
            item["chrome_user_data_dir"] = str(entry.chrome_user_data_dir)
            item["token_file"] = str(entry.token_file)
            payload.append(item)
        self.registry_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def list_users(self) -> list[UserRegistryEntry]:
        return self._load()

    def get_user(self, user_id: str) -> UserRegistryEntry:
        for entry in self._load():
            if entry.user_id == user_id:
                return entry
        raise RuntimeError("user_not_found")

    def create_user(self, display_name: str | None) -> UserRegistryEntry:
        entries = self._load()
        used_slots = {entry.slot_id for entry in entries}
        effective_size = max(1, self.pool_settings.size)
        slot_index = next(
            (
                idx
                for idx in range(1, effective_size + 1)
                if f"slot-{idx}" not in used_slots
            ),
            None,
        )
        if slot_index is None:
            raise RuntimeError("no_available_browser_slot")

        next_id = f"user-{len(entries) + 1:03d}"
        slot_id = f"slot-{slot_index}"
        profile_dir = self.pool_settings.profile_root / slot_id / "profile"
        token_file = self.data_root / next_id / "tokens" / "token.json"
        entry = UserRegistryEntry(
            user_id=next_id,
            display_name=display_name or next_id,
            enabled=True,
            status="pending_login",
            created_at=datetime.now(timezone.utc).isoformat(),
            slot_id=slot_id,
            cdp_host=self.pool_settings.cdp_host,
            cdp_port=self.pool_settings.start_port + slot_index - 1,
            chrome_user_data_dir=profile_dir,
            token_file=token_file,
        )
        self._save([*entries, entry])
        return entry

    def update_user(self, entry: UserRegistryEntry) -> None:
        entries = self._load()
        for i, existing in enumerate(entries):
            if existing.user_id == entry.user_id:
                entries[i] = entry
                self._save(entries)
                return
        raise RuntimeError("user_not_found")
