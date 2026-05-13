import asyncio
import json

import pytest
from unittest.mock import AsyncMock

from src.api.hook_notifier import HookNotifier
from src.api.websocket_client import WebSocketClient
from src.settings import HookSettings


class FakeHttpClient:
    cookies = {"unb": "4188939592"}
    device_id = "web_4188939592"


@pytest.mark.asyncio
async def test_create_conversation_sends_single_chat_create_rpc():
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


class RecordingNotifier:
    def __init__(self):
        self.calls = []

    def is_event_enabled(self, event_name: str) -> bool:
        return event_name == "message.received"

    async def notify(self, *, event_name: str, user_id: str, event: dict):
        self.calls.append({
            "event_name": event_name,
            "user_id": user_id,
            "event": event,
        })


def test_hook_notifier_skips_when_url_template_missing():
    notifier = HookNotifier(HookSettings(url_template="", timeout_seconds=5, enabled_events=("message.received",)))

    assert notifier.is_enabled() is False
    assert notifier.is_event_enabled("message.received") is False


@pytest.mark.asyncio
async def test_handle_raw_message_dispatches_message_received_hook():
    notifier = RecordingNotifier()
    client = WebSocketClient(FakeHttpClient(), user_id="user-001", hook_notifier=notifier)
    client._my_id = "self-user"
    client._update_cache_from_event = AsyncMock()

    payload = {
        "lwp": "/sync",
        "headers": {"mid": "server-mid"},
        "body": {
            "syncPushPackage": {
                "data": [
                    {
                        "data": json.dumps({
                            "1": {
                                "2": "conv-001@goofish",
                                "5": 1715566830123,
                                "6": {"contentType": 1, "text": {"text": "你好"}},
                                "10": {
                                    "senderUserId": "seller-001",
                                    "reminderTitle": "卖家A",
                                },
                            }
                        }, ensure_ascii=False)
                    }
                ]
            }
        },
    }

    await client._handle_raw_message(json.dumps(payload, ensure_ascii=False))
    await asyncio.sleep(0)

    assert len(notifier.calls) == 1
    hook_call = notifier.calls[0]
    assert hook_call["event_name"] == "message.received"
    assert hook_call["user_id"] == "user-001"
    assert hook_call["event"]["cid"] == "conv-001"
    assert hook_call["event"]["sender_id"] == "seller-001"


@pytest.mark.asyncio
async def test_handle_raw_message_skips_hook_for_self_sent_message():
    notifier = RecordingNotifier()
    client = WebSocketClient(FakeHttpClient(), user_id="user-001", hook_notifier=notifier)
    client._my_id = "self-user"
    client._update_cache_from_event = AsyncMock()

    payload = {
        "lwp": "/sync",
        "headers": {"mid": "server-mid"},
        "body": {
            "syncPushPackage": {
                "data": [
                    {
                        "data": json.dumps({
                            "1": {
                                "2": "conv-001@goofish",
                                "5": 1715566830123,
                                "6": {"contentType": 1, "text": {"text": "回显消息"}},
                                "10": {
                                    "senderUserId": "self-user",
                                    "reminderTitle": "自己",
                                },
                            }
                        }, ensure_ascii=False)
                    }
                ]
            }
        },
    }

    await client._handle_raw_message(json.dumps(payload, ensure_ascii=False))
    await asyncio.sleep(0)

    assert notifier.calls == []


@pytest.mark.asyncio
async def test_handle_raw_message_hook_failure_does_not_break_handlers():
    class FailingNotifier:
        def is_event_enabled(self, event_name: str) -> bool:
            return True

        async def notify(self, *, event_name: str, user_id: str, event: dict):
            raise RuntimeError("hook failed")

    seen = []
    client = WebSocketClient(FakeHttpClient(), user_id="user-001", hook_notifier=FailingNotifier())
    client._my_id = "self-user"
    client._update_cache_from_event = AsyncMock()
    client.on_message(lambda event: seen.append(event["cid"]))

    payload = {
        "lwp": "/sync",
        "headers": {"mid": "server-mid"},
        "body": {
            "syncPushPackage": {
                "data": [
                    {
                        "data": json.dumps({
                            "1": {
                                "2": "conv-err@goofish",
                                "5": 1715566830123,
                                "6": {"contentType": 1, "text": {"text": "你好"}},
                                "10": {
                                    "senderUserId": "seller-001",
                                    "reminderTitle": "卖家A",
                                },
                            }
                        }, ensure_ascii=False)
                    }
                ]
            }
        },
    }

    await client._handle_raw_message(json.dumps(payload, ensure_ascii=False))
    await asyncio.sleep(0)

    assert seen == ["conv-err"]
