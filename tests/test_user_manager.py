import json
import re
from datetime import datetime, timezone, timedelta

import pytest

from src.user_manager import UserManager


def test_add_user_creates_user_metadata_file(tmp_path):
    manager = UserManager(tmp_path)

    user = manager.add_user("user-1", "alice")

    metadata_path = tmp_path / "user-1" / "user.json"
    assert metadata_path.exists()
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert payload["user_id"] == "user-1"
    assert payload["username"] == "alice"
    assert payload["status"] == "active"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", payload["created_at"])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", payload["updated_at"])
    assert payload["last_login_at"] is None
    assert payload["last_keepalive_at"] is None
    assert payload["keepalive_enabled"] is True
    assert user == payload


def test_list_users_returns_all_users_sorted_by_created_at(tmp_path):
    manager = UserManager(tmp_path)

    first = manager.add_user("user-1", "alice")
    second = manager.add_user("user-2", "bob")

    users = manager.list_users()

    assert [user["user_id"] for user in users] == ["user-1", "user-2"]
    assert users[0]["created_at"] == first["created_at"]
    assert users[1]["created_at"] == second["created_at"]


def test_get_default_user_returns_first_active_user(tmp_path):
    manager = UserManager(tmp_path)

    manager.add_user("user-1", "alice")
    manager.add_user("user-2", "bob")
    manager.disable_user("user-1")

    default_user = manager.get_default_user()

    assert default_user["user_id"] == "user-2"


def test_get_default_user_raises_when_no_active_user(tmp_path):
    manager = UserManager(tmp_path)

    manager.add_user("user-1", "alice")
    manager.disable_user("user-1")

    with pytest.raises(ValueError, match="No active user"):
        manager.get_default_user()


def test_disable_user_only_marks_status_disabled(tmp_path):
    manager = UserManager(tmp_path)

    created = manager.add_user("user-1", "alice")

    disabled = manager.disable_user("user-1")

    assert disabled["status"] == "disabled"
    assert disabled["username"] == created["username"]
    assert (tmp_path / "user-1").is_dir()
    assert (tmp_path / "user-1" / "user.json").exists()


def test_add_user_rejects_existing_non_disabled_user(tmp_path):
    manager = UserManager(tmp_path)
    manager.add_user("user-1", "alice")

    with pytest.raises(ValueError, match="already exists"):
        manager.add_user("user-1", "alice-2")


@pytest.mark.parametrize("user_id", ["", "   ", "../evil", "user/1", "user\\1", ".", ".."])
def test_add_user_rejects_invalid_user_id(tmp_path, user_id):
    manager = UserManager(tmp_path)

    with pytest.raises(ValueError, match="Invalid user_id"):
        manager.add_user(user_id, "alice")


def test_add_user_allows_recreating_disabled_user(tmp_path):
    manager = UserManager(tmp_path)
    manager.add_user("user-1", "alice")
    manager.disable_user("user-1")

    recreated = manager.add_user("user-1", "alice-new")

    assert recreated["status"] == "active"
    assert recreated["username"] == "alice-new"


def test_get_user_returns_existing_metadata(tmp_path):
    manager = UserManager(tmp_path)
    created = manager.add_user("user-1", "alice")

    loaded = manager.get_user("user-1")

    assert loaded == created


