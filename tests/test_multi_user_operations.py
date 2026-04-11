import pytest


@pytest.mark.asyncio
async def test_search_without_user_id_uses_ready_user(tmp_path):
    from dataclasses import replace
    from tests.test_multi_user_manager import make_manager

    manager = make_manager(tmp_path)
    entry = manager.create_user()
    manager.registry.update_user(replace(entry, status="ready"))

    class FakeApp:
        async def search_with_meta(self, keyword, **options):
            return type(
                "Outcome",
                (),
                {
                    "items": [],
                    "requested_rows": 10,
                    "returned_rows": 0,
                    "stop_reason": "target_reached",
                    "stale_pages": 0,
                    "engine_used": "http_api",
                    "fallback_reason": None,
                    "pages_fetched": 1,
                },
            )()

    manager._runtimes[entry.user_id] = type(
        "Runtime", (), {"entry": entry, "app": FakeApp()}
    )()

    result = await manager.search(keyword="键盘", rows=10)

    assert result["success"] is True
    assert result["user_id"] == entry.user_id


@pytest.mark.asyncio
async def test_publish_requires_explicit_user_id(tmp_path):
    from tests.test_multi_user_manager import make_manager

    manager = make_manager(tmp_path)

    with pytest.raises(TypeError):
        await manager.publish(item_url="https://www.goofish.com/item?id=1")
