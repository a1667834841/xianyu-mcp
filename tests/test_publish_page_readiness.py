import pytest

from src.core import CopiedItem, CopiedSku, _ItemCopierImpl


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


class _EditableLocator(_FakeLocator):
    def __init__(self, visible=True):
        super().__init__(visible=visible)
        self.value = ""
        self.pressed = []

    async def fill(self, value):
        self.value = value

    async def press(self, key):
        self.pressed.append(key)


def test_parse_item_data_extracts_sku_prices_and_uses_them_as_price_fallback():
    copier = _ItemCopierImpl(_FakeChromeManager(), None)
    copier.captured_data = {
        "data": {
            "itemDO": {
                "itemId": "sku-item",
                "title": "多规格手机壳",
                "desc": "多颜色多型号",
                "categoryId": 50025387,
                "imageInfos": [],
                "skuList": [
                    {
                        "skuId": 1,
                        "priceInCent": 600,
                        "quantity": 3,
                        "propertyList": [
                            {"propertyText": "颜色", "actualValueText": "黑色"},
                            {"propertyText": "适用型号", "valueText": "iPhone7/8/se"},
                        ],
                    },
                    {
                        "skuId": 2,
                        "price": 900,
                        "quantity": 5,
                        "propertyList": [
                            {"propertyText": "颜色", "actualValueText": "蓝色"},
                            {"propertyText": "适用型号", "valueText": "iPhone7p/8p"},
                        ],
                    },
                ],
            },
            "sellerDO": {"city": "深圳"},
        }
    }

    item = copier._parse_item_data()

    assert item is not None
    assert item.min_price == 6.0
    assert item.max_price == 9.0
    assert item.sku_list == [
        CopiedSku(
            sku_id="1",
            price=6.0,
            quantity=3,
            props=[
                {"name": "颜色", "value": "黑色"},
                {"name": "适用型号", "value": "iPhone7/8/se"},
            ],
            image_url=None,
        ),
        CopiedSku(
            sku_id="2",
            price=9.0,
            quantity=5,
            props=[
                {"name": "颜色", "value": "蓝色"},
                {"name": "适用型号", "value": "iPhone7p/8p"},
            ],
            image_url=None,
        ),
    ]


def test_build_publish_description_adds_clear_sku_prices_with_30_percent_markup():
    item = CopiedItem(
        item_id="1",
        title="Crybaby",
        description="原始描述",
        category="潮玩盲盒",
        category_id=125960001,
        brand="POP MART/泡泡玛特",
        model=None,
        min_price=75,
        max_price=500,
        image_urls=["https://example.com/a.jpg"],
        seller_city="宁波",
        is_free_ship=True,
        raw_data={},
        sku_list=[
            CopiedSku(
                sku_id="1",
                price=75,
                quantity=10,
                props=[{"name": "款式", "value": "盲盒"}],
                image_url=None,
            ),
            CopiedSku(
                sku_id="2",
                price=125,
                quantity=10,
                props=[{"name": "款式", "value": "隐藏款-美人鱼的眼泪"}],
                image_url=None,
            ),
        ],
    )

    description = _ItemCopierImpl.build_publish_description(item)

    assert description.startswith("原始描述")
    assert "【规格价格】" in description
    assert "1. 盲盒：97.50元" in description
    assert "2. 隐藏款-美人鱼的眼泪：162.50元" in description
    assert "以上价格已按原商品规格价上浮30%" in description


@pytest.mark.asyncio
async def test_fill_title_supports_contenteditable_title_field():
    title_editor = _EditableLocator()
    page = _FakePage(
        {
            'input[placeholder*="标题"]': _FakeLocator(visible=False),
            'textarea[placeholder*="标题"]': _FakeLocator(visible=False),
            '[contenteditable="true"][placeholder*="标题"]': title_editor,
        }
    )
    copier = _ItemCopierImpl(_FakeChromeManager(), page)

    result = await copier._fill_title("测试勿拍 参数验证键盘")

    assert result is True
    assert title_editor.value == "测试勿拍 参数验证键盘"
    assert title_editor.pressed == ["Tab"]


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
async def test_publish_from_item_prepends_title_when_title_field_is_unavailable(
    monkeypatch,
):
    page = _FakePage({'input[type="file"]': _FakeLocator(count=1)})
    copier = _ItemCopierImpl(_FakeChromeManager(), page)
    descriptions = []

    async def fake_capture(_item_url):
        return CopiedItem(
            item_id="1",
            title="原始标题",
            description="原始描述",
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

    async def fake_fill_title(_title):
        return False

    async def fake_fill_description(description):
        descriptions.append(description)
        return True

    async def fake_fill_price(_price, _original_price):
        return True

    async def fake_select_condition(_condition):
        return True

    async def fake_try_publish():
        return True

    monkeypatch.setattr(copier, "capture_item_detail", fake_capture)
    monkeypatch.setattr(copier, "_upload_image", fake_upload)
    monkeypatch.setattr(copier, "_fill_title", fake_fill_title, raising=False)
    monkeypatch.setattr(copier, "_fill_description", fake_fill_description)
    monkeypatch.setattr(copier, "_fill_price", fake_fill_price)
    monkeypatch.setattr(copier, "_select_condition", fake_select_condition)
    monkeypatch.setattr(copier, "_try_publish_or_save_draft", fake_try_publish)

    await copier.publish_from_item(
        "https://www.goofish.com/item?id=1",
        new_title="测试勿拍 标题参数验证",
        new_description="自定义描述正文",
    )

    assert descriptions[0].startswith("测试勿拍 标题参数验证\n\n自定义描述正文")


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
