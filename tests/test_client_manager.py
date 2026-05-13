import asyncio
from pathlib import Path

import pytest

from src.client_manager import ClientManager


class FakeClient:
    def __init__(self, user_id, data_root=None, config_path=None):
        self.user_id = user_id
        self.data_root = data_root
        self.config_path = config_path
        self.check_session_result = {"valid": True}
        self.refresh_token_result = {"success": True, "method": "http"}
        self.stop_ws_listener_called = False
        self.stop_ws_listener_result = {"success": True}

    async def check_session(self):
        return self.check_session_result

    async def refresh_token(self):
        return self.refresh_token_result

    async def stop_ws_listener(self):
        self.stop_ws_listener_called = True
        return self.stop_ws_listener_result


class FakeUserManager:
    def __init__(self):
        self.users = {}

    def add_user(self, user_id, username="test"):
        now = "2026-05-07T12:00:00+00:00"
        user = {
            "user_id": user_id,
            "username": username,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
            "last_keepalive_at": None,
            "keepalive_enabled": True,
        }
        self.users[user_id] = user
        return dict(user)

    def get_user(self, user_id):
        if user_id not in self.users:
            raise ValueError(f"User '{user_id}' not found")
        return dict(self.users[user_id])

    def update_user(self, user_id, **changes):
        if user_id not in self.users:
            raise ValueError(f"User '{user_id}' not found")
        self.users[user_id].update(changes)
        self.users[user_id]["updated_at"] = "2026-05-07T12:00:00+00:00"
        return dict(self.users[user_id])

    def list_users(self):
        return [dict(u) for u in self.users.values()]


@pytest.fixture
def user_manager():
    um = FakeUserManager()
    um.add_user("user-1")
    um.add_user("user-2")
    return um


@pytest.fixture
def data_root(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def fake_client_factory():
    def factory(user_id, data_root=None, config_path=None):
        return FakeClient(user_id, data_root, config_path)

    return factory


@pytest.fixture
def manager(user_manager, data_root, fake_client_factory):
    return ClientManager(
        user_manager=user_manager,
        data_root=data_root,
        client_factory=fake_client_factory,
    )


class TestGetClient:
    async def test_get_client_creates_new_client_when_not_cached(self, manager):
        client = manager.get_client("user-1")

        assert client is not None
        assert client.user_id == "user-1"

    async def test_get_client_returns_same_instance_on_multiple_calls(self, manager):
        client1 = manager.get_client("user-1")
        client2 = manager.get_client("user-1")

        assert client1 is client2

    async def test_get_client_creates_separate_instances_for_different_users(
        self, manager
    ):
        client1 = manager.get_client("user-1")
        client2 = manager.get_client("user-2")

        assert client1 is not client2
        assert client1.user_id == "user-1"
        assert client2.user_id == "user-2"


class TestHasClient:
    async def test_has_client_false_when_not_created(self, manager):
        assert manager.has_client("user-1") is False

    async def test_has_client_true_after_get_client(self, manager):
        manager.get_client("user-1")

        assert manager.has_client("user-1") is True

    async def test_has_client_false_for_unknown_user(self, manager):
        manager.get_client("user-1")

        assert manager.has_client("nonexistent") is False


class TestHasKeepaliveTask:
    async def test_has_keepalive_task_false_by_default(self, manager):
        assert manager.has_keepalive_task("user-1") is False

    async def test_has_keepalive_task_true_after_start(self, manager):
        manager.get_client("user-1")
        await manager.start_keepalive("user-1", interval_minutes=999)

        assert manager.has_keepalive_task("user-1") is True

    async def test_has_keepalive_task_false_after_stop(self, manager):
        manager.get_client("user-1")
        await manager.start_keepalive("user-1", interval_minutes=999)
        await manager.stop_user("user-1")

        assert manager.has_keepalive_task("user-1") is False

    async def test_start_keepalive_twice_cancels_old_task(self, manager):
        await manager.start_keepalive("user-1", interval_minutes=999)
        old_task = manager._keepalive_tasks["user-1"]

        await manager.start_keepalive("user-1", interval_minutes=999)
        new_task = manager._keepalive_tasks["user-1"]

        assert old_task.done()
        assert old_task is not new_task
        assert not new_task.done()


class TestRunKeepaliveOnce:
    async def test_keepalive_valid_session_refreshes_token_and_updates_active(
        self, manager, user_manager
    ):
        client = manager.get_client("user-1")
        client.check_session_result = {"valid": True}

        await manager.run_keepalive_once("user-1")

        updated = user_manager.get_user("user-1")
        assert updated["status"] == "active"
        assert updated["last_keepalive_at"] is not None

    async def test_keepalive_invalid_session_updates_expired(
        self, manager, user_manager
    ):
        client = manager.get_client("user-1")
        client.check_session_result = {"valid": False}

        await manager.run_keepalive_once("user-1")

        updated = user_manager.get_user("user-1")
        assert updated["status"] == "expired"
        assert updated["last_keepalive_at"] is not None

    async def test_keepalive_exception_updates_error(self, manager, user_manager):
        client = manager.get_client("user-1")

        async def failing_check():
            raise RuntimeError("connection failed")

        client.check_session = failing_check

        await manager.run_keepalive_once("user-1")

        updated = user_manager.get_user("user-1")
        assert updated["status"] == "error"
        assert updated["last_keepalive_at"] is not None


class TestStopUser:
    async def test_stop_user_cancels_keepalive_task(self, manager):
        manager.get_client("user-1")
        await manager.start_keepalive("user-1", interval_minutes=999)
        assert manager.has_keepalive_task("user-1") is True

        await manager.stop_user("user-1")

        assert manager.has_keepalive_task("user-1") is False

    async def test_stop_user_calls_stop_ws_listener(self, manager):
        client = manager.get_client("user-1")

        await manager.stop_user("user-1")

        assert client.stop_ws_listener_called is True


class TestShutdown:
    async def test_shutdown_stops_all_users(self, manager):
        manager.get_client("user-1")
        manager.get_client("user-2")
        await manager.start_keepalive("user-1", interval_minutes=999)
        await manager.start_keepalive("user-2", interval_minutes=999)

        await manager.shutdown()

        assert manager.has_keepalive_task("user-1") is False
        assert manager.has_keepalive_task("user-2") is False
