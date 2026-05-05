import pytest
import hashlib
import json
import asyncio
from unittest.mock import AsyncMock, patch
from src.api.http_client import HttpClient, save_local_auth


class TestHttpClientSign:
    def test_init_loads_device_id_from_auth_file(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "tokens"
        data_dir.mkdir()
        (data_dir / "auth.json").write_text(
            json.dumps({"cookies": {"unb": "123"}, "device_id": "web_saved"}),
            encoding="utf-8",
        )
        monkeypatch.setenv("XIANYU_DATA_DIR", str(data_dir))

        client = HttpClient(cookies=None, device_id="")

        assert client.cookies == {"unb": "123"}
        assert client.device_id == "web_saved"

    def test_init_uses_unb_based_device_id_when_auth_file_has_no_device_id(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "tokens"
        data_dir.mkdir()
        (data_dir / "auth.json").write_text(
            json.dumps({"cookies": {"unb": "4188939592"}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("XIANYU_DATA_DIR", str(data_dir))

        client = HttpClient(cookies=None, device_id="")

        assert client.cookies == {"unb": "4188939592"}
        assert client.device_id == "web_4188939592"

    def test_save_local_auth_preserves_existing_device_id(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "tokens"
        data_dir.mkdir()
        (data_dir / "auth.json").write_text(
            json.dumps({"cookies": {"old": "cookie"}, "device_id": "web_saved"}),
            encoding="utf-8",
        )
        monkeypatch.setenv("XIANYU_DATA_DIR", str(data_dir))

        save_local_auth({"new": "cookie"})

        saved = json.loads((data_dir / "auth.json").read_text(encoding="utf-8"))
        assert saved["cookies"] == {"new": "cookie"}
        assert saved["device_id"] == "web_saved"

    def test_save_cookies_to_file_persists_current_cookies(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "tokens"
        data_dir.mkdir()
        monkeypatch.setenv("XIANYU_DATA_DIR", str(data_dir))

        client = HttpClient(cookies={"cookie2": "abc", "unb": "123"}, device_id="")

        client._save_cookies_to_file()

        saved = json.loads((data_dir / "auth.json").read_text(encoding="utf-8"))
        assert saved["cookies"] == {"cookie2": "abc", "unb": "123"}

    def test_generate_sign_basic(self):
        client = HttpClient(cookies={}, device_id="test_device")
        token = "test_token"
        timestamp = "1234567890"
        data_str = '{"keyword":"test"}'
        
        sign = client._generate_sign(token, timestamp, data_str)
        
        expected = hashlib.md5(
            f"{token}&{timestamp}&{client.APP_KEY}&{data_str}".encode()
        ).hexdigest()
        assert sign == expected

    def test_extract_token_from_cookie(self):
        client = HttpClient(cookies={}, device_id="test_device")
        cookie_str = "_m_h5_tk=test_token_1234567890; other_cookie=value"
        
        token = client._extract_token_from_cookie(cookie_str)
        
        assert token == "test_token"

    def test_extract_token_missing(self):
        client = HttpClient(cookies={}, device_id="test_device")
        cookie_str = "other_cookie=value; session=abc"
        
        token = client._extract_token_from_cookie(cookie_str)
        
        assert token == ""


class TestHttpClientSearch:
    @pytest.mark.asyncio
    async def test_search_success(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": [
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "exContent": {
                                        "itemId": "123",
                                        "title": "测试商品",
                                        "price": [{"text": "¥100"}],
                                    },
                                    "clickParam": {"args": {"item_id": "123"}},
                                }
                            }
                        }
                    }
                ]
            },
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.search(keyword="iPhone", rows=30)
            
            assert len(result) == 1
            assert result[0]["item_id"] == "123"
            assert result[0]["title"] == "测试商品"

    @pytest.mark.asyncio
    async def test_search_session_expired(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["FAIL_SYS_SESSION_EXPIRED::Session 过期"],
            "data": None,
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            with pytest.raises(Exception) as exc_info:
                await client.search(keyword="test", rows=30)
            
            assert "SESSION_EXPIRED" in str(exc_info.value)


class TestHttpClientConversation:
    @pytest.mark.asyncio
    async def test_create_conversation(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {"conversationId": "conv_123"},
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.create_conversation(seller_id="user_456", item_id="item_789")
            
            assert result == "conv_123"

    @pytest.mark.asyncio
    async def test_list_conversations(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "conversationList": [
                    {
                        "conversationId": "conv_123",
                        "userId": "user_456",
                        "userNick": "test_user",
                        "lastMessage": "hello",
                        "lastMessageTime": 1700000000000,
                        "unreadCount": 2,
                    }
                ]
            },
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.list_conversations(limit=20, offset=0)
            
            assert len(result) == 1
            assert result[0].conversation_id == "conv_123"
            assert result[0].user_nick == "test_user"

    @pytest.mark.asyncio
    async def test_get_message_history(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "messageList": [
                    {
                        "messageId": "msg_123",
                        "senderId": "user_456",
                        "receiverId": "user_789",
                        "content": {"type": "text", "text": "hello"},
                        "timestamp": 1700000000000,
                    }
                ],
                "hasMore": False,
            },
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.get_message_history(conversation_id="conv_123", limit=50)
            
            assert len(result["messages"]) == 1
            assert result["has_more"] == False


class TestHttpClientAccessToken:
    @pytest.mark.asyncio
    async def test_get_access_token_returns_empty_when_api_has_no_token(self):
        client = HttpClient(cookies={"unb": "4188939592", "_m_h5_tk": "token_123"}, device_id="web_4188939592")

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"ret": ["FAIL_SYS_USER_VALIDATE"], "data": {}}

            token = await client.get_access_token()

        assert token == ""

    @pytest.mark.asyncio
    async def test_handle_captcha_serializes_concurrent_recovery(self):
        client = HttpClient(cookies={"unb": "4188939592", "_m_h5_tk": "token_123"}, device_id="web_4188939592")

        calls = 0

        async def fake_handle(url, max_retries=3):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return True

        with patch("src.api.captcha_handler.CaptchaHandler.handle", new=AsyncMock(side_effect=fake_handle)):

            await asyncio.gather(
                client._handle_captcha("https://example.com/captcha"),
                client._handle_captcha("https://example.com/captcha"),
            )

        assert calls == 1
