from datetime import datetime, timedelta, timezone

import pytest

from src.pending_login_manager import PendingLoginManager


def test_create_session_returns_login_required_payload():
    manager = PendingLoginManager()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    expected_expires_at = expires_at.astimezone(timezone.utc).isoformat()

    payload = manager.create_session(
        t="token-1",
        ck="cookie-1",
        qr_code_url="https://example.com/qr.png",
        expires_at=expires_at,
    )

    assert payload == {
        "t": "token-1",
        "ck": "cookie-1",
        "qr_code_url": "https://example.com/qr.png",
        "expires_at": expected_expires_at,
        "phase": "login_required",
    }
    assert isinstance(payload["expires_at"], str)


def test_get_session_returns_existing_session():
    manager = PendingLoginManager()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    created = manager.create_session(
        t="token-1",
        ck="cookie-1",
        qr_code_url="https://example.com/qr.png",
        expires_at=expires_at,
    )

    loaded = manager.get_session("token-1", "cookie-1")

    assert loaded == created
    assert loaded is not created


def test_create_session_returns_copy_not_internal_reference():
    manager = PendingLoginManager()
    created = manager.create_session(
        t="token-1",
        ck="cookie-1",
        qr_code_url="https://example.com/qr.png",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    created["phase"] = "mutated"

    loaded = manager.get_session("token-1", "cookie-1")

    assert loaded["phase"] == "login_required"


def test_get_session_returns_copy_not_internal_reference():
    manager = PendingLoginManager()
    manager.create_session(
        t="token-1",
        ck="cookie-1",
        qr_code_url="https://example.com/qr.png",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    loaded = manager.get_session("token-1", "cookie-1")
    loaded["phase"] = "mutated"

    reloaded = manager.get_session("token-1", "cookie-1")

    assert reloaded["phase"] == "login_required"


def test_get_session_raises_when_session_missing():
    manager = PendingLoginManager()

    with pytest.raises(ValueError, match="pending login session not found"):
        manager.get_session("missing-token", "missing-cookie")


def test_get_session_raises_when_session_expired():
    manager = PendingLoginManager()
    manager.create_session(
        t="token-1",
        ck="cookie-1",
        qr_code_url="https://example.com/qr.png",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    with pytest.raises(ValueError, match="expired"):
        manager.get_session("token-1", "cookie-1")

    with pytest.raises(ValueError, match="pending login session not found"):
        manager.get_session("token-1", "cookie-1")


def test_delete_session_removes_existing_session():
    manager = PendingLoginManager()
    manager.create_session(
        t="token-1",
        ck="cookie-1",
        qr_code_url="https://example.com/qr.png",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    manager.delete_session("token-1", "cookie-1")

    with pytest.raises(ValueError, match="pending login session not found"):
        manager.get_session("token-1", "cookie-1")
