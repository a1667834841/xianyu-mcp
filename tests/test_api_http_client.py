import pytest
import hashlib
from unittest.mock import AsyncMock, patch
from src.api.http_client import HttpClient


class TestHttpClientSign:
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
