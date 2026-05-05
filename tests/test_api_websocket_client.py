import pytest
from unittest.mock import AsyncMock

from src.api.websocket_client import WebSocketClient


@pytest.mark.asyncio
async def test_create_conversation_sends_single_chat_create_rpc():
    class FakeHttpClient:
        cookies = {"unb": "4188939592"}
        device_id = "web_4188939592"

    client = WebSocketClient(FakeHttpClient())
    client._running = True
    client.ws = object()
    client.send_rpc = AsyncMock(return_value={"success": True, "body": [{"cid": "60971615689@goofish"}]})

    result = await client.create_conversation(seller_id="2201414115913", item_id="1027628395193")

    assert result == {"success": True, "conversation_id": "60971615689"}
    client.send_rpc.assert_awaited_once_with(
        "/r/SingleChatConversation/create",
        [
            {
                "pairFirst": "4188939592@goofish",
                "pairSecond": "2201414115913@goofish",
                "bizType": "1",
                "extension": {"itemId": "1027628395193", "orderId": "", "source": ""},
                "ctx": {"appVersion": "1.0", "platform": "web"},
            }
        ],
    )


@pytest.mark.asyncio
async def test_create_conversation_reads_cid_from_single_chat_conversation_body():
    class FakeHttpClient:
        cookies = {"unb": "4188939592"}
        device_id = "web_4188939592"

    client = WebSocketClient(FakeHttpClient())
    client._running = True
    client.ws = object()
    client.send_rpc = AsyncMock(
        return_value={
            "success": True,
            "body": {
                "singleChatConversation": {
                    "cid": "61324594446@goofish"
                }
            },
        }
    )

    result = await client.create_conversation(seller_id="2201414115913", item_id="1042685373726")

    assert result == {"success": True, "conversation_id": "61324594446"}
