import pytest

from src.core import CopiedItem, _ItemCopierImpl


class _FakeLocator:
    def __init__(self, count=0, visible=False):
        self._count = count
        self._visible = visible

    @property
    def first(self):
        return self

    async def count(self):
        return self._count

    async def is_visible(self, timeout=None):
        return self._visible


class _FakePage:
    def __init__(self, selectors):
        self._selectors = selectors

    def locator(self, selector):
        return self._selectors.get(selector, _FakeLocator())


class _FakeChromeManager:
    async def navigate(self, *_args, **_kwargs):
        return True


@pytest.mark.asyncio
async def test_publish_from_item_reports_login_required_when_publish_page_is_blocked(
    monkeypatch,
):
    page = _FakePage(
        {
            'input[type="file"]': _FakeLocator(count=0),
            "text=立即登录": _FakeLocator(visible=True),
            "text=登录后可以更懂你": _FakeLocator(visible=True),
        }
    )
    copier = _ItemCopierImpl(_FakeChromeManager(), page)

    async def fake_capture(_item_url):
        return CopiedItem(
            item_id="1",
            title="title",
            description="desc",
            category="",
            category_id=0,
            brand="",
            model="",
            min_price=10,
            max_price=10,
            image_urls=["https://example.com/a.jpg"],
            seller_city="",
            is_free_ship=False,
            raw_data={},
        )

    async def fail_upload(*_args, **_kwargs):
        raise AssertionError("不应在登录拦截页尝试上传")

    monkeypatch.setattr(copier, "capture_item_detail", fake_capture)
    monkeypatch.setattr(copier, "_upload_image", fail_upload)

    result = await copier.publish_from_item("https://www.goofish.com/item?id=1")

    assert result["success"] is False
    assert result["error"] == "发布页需要重新登录"
