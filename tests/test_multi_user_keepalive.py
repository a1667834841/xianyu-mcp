import pytest

from src.browser_pool import BrowserPoolSettings
from src.multi_user_manager import MultiUserManager
from src.multi_user_registry import MultiUserRegistry


def make_manager(tmp_path):
    pool = BrowserPoolSettings(
        size=2,
        cdp_host="browser",
        start_port=9222,
        profile_root=tmp_path / "browser-pool",
        registry_file=tmp_path / "registry" / "users.json",
        default_display_name_prefix="user",
    )
    registry = MultiUserRegistry(pool, data_root=tmp_path / "users")
    return MultiUserManager(pool_settings=pool, registry=registry)


@pytest.mark.asyncio
async def test_start_keepalive_marks_user_running(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    runtime = type(
        "Runtime",
        (),
        {
            "entry": entry,
            "app": type("App", (), {"start_background_tasks": lambda self: None})(),
        },
    )()
    manager._runtimes[entry.user_id] = runtime

    await manager.start_keepalive(entry.user_id)

    assert manager._runtime_state[entry.user_id]["keepalive_running"] is True


@pytest.mark.asyncio
async def test_check_all_sessions_returns_status_per_user(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    first = manager.create_user()
    second = manager.create_user()

    class FakeApp:
        async def check_session(self):
            return {"valid": True, "last_updated_at": "2026-04-11T10:00:00+00:00"}

    manager._runtimes[first.user_id] = type(
        "Runtime", (), {"entry": first, "app": FakeApp()}
    )()
    manager._runtimes[second.user_id] = type(
        "Runtime", (), {"entry": second, "app": FakeApp()}
    )()

    result = await manager.check_all_sessions()

    assert result[0]["user_id"] == first.user_id
    assert result[0]["cookie_valid"] is True
    assert result[1]["user_id"] == second.user_id


@pytest.mark.asyncio
async def test_stop_keepalive_does_nothing_if_not_running(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    manager._runtime_state[entry.user_id]["keepalive_running"] = False

    runtime = type(
        "Runtime",
        (),
        {
            "entry": entry,
            "app": type("App", (), {"stop_background_tasks": lambda self: None})(),
        },
    )()
    manager._runtimes[entry.user_id] = runtime

    await manager.stop_keepalive(entry.user_id)

    assert manager._runtime_state[entry.user_id]["keepalive_running"] is False


@pytest.mark.asyncio
async def test_check_all_sessions_continues_after_one_user_fails(tmp_path):
    manager = make_manager(tmp_path)
    first = manager.create_user()
    second = manager.create_user()

    class FailingApp:
        async def check_session(self):
            raise RuntimeError("Session check failed")

    class WorkingApp:
        async def check_session(self):
            return {"valid": True, "last_updated_at": "2026-04-11T10:00:00+00:00"}

    manager._runtimes[first.user_id] = type(
        "Runtime", (), {"entry": first, "app": FailingApp()}
    )()
    manager._runtimes[second.user_id] = type(
        "Runtime", (), {"entry": second, "app": WorkingApp()}
    )()

    result = await manager.check_all_sessions()

    assert len(result) == 2
    assert result[0]["user_id"] == first.user_id
    assert result[0]["cookie_present"] is False
    assert result[0]["last_error"] == "Session check failed"
    assert result[1]["user_id"] == second.user_id
    assert result[1]["cookie_valid"] is True
