import json
import sys
import importlib.util

spec = importlib.util.spec_from_file_location(
    "http_server", "mcp_server/http_server.py"
)
http_server = importlib.util.module_from_spec(spec)
sys.modules["http_server"] = http_server
spec.loader.exec_module(http_server)


class FakeManager:
    def create_user(self, display_name=None):
        return type(
            "Entry",
            (),
            {
                "user_id": "user-001",
                "slot_id": "slot-1",
                "cdp_port": 9222,
                "status": "pending_login",
            },
        )()

    def list_user_statuses(self):
        return [{"user_id": "user-001", "status": "ready"}]

    def get_user_status(self, user_id):
        return {"user_id": user_id, "status": "ready"}

    async def search(self, keyword, user_id=None, **options):
        return {"success": True, "user_id": user_id or "user-001", "items": []}

    async def publish(self, user_id, item_url, **options):
        return {"success": True, "user_id": user_id, "item_id": "123"}


async def test_xianyu_publish_requires_user_id(monkeypatch):
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeManager())

    payload = json.loads(
        await http_server.xianyu_publish(
            user_id="user-001", item_url="https://www.goofish.com/item?id=1"
        )
    )

    assert payload["success"] is True
    assert payload["user_id"] == "user-001"
