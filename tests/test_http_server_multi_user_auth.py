import json

import pytest

from mcp_server import http_server


class FakeAuthManager:
    async def login(self, user_id):
        return {"success": True, "user_id": user_id, "need_qr": True}

    async def show_qr(self, user_id):
        return {"success": True, "user_id": user_id, "message": "请扫码登录"}

    async def check_session(self, user_id):
        return {"success": True, "user_id": user_id, "valid": True}

    async def refresh_token(self, user_id):
        return {"success": True, "user_id": user_id, "token": "abc"}


class FakeAuthManagerWithError:
    async def show_qr(self, user_id):
        raise RuntimeError("user_not_found")

    async def refresh_token(self, user_id):
        raise RuntimeError("user_not_found")


async def test_xianyu_login_routes_user_id(monkeypatch):
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeAuthManager())

    payload = json.loads(await http_server.xianyu_login(user_id="user-001"))

    assert payload["user_id"] == "user-001"


async def test_xianyu_check_session_routes_user_id(monkeypatch):
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeAuthManager())

    payload = json.loads(await http_server.xianyu_check_session(user_id="user-001"))

    assert payload["valid"] is True


async def test_xianyu_refresh_token_routes_user_id(monkeypatch):
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeAuthManager())

    payload = json.loads(await http_server.xianyu_refresh_token(user_id="user-001"))

    assert payload["user_id"] == "user-001"
    assert payload["success"] is True
    assert payload["token"] == "abc"


async def test_xianyu_show_qr_routes_user_id(monkeypatch):
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeAuthManager())

    payload = json.loads(await http_server.xianyu_show_qr(user_id="user-001"))

    assert payload["user_id"] == "user-001"
    assert payload["success"] is True
    assert payload["message"] == "请扫码登录"


async def test_xianyu_show_qr_invalid_user_id_raises_error(monkeypatch):
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeAuthManagerWithError())

    with pytest.raises(RuntimeError, match="user_not_found"):
        await http_server.xianyu_show_qr(user_id="invalid-user")


async def test_xianyu_refresh_token_invalid_user_id_raises_error(monkeypatch):
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeAuthManagerWithError())

    with pytest.raises(RuntimeError, match="user_not_found"):
        await http_server.xianyu_refresh_token(user_id="invalid-user")
