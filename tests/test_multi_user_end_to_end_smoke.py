import pytest


@pytest.mark.asyncio
async def test_search_payload_includes_user_and_slot(tmp_path):
    from tests.test_multi_user_manager import make_manager
    from dataclasses import replace

    manager = make_manager(tmp_path)
    entry = manager.create_user()
    entry = replace(entry, status="ready", enabled=True)
    manager.registry.update_user(entry)

    runtime = await manager._get_or_create_runtime(entry.user_id)

    class FakeOutcome:
        requested_rows = 5
        returned_rows = 0
        stop_reason = "target_reached"
        stale_pages = 0
        items = []
        engine_used = "http_api"
        fallback_reason = None
        pages_fetched = 1

    async def mock_search(**kwargs):
        return FakeOutcome()

    runtime.app.search_with_meta = mock_search

    payload = await manager.search(keyword="球鞋", rows=5)

    assert payload["user_id"] == entry.user_id
    assert payload["slot_id"] == entry.slot_id