def test_update_user_persists_changes_and_updates_timestamp(tmp_path):
    manager = UserManager(tmp_path)
    created = manager.add_user("user-1", "alice")

    updated = manager.update_user(
        "user-1",
        username="alice-2",
        last_login_at="2026-05-07 12:00:00",
        last_keepalive_at="2026-05-07 13:00:00",
        keepalive_enabled=False,
    )

    assert updated["user_id"] == "user-1"
    assert updated["username"] == "alice-2"
    assert updated["last_login_at"] == "2026-05-07 12:00:00"
    assert updated["last_keepalive_at"] == "2026-05-07 13:00:00"
    assert updated["keepalive_enabled"] is False
    assert updated["created_at"] == created["created_at"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", updated["updated_at"])
    assert manager.get_user("user-1") == updated


@pytest.mark.parametrize("field", ["user_id", "created_at", "updated_at", "unknown_field"])
def test_update_user_rejects_immutable_or_unknown_fields(tmp_path, field):
    manager = UserManager(tmp_path)
    manager.add_user("user-1", "alice")

    with pytest.raises(ValueError, match="Cannot update field"):
        manager.update_user("user-1", **{field: "changed"})


def test_get_user_raises_with_context_for_invalid_json(tmp_path):
    manager = UserManager(tmp_path)
    metadata_path = tmp_path / "user-1" / "user.json"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(ValueError, match="user-1"):
        manager.get_user("user-1")


def test_list_users_skips_invalid_json_and_logs_warning(tmp_path, caplog):
    manager = UserManager(tmp_path)
    manager.add_user("user-1", "alice")
    broken_path = tmp_path / "user-2" / "user.json"
    broken_path.parent.mkdir(parents=True)
    broken_path.write_text("{invalid", encoding="utf-8")

    users = manager.list_users()

    assert [user["user_id"] for user in users] == ["user-1"]
    assert "user-2" in caplog.text
    assert "Invalid user metadata" in caplog.text


def test_list_users_sorts_by_parsed_created_at_and_falls_back_for_invalid_timestamp(tmp_path):
    manager = UserManager(tmp_path)
    first_path = tmp_path / "user-1" / "user.json"
    first_path.parent.mkdir(parents=True)
    first_path.write_text(json.dumps({
        "user_id": "user-1",
        "username": "alice",
        "status": "active",
        "created_at": "2026-01-02T00:00:00+00:00",
        "updated_at": "2026-01-02T00:00:00+00:00",
        "last_login_at": None,
        "last_keepalive_at": None,
        "keepalive_enabled": True,
    }), encoding="utf-8")
    second_path = tmp_path / "user-2" / "user.json"
    second_path.parent.mkdir(parents=True)
    second_path.write_text(json.dumps({
        "user_id": "user-2",
        "username": "bob",
        "status": "active",
        "created_at": "not-a-timestamp",
        "updated_at": "2026-01-03T00:00:00+00:00",
        "last_login_at": None,
        "last_keepalive_at": None,
        "keepalive_enabled": True,
    }), encoding="utf-8")

    users = manager.list_users()

    assert [user["user_id"] for user in users] == ["user-1", "user-2"]


def test_list_users_keeps_sorting_with_legacy_iso_timestamps(tmp_path):
    manager = UserManager(tmp_path)
    first_path = tmp_path / "user-1" / "user.json"
    first_path.parent.mkdir(parents=True)
    first_path.write_text(json.dumps({
        "user_id": "user-1",
        "username": "alice",
        "status": "active",
        "created_at": "2026-01-02T00:00:00+00:00",
        "updated_at": "2026-01-02T00:00:00+00:00",
        "last_login_at": None,
        "last_keepalive_at": None,
        "keepalive_enabled": True,
    }), encoding="utf-8")
    second_path = tmp_path / "user-2" / "user.json"
    second_path.parent.mkdir(parents=True)
    second_path.write_text(json.dumps({
        "user_id": "user-2",
        "username": "bob",
        "status": "active",
        "created_at": "2026-01-02 00:00:01",
        "updated_at": "2026-01-02 00:00:01",
        "last_login_at": None,
        "last_keepalive_at": None,
        "keepalive_enabled": True,
    }), encoding="utf-8")

    users = manager.list_users()

    assert [user["user_id"] for user in users] == ["user-1", "user-2"]


def test_get_user_formats_legacy_iso_timestamps_for_display(tmp_path):
    manager = UserManager(tmp_path)
    metadata_path = tmp_path / "user-1" / "user.json"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(json.dumps({
        "user_id": "user-1",
        "username": "alice",
        "status": "active",
        "created_at": "2026-05-08T04:32:51.024153+00:00",
        "updated_at": "2026-05-08T06:25:31.695313+00:00",
        "last_login_at": "2026-05-08T04:32:51.024427+00:00",
        "last_keepalive_at": "2026-05-08T06:25:31.576966+00:00",
        "keepalive_enabled": True,
    }), encoding="utf-8")

    user = manager.get_user("user-1")

    assert user["created_at"] == "2026-05-08 04:32:51"
    assert user["updated_at"] == "2026-05-08 06:25:31"
    assert user["last_login_at"] == "2026-05-08 04:32:51"
    assert user["last_keepalive_at"] == "2026-05-08 06:25:31"


@pytest.mark.parametrize("method_name", ["get_user", "disable_user"])
def test_missing_user_methods_raise_clear_errors(tmp_path, method_name):
    manager = UserManager(tmp_path)

    with pytest.raises(ValueError, match="missing-user"):
        getattr(manager, method_name)("missing-user")


def test_update_user_missing_user_raises_clear_error(tmp_path):
    manager = UserManager(tmp_path)

    with pytest.raises(ValueError, match="missing-user"):
        manager.update_user("missing-user", username="alice")


def test_now_iso_uses_shanghai_timezone(tmp_path):
    from datetime import timezone, timedelta
    manager = UserManager(tmp_path)
    result = manager._now_iso()
    now_shanghai = datetime.now(timezone(timedelta(hours=8)))
    expected_prefix = now_shanghai.strftime("%Y-%m-%d %H")
    assert result.startswith(expected_prefix), f"Expected Shanghai time starting with {expected_prefix}, got {result}"
