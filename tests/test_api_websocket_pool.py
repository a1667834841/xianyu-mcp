import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.api.websocket_pool import WebSocketPool
from src.api.types import TextContent


class TestWebSocketPool:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        pool = WebSocketPool()
        
        mock_ws = AsyncMock()
        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_ws
            
            result = await pool.connect(cookies_str="test_cookie")
            
            assert result == True
            assert pool.ws == mock_ws

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        pool = WebSocketPool()
        
        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            
            result = await pool.connect(cookies_str="test_cookie")
            
            assert result == False

    @pytest.mark.asyncio
    async def test_send_text_message(self):
        pool = WebSocketPool()
        pool.ws = AsyncMock()
        
        message = TextContent(type="text", text="hello")
        
        result = await pool.send_message(
            conversation_id="conv_123", 
            to_user_id="user_456", 
            message=message
        )
        
        assert result == True
        pool.ws.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_no_connection(self):
        pool = WebSocketPool()
        pool.ws = None
        
        message = TextContent(type="text", text="hello")
        
        result = await pool.send_message(
            conversation_id="conv_123", 
            to_user_id="user_456", 
            message=message
        )
        
        assert result == False

    @pytest.mark.asyncio
    async def test_message_callback(self):
        pool = WebSocketPool()
        
        received_messages = []
        
        async def on_message(msg):
            received_messages.append(msg)
        
        pool.on_message(on_message)
        assert len(pool._message_handlers) == 1
