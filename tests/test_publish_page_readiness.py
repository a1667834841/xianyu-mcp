import pytest

from src.core import CopiedItem, _ItemCopierImpl


class _FakeLocator:
    def __init__(self, count=0, visible=False):
        self._count = count
        self._visible = visible
        self.clicked = False

    @property
    def first(self):
        return self

    async def count(self):
        return self._count

    async def is_visible(self, timeout=None):
        return self._visible

    async def is_enabled(self):
        return self._visible

    async def click(self):
        self.clicked = True


class _FakePage:
    def __init__(self, selectors, url="https://www.goofish.com/publish"):
        self._selectors = selectors
        self.screenshots = []
        self.url = url

    def locator(self, selector):
        return self._selectors.get(selector, _FakeLocator())

    async def screenshot(self, path, full_page):
        self.screenshots.append((path, full_page))


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


@pytest.mark.asyncio
async def test_publish_from_item_fills_title_and_returns_final_title(monkeypatch):
    page = _FakePage({'input[type="file"]': _FakeLocator(count=1)})
    copier = _ItemCopierImpl(_FakeChromeManager(), page)
    calls = []

    async def fake_capture(_item_url):
        return CopiedItem(
            item_id="1",
            title="全新库存 狼蛛F3087有线87键真机械键盘 多彩灯光 全键",
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

    async def fake_upload(*_args, **_kwargs):
        return True

    async def fake_fill_title(title):
        calls.append(("title", title))
        return True

    async def fake_fill_description(_description):
        return True

    async def fake_fill_price(_price, _original_price):
        return True

    async def fake_select_condition(_condition):
        return True

    async def fake_try_publish():
        return True

    async def fake_get_title():
        return "全新库存 狼蛛F3087有线87键真机械键盘 多彩灯光 全键"

    monkeypatch.setattr(copier, "capture_item_detail", fake_capture)
    monkeypatch.setattr(copier, "_upload_image", fake_upload)
    monkeypatch.setattr(copier, "_fill_title", fake_fill_title, raising=False)
    monkeypatch.setattr(copier, "_fill_description", fake_fill_description)
    monkeypatch.setattr(copier, "_fill_price", fake_fill_price)
    monkeypatch.setattr(copier, "_select_condition", fake_select_condition)
    monkeypatch.setattr(copier, "_try_publish_or_save_draft", fake_try_publish)
    monkeypatch.setattr(copier, "_get_current_title", fake_get_title, raising=False)

    result = await copier.publish_from_item("https://www.goofish.com/item?id=1")

    assert ("title", "全新库存 狼蛛F3087有线87键真机械键盘 多彩灯光 全键") in calls
    assert result["final_title"] == "全新库存 狼蛛F3087有线87键真机械键盘 多彩灯光 全键"


@pytest.mark.asyncio
async def test_try_publish_clicks_publish_button_when_available():
    publish_button = _FakeLocator(visible=True)
    page = _FakePage(
        {
            "text=点击展示二维码": _FakeLocator(visible=False),
            'button[class*="publish-button"]': publish_button,
        }
    )
    copier = _ItemCopierImpl(_FakeChromeManager(), page)

    result = await copier._try_publish_or_save_draft()

    assert result is True
    assert publish_button.clicked is True


@pytest.mark.asyncio
async def test_capture_publish_outcome_extracts_item_id_from_detail_url(monkeypatch):
    page = _FakePage({}, url="https://www.goofish.com/item?id=987654321")
    copier = _ItemCopierImpl(_FakeChromeManager(), page)

    async def fake_get_current_title():
        return None

    monkeypatch.setattr(copier, "_get_current_title", fake_get_current_title)

    result = await copier._capture_publish_outcome(
        expected_title="全新库存 狼蛛F3087有线87键真机械键盘 多彩灯光 全键",
        timeout_seconds=0.01,
        poll_interval=0,
    )

    assert result["publish_state"] == "published"
    assert result["item_id"] == "987654321"
    assert result["final_title"] == "全新库存 狼蛛F3087有线87键真机械键盘 多彩灯光 全键"
