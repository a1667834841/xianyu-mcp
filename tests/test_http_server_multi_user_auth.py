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

    def get_user_status(self, user_id):
        return {"user_id": user_id, "slot_id": "slot-1", "status": "ready"}


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


async def test_xianyu_refresh_token_invalid_user_id_raises_error(monkeypatch):
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeAuthManagerWithError())

    with pytest.raises(RuntimeError, match="user_not_found"):
        await http_server.xianyu_refresh_token(user_id="invalid-user")


class FakeMultiUserManager:
    async def debug_login(self, user_id=None):
        return {
            "success": True,
            "user_id": user_id or "user-002",
            "slot_id": "slot-2",
            "selected_by": "auto" if user_id is None else "explicit",
            "logged_in": False,
            "qr_code": {
                "url": "https://passport.goofish.com/qrcodeCheck.htm?lgToken=test"
            },
            "message": "请扫码登录",
        }

    async def debug_check_session(self, user_id=None):
        return {
            "success": True,
            "user_id": user_id or "user-001",
            "slot_id": "slot-1",
            "selected_by": "auto" if user_id is None else "explicit",
            "valid": True,
            "last_updated_at": "2026-04-12 10:40:00",
        }

    async def refresh_token(self, user_id):
        return {"success": True, "user_id": user_id, "token": "abc"}


async def test_http_rest_login_uses_debug_login(monkeypatch):
    from starlette.requests import Request
    from mcp_server import http_server

    async def receive():
        return {
            "type": "http.request",
            "body": b'{"user_id":"user-001"}',
            "more_body": False,
        }

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/rest/login",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeMultiUserManager())

    response = await http_server.rest_login(request)
    assert response.status_code == 200
    assert b"user-001" in response.body


async def test_http_rest_check_session_uses_debug_check_session(monkeypatch):
    from starlette.requests import Request
    from mcp_server import http_server

    async def receive():
        return {
            "type": "http.request",
            "body": b'{"user_id":"user-001"}',
            "more_body": False,
        }

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/rest/check_session",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeMultiUserManager())

    response = await http_server.rest_check_session(request)
    assert response.status_code == 200
    assert b"user-001" in response.body


async def test_http_module_no_longer_exports_xianyu_show_qr():
    from mcp_server import http_server

    assert not hasattr(http_server, "xianyu_show_qr")
