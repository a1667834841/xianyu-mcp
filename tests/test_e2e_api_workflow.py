import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.api.client import XianyuApiClient


class TestEndToEndWorkflow:
    @pytest.mark.asyncio
    async def test_login_search_publish_workflow(self):
        """测试登录 -> 搜索 -> 发布完整工作流"""
        client = XianyuApiClient()
        
        # 1. 登录
        with patch.object(client.http_client, "login", new_callable=AsyncMock) as mock_login:
            mock_login.return_value = {
                "success": True,
                "logged_in": False,
                "qr_code_url": "https://example.com/qr"
            }
            
            login_result = await client.login(timeout=300)
            assert login_result["success"] == True

        # 2. 检查会话
        with patch.object(client.http_client, "check_session", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = {"valid": True}
            
            check_result = await client.check_session()
            assert check_result["valid"] == True

        # 3. 搜索商品
        with patch.object(client.http_client, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [
                {"item_id": "123", "title": "iPhone", "price": "¥5000"}
            ]
            
            search_result = await client.search(keyword="iPhone", rows=10)
            assert len(search_result) == 1

        # 4. 获取商品详情
        with patch.object(client.http_client, "get_item_detail", new_callable=AsyncMock) as mock_detail:
            mock_detail.return_value = {
                "item_id": "123",
                "title": "iPhone",
                "price": 5000.0,
            }
            
            detail_result = await client.get_detail(item_url="http://example.com/item?id=123")
            assert detail_result["item_id"] == "123"

        # 5. 发布商品（API 成功）
        with patch.object(client.http_client, "publish", new_callable=AsyncMock) as mock_publish:
            mock_publish.return_value = {
                "success": True,
                "item_id": "item_456",
                "method": "http",
            }
            
            publish_result = await client.publish(item_url="http://example.com/item?id=123")
            assert publish_result["success"] == True
            assert publish_result["method"] == "http"

    @pytest.mark.asyncio
    async def test_conversation_workflow(self):
        """测试对话完整工作流"""
        client = XianyuApiClient()
        
        # 1. 创建对话
        with patch.object(client.http_client, "create_conversation", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "conv_123"
            
            create_result = await client.create_conversation(
                item_url="http://example.com/item/123",
                seller_id="user_456"
            )
            assert create_result == "conv_123"

        # 2. 获取对话列表
        with patch.object(client.http_client, "list_conversations", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []
            
            list_result = await client.list_conversations(limit=20)
            assert isinstance(list_result, list)

        # 3. 获取消息历史
        with patch.object(client.http_client, "get_message_history", new_callable=AsyncMock) as mock_history:
            mock_history.return_value = {
                "messages": [],
                "has_more": False
            }
            
            history_result = await client.get_messages(conversation_id="conv_123", limit=50)
            assert "messages" in history_result
            assert "has_more" in history_result

        # 4. 发送消息
        with patch.object(client.websocket_pool, "send_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            
            send_result = await client.send_message(
                conversation_id="conv_123",
                content="hello"
            )
            assert send_result == True

    @pytest.mark.asyncio
    async def test_refresh_token_returns_http_failure_when_api_fails(self):
        client = XianyuApiClient()

        with patch.object(client.http_client, "refresh_token", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = Exception("API failed")

            result = await client.refresh_token()

        assert result == {"success": False, "method": "http", "message": "API failed"}
