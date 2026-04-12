from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, replace
from typing import Any

from .browser import AsyncChromeManager
from .browser_pool import BrowserPoolSettings
from .core import XianyuApp
from .multi_user_registry import MultiUserRegistry, UserRegistryEntry
from .settings import build_user_settings


@dataclass
class UserRuntime:
    entry: UserRegistryEntry
    app: Any | None = None


class MultiUserManager:
    def __init__(self, pool_settings: BrowserPoolSettings, registry: MultiUserRegistry):
        self.pool_settings = pool_settings
        self.registry = registry
        self.operation_lock = asyncio.Lock()
        self._runtimes: dict[str, UserRuntime] = {}
        self._runtime_state: dict[str, dict[str, Any]] = {}

    def create_user(self, display_name: str | None = None) -> UserRegistryEntry:
        entry = self.registry.create_user(display_name=display_name)
        self._runtime_state[entry.user_id] = {
            "status": entry.status,
            "enabled": entry.enabled,
            "keepalive_running": False,
            "browser_connected": False,
            "cookie_present": False,
            "cookie_valid": False,
            "last_error": None,
            "busy": False,
            "xianyu_nick": None,
        }
        return entry

    def list_users(self) -> list[UserRegistryEntry]:
        return self.registry.list_users()

    def pick_search_user_id(self) -> str:
        ready_users = [
            entry.user_id
            for entry in self.registry.list_users()
            if entry.enabled and entry.status == "ready"
        ]
        if not ready_users:
            raise RuntimeError("no_available_user")
        return secrets.choice(ready_users)

    def _entry_by_user_id(self, user_id: str) -> UserRegistryEntry:
        return self.registry.get_user(user_id)

    def resolve_debug_user(self, user_id: str | None) -> tuple[UserRegistryEntry, str]:
        if user_id is not None:
            return self._entry_by_user_id(user_id), "explicit"
        for entry in self.registry.list_users():
            if entry.enabled and entry.status == "ready":
                return entry, "auto"
        raise RuntimeError("no_available_user")

    def resolve_login_user(self, user_id: str | None) -> tuple[UserRegistryEntry, str]:
        if user_id is not None:
            return self._entry_by_user_id(user_id), "explicit"
        for entry in self.registry.list_users():
            state = self._runtime_state.get(entry.user_id, {})
            status = state.get("status", entry.status)
            cookie_valid = state.get("cookie_valid", False)
            if entry.enabled and not (status == "ready" and cookie_valid):
                return entry, "auto"
        raise RuntimeError("no_available_user")

    async def debug_login(self, user_id: str | None = None) -> dict[str, Any]:
        entry, selected_by = self.resolve_login_user(user_id)
        result = await self.login(entry.user_id)
        return {"slot_id": entry.slot_id, "selected_by": selected_by, **result}

    async def debug_check_session(self, user_id: str | None = None) -> dict[str, Any]:
        entry, selected_by = self.resolve_debug_user(user_id)
        result = await self.check_session(entry.user_id)
        return {"slot_id": entry.slot_id, "selected_by": selected_by, **result}

    async def debug_search(
        self, keyword: str, user_id: str | None = None, **options
    ) -> dict[str, Any]:
        entry, selected_by = self.resolve_debug_user(user_id)
        result = await self.search(keyword=keyword, user_id=entry.user_id, **options)
        result["selected_by"] = selected_by
        return result

    async def debug_browser_overview(
        self, user_id: str | None = None
    ) -> dict[str, Any]:
        if user_id is not None:
            runtime = await self._get_or_create_runtime(user_id)
            overview = await runtime.app.browser_overview()
            return {
                "user_id": user_id,
                "slot_id": runtime.entry.slot_id,
                "selected_by": "explicit",
                **overview,
            }
        users = []
        for runtime in self._runtimes.values():
            overview = await runtime.app.browser_overview()
            users.append(
                {
                    "user_id": runtime.entry.user_id,
                    "slot_id": runtime.entry.slot_id,
                    **overview,
                }
            )
        return {"users": users}

    def _is_keepalive_running(self, user_id: str) -> bool:
        runtime = self._runtimes.get(user_id)
        if runtime is not None and hasattr(runtime.app, "background_tasks_running"):
            return runtime.app.background_tasks_running()
        return self._runtime_state.get(user_id, {}).get("keepalive_running", False)

    def _record_keepalive_success(
        self, user_id: str, last_updated_at: str | None
    ) -> None:
        self._runtime_state[user_id]["last_keepalive_at"] = last_updated_at
        self._runtime_state[user_id]["last_keepalive_status"] = "ok"
        self._runtime_state[user_id]["last_error"] = None

    def _record_keepalive_error(self, user_id: str, message: str) -> None:
        self._runtime_state[user_id]["last_keepalive_status"] = "error"
        self._runtime_state[user_id]["last_error"] = message

    def _ensure_runtime_state(self, entry: UserRegistryEntry) -> dict[str, Any]:
        return self._runtime_state.setdefault(
            entry.user_id,
            {
                "status": entry.status,
                "enabled": entry.enabled,
                "keepalive_running": False,
                "browser_connected": False,
                "cookie_present": False,
                "cookie_valid": False,
                "last_error": None,
                "busy": False,
                "xianyu_nick": None,
            },
        )

    async def _get_or_create_runtime(self, user_id: str) -> UserRuntime:
        if user_id in self._runtimes:
            return self._runtimes[user_id]

        entry = self._entry_by_user_id(user_id)
        state = self._ensure_runtime_state(entry)
        settings = build_user_settings(
            user_id=entry.user_id,
            token_file=entry.token_file,
            chrome_user_data_dir=entry.chrome_user_data_dir,
            data_root=entry.token_file.parents[2],
        )
        browser = AsyncChromeManager(
            host=entry.cdp_host,
            port=entry.cdp_port,
            auto_start=False,
            settings=settings,
        )
        app = XianyuApp(
            browser=browser,
            settings=settings,
            keepalive_on_cookie_saved=lambda ts, _uid=user_id: (
                self._record_keepalive_success(_uid, ts)
            ),
            keepalive_on_error=lambda msg, _uid=user_id: self._record_keepalive_error(
                _uid, msg
            ),
        )
        runtime = UserRuntime(entry=entry, app=app)
        self._runtimes[user_id] = runtime
        state["browser_connected"] = True
        return runtime

    def get_user_status(self, user_id: str) -> dict[str, Any]:
        entry = self._entry_by_user_id(user_id)
        state = self._runtime_state.get(user_id, {})
        return {
            "user_id": entry.user_id,
            "display_name": entry.display_name,
            "xianyu_nick": state.get("xianyu_nick"),
            "enabled": entry.enabled,
            "status": state.get("status", entry.status),
            "slot_id": entry.slot_id,
            "cdp_host": entry.cdp_host,
            "cdp_port": entry.cdp_port,
            "browser_connected": state.get("browser_connected", False),
            "keepalive_running": self._is_keepalive_running(user_id),
            "cookie_present": state.get("cookie_present", False),
            "cookie_valid": state.get("cookie_valid", False),
            "last_cookie_updated_at": state.get("last_cookie_updated_at"),
            "last_keepalive_at": state.get("last_keepalive_at"),
            "last_keepalive_status": state.get("last_keepalive_status"),
            "last_error": state.get("last_error"),
            "busy": state.get("busy", False),
            "token_preview": state.get("token_preview"),
        }

    def list_user_statuses(self) -> list[dict[str, Any]]:
        return [
            self.get_user_status(entry.user_id) for entry in self.registry.list_users()
        ]

    async def search(
        self, keyword: str, user_id: str | None = None, **options
    ) -> dict[str, Any]:
        selected_user_id = user_id or self.pick_search_user_id()
        runtime = await self._get_or_create_runtime(selected_user_id)
        async with self.operation_lock:
            self._runtime_state[selected_user_id]["busy"] = True
            try:
                outcome = await runtime.app.search_with_meta(keyword=keyword, **options)
            finally:
                self._runtime_state[selected_user_id]["busy"] = False

        return {
            "success": True,
            "user_id": selected_user_id,
            "slot_id": runtime.entry.slot_id,
            "requested": outcome.requested_rows,
            "total": outcome.returned_rows,
            "stop_reason": outcome.stop_reason,
            "stale_pages": outcome.stale_pages,
            "items": [item.__dict__ for item in outcome.items],
            "engine_used": outcome.engine_used,
            "fallback_reason": outcome.fallback_reason,
            "pages_fetched": outcome.pages_fetched,
        }

    async def publish(self, user_id: str, item_url: str, **options) -> dict[str, Any]:
        if user_id is None:
            raise TypeError("publish() missing required argument: 'user_id'")
        entry = self._entry_by_user_id(user_id)
        if not entry.enabled:
            raise RuntimeError("user_disabled")
        if entry.status != "ready":
            raise RuntimeError("user_not_logged_in")

        runtime = await self._get_or_create_runtime(user_id)
        async with self.operation_lock:
            self._runtime_state[user_id]["busy"] = True
            try:
                result = await runtime.app.publish(item_url=item_url, **options)
            finally:
                self._runtime_state[user_id]["busy"] = False

        return {"user_id": user_id, "slot_id": runtime.entry.slot_id, **result}

    async def get_detail(self, user_id: str, item_url: str) -> dict[str, Any]:
        if user_id is None:
            raise TypeError("get_detail() missing required argument: 'user_id'")
        entry = self._entry_by_user_id(user_id)
        if not entry.enabled:
            raise RuntimeError("user_disabled")
        if entry.status != "ready":
            raise RuntimeError("user_not_logged_in")

        runtime = await self._get_or_create_runtime(user_id)
        async with self.operation_lock:
            self._runtime_state[user_id]["busy"] = True
            try:
                item = await runtime.app.get_detail(item_url)
            finally:
                self._runtime_state[user_id]["busy"] = False

        if item is None:
            return {"success": False, "user_id": user_id, "error": "获取详情失败"}

        return {
            "success": True,
            "user_id": user_id,
            "slot_id": runtime.entry.slot_id,
            "item_id": item.item_id,
            "title": item.title,
            "description": item.description if item.description else "",
            "category": item.category,
            "category_id": item.category_id,
            "brand": item.brand,
            "model": item.model,
            "min_price": item.min_price,
            "max_price": item.max_price,
            "image_urls": item.image_urls if item.image_urls else [],
            "seller_city": item.seller_city,
            "is_free_ship": item.is_free_ship,
        }

    async def start_keepalive(self, user_id: str) -> None:
        if self._runtime_state.get(user_id, {}).get("keepalive_running"):
            return
        runtime = await self._get_or_create_runtime(user_id)
        runtime.app.start_background_tasks()
        self._runtime_state[user_id]["keepalive_running"] = True

    async def stop_keepalive(self, user_id: str) -> None:
        if not self._runtime_state.get(user_id, {}).get("keepalive_running"):
            return
        runtime = await self._get_or_create_runtime(user_id)
        await runtime.app.stop_background_tasks()
        self._runtime_state[user_id]["keepalive_running"] = False

    async def ensure_keepalive(self, user_id: str) -> None:
        runtime = await self._get_or_create_runtime(user_id)
        runtime.app.start_background_tasks()
        self._runtime_state[user_id]["keepalive_running"] = self._is_keepalive_running(
            user_id
        )

    async def check_all_sessions(self) -> list[dict[str, Any]]:
        results = []
        for entry in self.registry.list_users():
            try:
                runtime = await self._get_or_create_runtime(entry.user_id)
                session_status = await runtime.app.check_session()
                self._runtime_state[entry.user_id]["cookie_valid"] = session_status[
                    "valid"
                ]
                self._runtime_state[entry.user_id]["last_cookie_updated_at"] = (
                    session_status.get("last_updated_at")
                )
                self._runtime_state[entry.user_id]["xianyu_nick"] = session_status.get(
                    "display_name"
                )
                self._runtime_state[entry.user_id]["cookie_present"] = True
                status = "ready" if session_status["valid"] else "pending_login"
                self._runtime_state[entry.user_id]["status"] = status
                updated_entry = replace(entry, status=status)
                self.registry.update_user(updated_entry)
            except Exception as e:
                self._runtime_state[entry.user_id]["last_error"] = str(e)
                self._runtime_state[entry.user_id]["cookie_present"] = False
            results.append(self.get_user_status(entry.user_id))
        return results

    async def login(self, user_id: str) -> dict[str, Any]:
        runtime = await self._get_or_create_runtime(user_id)
        try:
            result = await runtime.app.login(timeout=30)
        except Exception as e:
            raise RuntimeError(f"login_failed: {e}") from e
        if result.get("success"):
            status = (
                "ready"
                if result.get("logged_in") or result.get("token")
                else "pending_login"
            )
            self._runtime_state[user_id]["status"] = status
            entry = self._entry_by_user_id(user_id)
            self.registry.update_user(replace(entry, status=status))
            if status == "ready":
                await self.ensure_keepalive(user_id)
        return {"user_id": user_id, **result}

    async def check_session(self, user_id: str) -> dict[str, Any]:
        runtime = await self._get_or_create_runtime(user_id)
        try:
            result = await runtime.app.check_session()
        except Exception as e:
            raise RuntimeError(f"check_session_failed: {e}") from e
        self._runtime_state[user_id]["cookie_valid"] = result["valid"]
        self._runtime_state[user_id]["cookie_present"] = True
        self._runtime_state[user_id]["last_cookie_updated_at"] = result.get(
            "last_updated_at"
        )
        self._runtime_state[user_id]["xianyu_nick"] = result.get("display_name")
        status = "ready" if result["valid"] else "pending_login"
        self._runtime_state[user_id]["status"] = status
        entry = self._entry_by_user_id(user_id)
        self.registry.update_user(replace(entry, status=status))
        if result["valid"]:
            await self.ensure_keepalive(user_id)
        else:
            await self.stop_keepalive(user_id)
        return {"user_id": user_id, **result}

    async def refresh_token(self, user_id: str) -> dict[str, Any]:
        runtime = await self._get_or_create_runtime(user_id)
        try:
            result = await runtime.app.refresh_token()
        except Exception as e:
            raise RuntimeError(f"refresh_token_failed: {e}") from e
        if result:
            self._runtime_state[user_id]["cookie_present"] = True
            self._runtime_state[user_id]["cookie_valid"] = True
            self._runtime_state[user_id]["status"] = "ready"
            entry = self._entry_by_user_id(user_id)
            self.registry.update_user(replace(entry, status="ready"))
            await self.ensure_keepalive(user_id)
        return {"user_id": user_id, "success": bool(result), **(result or {})}

    async def ensure_initialized(self) -> None:
        for entry in self.registry.list_users():
            try:
                runtime = await self._get_or_create_runtime(entry.user_id)
                session_status = await runtime.app.check_session()
                is_valid = session_status.get("valid", False)
                status = "ready" if is_valid else "pending_login"
                self._runtime_state[entry.user_id]["cookie_valid"] = is_valid
                self._runtime_state[entry.user_id]["cookie_present"] = True
                self._runtime_state[entry.user_id]["last_cookie_updated_at"] = (
                    session_status.get("last_updated_at")
                )
                self._runtime_state[entry.user_id]["xianyu_nick"] = session_status.get(
                    "display_name"
                )
                self._runtime_state[entry.user_id]["status"] = status
                updated_entry = replace(entry, status=status)
                self.registry.update_user(updated_entry)
                if is_valid:
                    await self.start_keepalive(entry.user_id)
                else:
                    await self.stop_keepalive(entry.user_id)
            except Exception as e:
                self._runtime_state[entry.user_id]["last_error"] = str(e)
                self._runtime_state[entry.user_id]["cookie_present"] = False
                self._runtime_state[entry.user_id]["keepalive_running"] = False
