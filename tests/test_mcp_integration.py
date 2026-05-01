import pytest
import json
from unittest.mock import AsyncMock, patch
from mcp_server.server import call_tool


class TestMCPToolsIntegration:
    @pytest.mark.asyncio
    async def test_xianyu_login_success(self):
        """测试登录工具"""
        with patch("mcp_server.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.login.return_value = {
                "success": True,
                "logged_in": False,
                "qr_code_url": "https://example.com/qr"
            }
            mock_get_client.return_value = mock_client
            
            result = await call_tool("xianyu_login", {"timeout": 300})
            
            assert len(result.content) == 1
            data = json.loads(result.content[0].text)
            assert data["success"] == True
            assert data["qr_code_url"] == "https://example.com/qr"

    @pytest.mark.asyncio
    async def test_xianyu_search_success(self):
        """测试搜索工具"""
        with patch("mcp_server.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.search.return_value = [
                {
                    "item_id": "123",
                    "title": "测试商品",
                    "price": "¥100",
                }
            ]
            mock_get_client.return_value = mock_client
            
            result = await call_tool("xianyu_search", {"keyword": "iPhone", "rows": 30})
            
            data = json.loads(result.content[0].text)
            assert len(data["items"]) == 1
            assert data["items"][0]["item_id"] == "123"

    @pytest.mark.asyncio
    async def test_xianyu_create_conversation(self):
        """测试创建对话工具"""
        with patch("mcp_server.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.create_conversation.return_value = "conv_123"
            mock_get_client.return_value = mock_client
            
            result = await call_tool("xianyu_create_conversation", {
                "item_url": "http://example.com/item/123"
            })
            
            data = json.loads(result.content[0].text)
            assert data["success"] == True
            assert data["conversation_id"] == "conv_123"

    @pytest.mark.asyncio
    async def test_xianyu_send_message(self):
        """测试发送消息工具"""
        with patch("mcp_server.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.send_message.return_value = True
            mock_get_client.return_value = mock_client
            
            result = await call_tool("xianyu_send_message", {
                "conversation_id": "conv_123",
                "content": "hello"
            })
            
            data = json.loads(result.content[0].text)
            assert data["success"] == True

    @pytest.mark.asyncio
    async def test_unknown_tool_error(self):
        """测试未知工具返回错误"""
        result = await call_tool("unknown_tool", {})
        
        assert result.isError == True
        assert "未知工具" in result.content[0].text
