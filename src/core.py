"""
core.py - 闲鱼核心业务模块
提供统一的闲鱼操作入口：搜索、发布、获取详情
"""

import asyncio
import json
import time
import base64
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
import logging

try:
    from .browser import AsyncChromeManager
    from .session import SessionManager
    from .settings import AppSettings, load_settings
    from .keepalive import CookieKeepaliveService
    from .http_search import HttpApiSearchClient
except ImportError:
    from browser import AsyncChromeManager
    from session import SessionManager
    from settings import AppSettings, load_settings
    from keepalive import CookieKeepaliveService
    from http_search import HttpApiSearchClient


logger = logging.getLogger(__name__)


# ==================== 数据类 ====================


@dataclass
class SearchItem:
    """搜索商品"""

    item_id: str
    title: str
    price: str
    original_price: str
    want_cnt: int
    seller_nick: str
    seller_city: str
    image_urls: List[str]
    detail_url: str
    is_free_ship: bool
    publish_time: Optional[str] = None
    exposure_score: float = 0.0  # 曝光度分数


@dataclass
class SearchParams:
    """搜索参数"""

    keyword: str
    rows: int = 30
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    free_ship: bool = False
    sort_field: str = ""
    sort_order: str = ""


@dataclass
class CopiedItem:
    """复制的商品数据"""

    item_id: str
    title: str
    description: str
    category: str
    category_id: int
    brand: Optional[str]
    model: Optional[str]
    min_price: float
    max_price: float
    image_urls: List[str]
    seller_city: str
    is_free_ship: bool
    raw_data: Dict[str, Any]


@dataclass
class SearchOutcome:
    items: List[SearchItem]
    requested_rows: int
    returned_rows: int
    stop_reason: str
    stale_pages: int
    engine_used: str = "browser_fallback"
    fallback_reason: Optional[str] = None
    pages_fetched: int = 0


# ==================== XianyuApp 主类 ====================


class XianyuApp:
    """闲鱼操作统一入口"""

    def __init__(
        self,
        browser: Optional[AsyncChromeManager] = None,
        settings: Optional[AppSettings] = None,
    ):
        """
        初始化 XianyuApp

        Args:
            browser: 浏览器管理器实例（可选）
        """
        resolved_settings = (
            settings or getattr(browser, "settings", None) or load_settings()
        )
        self.settings = resolved_settings

        self.browser = browser or AsyncChromeManager(settings=resolved_settings)
        # If the caller provided an already-constructed browser, align its settings for consistency.
        try:
            self.browser.settings = resolved_settings
        except Exception:
            pass

        self.session = SessionManager(self.browser, settings=resolved_settings)
        self._search_lock = asyncio.Lock()
        self._session_lock = asyncio.Lock()
        self._publish_lock = asyncio.Lock()
        self._work_lock = self._search_lock
        keepalive = CookieKeepaliveService(
            browser=self.browser,
            session=self.session,
            interval_minutes=resolved_settings.keepalive.interval_minutes,
        )
        # Public name used by tests and other modules.
        self.keepalive = keepalive
        # Backward-compatible alias (older drafts used keepalive_service).
        self.keepalive_service = keepalive
        self._background_started = False

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.browser.ensure_running()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.stop_background_tasks()
        await self.browser.close()

    def start_background_tasks(self) -> None:
        if self._background_started:
            return
        if not (
            getattr(self.settings, "keepalive", None)
            and self.settings.keepalive.enabled
        ):
            return

        # Avoid marking the tasks as started when no loop exists, so callers can retry later.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "start_background_tasks called without a running event loop; skipped."
            )
            return

        try:
            self.keepalive.start()
            self._background_started = True
        except Exception:
            logger.exception(
                "Failed to start keepalive service; continuing without it."
            )

    async def stop_background_tasks(self) -> None:
        if not self._background_started:
            return
        self._background_started = False

        try:
            await self.keepalive.stop()
        except Exception:
            logger.exception("Failed to stop keepalive service; continuing shutdown.")

    # ==================== 会话管理（委托给 session） ====================

    async def login(self, timeout: int = 15) -> Dict[str, Any]:
        """
        扫码登录获取 Token

        流程：
        1. 访问闲鱼首页
        2. 如果已登录，直接返回 token
        3. 如果未登录，获取并显示二维码（不等待扫码）

        Args:
            timeout: 等待二维码 API 超时时间（秒），默认 15 秒

        Returns:
            字典，包含：
            - success: bool
            - logged_in: bool (是否已登录)
            - token: str (可选，已登录时返回)
            - qr_code: Dict (可选，未登录时返回)
            - message: str
        """
        async with self._session_lock:
            return await self.session.login(timeout=timeout)

    async def show_qr_code(self) -> Optional[Dict[str, Any]]:
        """
        显示登录二维码（不等待扫码）

        访问闲鱼首页，如果未登录则显示二维码。用户扫码后浏览器会自动跳转完成登录。

        Returns:
            字典，包含：
            - success: bool
            - logged_in: bool (是否已登录)
            - qr_code: Dict (仅未登录时返回)
            - message: str
        """
        async with self._session_lock:
            return await self.session.show_qr_code()

    async def refresh_token(self) -> Optional[Dict[str, str]]:
        """刷新 Token"""
        async with self._session_lock:
            return await self.session.refresh_token()

    async def check_session(self) -> Dict[str, Any]:
        """检查 Cookie 是否有效，并返回最近更新时间。"""
        async with self._session_lock:
            is_valid = await self.session.check_cookie_valid()
            return self.session.get_cookie_status(is_valid)

    # ==================== 搜索功能 ====================

    async def search(self, keyword: str, **options) -> List[SearchItem]:
        outcome = await self.search_with_meta(keyword, **options)
        return outcome.items

    async def search_with_meta(self, keyword: str, **options) -> SearchOutcome:
        """
        搜索商品（使用 HTTP API）

        Args:
            keyword: 搜索关键词
            **options: 搜索选项 (rows, min_price, max_price, free_ship, sort_field, sort_order)

        Returns:
            搜索结果
        """
        params = SearchParams(
            keyword=keyword,
            rows=options.get("rows", 30),
            min_price=options.get("min_price"),
            max_price=options.get("max_price"),
            free_ship=options.get("free_ship", False),
            sort_field=options.get("sort_field", ""),
            sort_order=options.get("sort_order", ""),
        )

        print(
            f"[Search] 开始 HTTP 搜索 keyword={params.keyword!r} rows={params.rows}",
            flush=True,
        )

        async def get_cookie():
            cached = self.session.load_cached_cookie()
            if cached:
                return cached
            if await self.browser.ensure_running():
                full_cookie = await self.browser.get_full_cookie_string()
                if full_cookie:
                    self.session.save_cookie(full_cookie)
                    return full_cookie
            return None

        client = HttpApiSearchClient(get_cookie)

        try:
            from .search_api import StableSearchRunner
        except ImportError:
            from search_api import StableSearchRunner

        try:
            runner = StableSearchRunner(
                client=client,
                max_stale_pages=self.settings.search.max_stale_pages,
            )
            outcome = await runner.search(params)

            print(
                f"[Search] HTTP 搜索结束 engine={outcome.engine_used} "
                f"returned={outcome.returned_rows} stop_reason={outcome.stop_reason} "
                f"pages_fetched={outcome.pages_fetched}",
                flush=True,
            )

            return outcome

        finally:
            await client.aclose()

    # ==================== 发布功能 ====================

    async def publish(self, item_url: str, **options) -> Dict[str, Any]:
        """
        根据对标商品发布新商品

        Args:
            item_url: 对标商品链接
            **options: 选项 (new_title, new_description, new_price, original_price, condition)

        Returns:
            发布结果字典
        """
        async with self._publish_lock:
            page = await self.browser.get_publish_page()
            copier = _ItemCopierImpl(self.browser, page)
            return await copier.publish_from_item(
                item_url,
                new_title=options.get("new_title"),
                new_description=options.get("new_description"),
                new_price=options.get("new_price"),
                original_price=options.get("original_price"),
                condition=options.get("condition", "全新"),
            )

    async def get_detail(self, item_url: str) -> Optional[CopiedItem]:
        """
        获取商品详情数据

        Args:
            item_url: 商品链接

        Returns:
            CopiedItem 对象，失败返回 None
        """
        async with self._publish_lock:
            page = await self.browser.get_publish_page()
            copier = _ItemCopierImpl(self.browser, page)
            return await copier.capture_item_detail(item_url)

# ==================== 发布实现（从 item_copier.py 迁移） ====================


class _ItemCopierImpl:
    """商品复制发布器（内部实现）"""

    def __init__(self, chrome_manager: AsyncChromeManager, publish_page):
        self.chrome_manager = chrome_manager
        self.page = publish_page
        self.captured_data: Dict[str, Any] = {}

    async def capture_item_detail(
        self, item_url: str, timeout: int = 15
    ) -> Optional[CopiedItem]:
        """打开商品链接并捕获详情 API 数据"""
        self.captured_data = {}

        if not await self.chrome_manager.ensure_running():
            print("[ItemCopier] 浏览器启动失败")
            return None

        page = self.page
        if not page:
            return None

        capture_event = asyncio.Event()

        async def process_response(response):
            try:
                url = response.url
                if "mtop.taobao.idle.pc.detail" in url:
                    data = await response.json()
                    self.captured_data = data
                    capture_event.set()
                    print(f"[ItemCopier] 已捕获详情 API 响应")
            except Exception as e:
                print(f"[ItemCopier] 解析响应失败：{e}")

        def on_response(response):
            asyncio.create_task(process_response(response))

        page.on("response", on_response)

        print(f"[ItemCopier] 打开商品链接：{item_url}")
        await self.chrome_manager.navigate(item_url, page=page)

        try:
            print(f"[ItemCopier] 等待 API 响应...")
            await asyncio.wait_for(capture_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            print(f"[ItemCopier] 等待 API 响应超时")
            return None

        return self._parse_item_data()

    def _parse_item_data(self) -> Optional[CopiedItem]:
        """解析捕获的商品数据"""
        if not self.captured_data:
            return None

        data_container = self.captured_data.get("data", {})
        item_do = data_container.get("itemDO", {})

        if not item_do:
            item_do = data_container
            if not item_do:
                result = self.captured_data.get("result", {})
                item_do = result.get("itemDO", result)

        seller_do = data_container.get("sellerDO", {})

        if not item_do:
            print("[ItemCopier] 未找到商品数据")
            return None

        item_id = str(item_do.get("itemId", ""))
        title = item_do.get("title", "")
        description = item_do.get("desc", "")

        category = None
        category_id = item_do.get("categoryId")

        item_labels = item_do.get("itemLabelExtList", [])
        for label in item_labels:
            if label.get("propertyText") == "分类":
                category = label.get("text")
                break

        brand = None
        model = None
        cpv_labels = item_do.get("cpvLabels", [])
        for label in cpv_labels:
            prop_name = label.get("propertyName", "")
            value_name = label.get("valueName", "")
            if prop_name == "品牌":
                brand = value_name
            elif prop_name == "型号":
                model = value_name

        if not brand:
            for label in item_labels:
                if label.get("propertyText") == "品牌":
                    brand = label.get("text")
                    break

        min_price = float(item_do.get("minPrice", 0))
        max_price = float(item_do.get("maxPrice", min_price))

        image_infos = item_do.get("imageInfos", [])
        image_urls = [img.get("url", "") for img in image_infos if img.get("url")]

        is_free_ship = False
        common_tags = item_do.get("commonTags", [])
        for tag in common_tags:
            if tag.get("text") == "包邮":
                is_free_ship = True
                break

        seller_city = seller_do.get("publishCity", seller_do.get("city", ""))

        return CopiedItem(
            item_id=item_id,
            title=title,
            description=description,
            category=category or "",
            category_id=category_id or 0,
            brand=brand,
            model=model,
            min_price=min_price,
            max_price=max_price,
            image_urls=image_urls,
            seller_city=seller_city,
            is_free_ship=is_free_ship,
            raw_data=self.captured_data,
        )

    async def publish_from_item(
        self,
        item_url: str,
        new_title: Optional[str] = None,
        new_description: Optional[str] = None,
        new_price: Optional[float] = None,
        original_price: Optional[float] = None,
        condition: str = "全新",
    ) -> Dict[str, Any]:
        """根据对标商品发布新商品"""
        result = {"success": False, "item_id": None, "error": None, "item_data": None}

        print("[ItemCopier] 步骤 1: 获取对标商品数据...")
        item_data = await self.capture_item_detail(item_url)

        if not item_data:
            result["error"] = "获取商品数据失败"
            return result

        result["item_data"] = asdict(item_data)
        print(f"[ItemCopier] 成功获取商品数据")

        print("[ItemCopier] 导航到发布页面...")
        await self.chrome_manager.navigate(
            "https://www.goofish.com/publish", page=self.page
        )
        await asyncio.sleep(2)

        print("[ItemCopier] 步骤 2: 上传主图...")
        if not item_data.image_urls:
            result["error"] = "商品没有图片"
            return result

        if not await self._upload_image(item_data.image_urls[0], is_main=True):
            result["error"] = "上传主图失败"
            return result

        await asyncio.sleep(1.5)

        print("[ItemCopier] 步骤 3: 上传详情图...")
        for i, img_url in enumerate(item_data.image_urls[1:9]):
            if await self._upload_image(img_url, is_main=False):
                await asyncio.sleep(1)

        print("[ItemCopier] 步骤 4: 等待 AI 生成内容...")
        await asyncio.sleep(3)

        print("[ItemCopier] 步骤 5: 填充描述...")
        desc_to_use = new_description or item_data.description
        await self._fill_description(desc_to_use)
        await asyncio.sleep(0.5)

        print("[ItemCopier] 步骤 6: 填充价格...")
        price_to_use = new_price or item_data.min_price
        if original_price is None:
            original_price = price_to_use * 1.5
        await self._fill_price(price_to_use, original_price)
        await asyncio.sleep(0.5)

        if item_data.category:
            print("[ItemCopier] 步骤 7: 选择分类...")
            await self._select_category(item_data.category)
            await asyncio.sleep(0.5)

        if item_data.brand:
            print(f"[ItemCopier] 步骤 8: 选择品牌...")
            await self._fill_brand(item_data.brand)
            await asyncio.sleep(0.5)

        if item_data.model:
            print(f"[ItemCopier] 步骤 8.1: 填写型号...")
            await self._fill_model(item_data.model)
            await asyncio.sleep(0.5)

        print(f"[ItemCopier] 步骤 9: 选择成色...")
        await self._select_condition(condition)
        await asyncio.sleep(0.5)

        if item_data.is_free_ship:
            print("[ItemCopier] 步骤 10: 设置包邮...")
            await self._set_free_ship()
            await asyncio.sleep(0.5)

        print("[ItemCopier] 步骤 11: 尝试发布或保存草稿...")
        await self._try_publish_or_save_draft()
        await asyncio.sleep(1)

        page = self.page
        if page:
            await page.screenshot(
                path="/tmp/xianyu_publish_preview.png", full_page=True
            )
            print("[ItemCopier] 已保存发布预览截图")

        result["success"] = True
        print("[ItemCopier] 表单填充完成")

        return result

    async def _upload_image(self, image_url: str, is_main: bool = True) -> bool:
        """上传图片"""
        try:
            page = self.page
            if not page:
                return False

            if image_url.startswith("http://"):
                image_url = image_url.replace("http://", "https://")

            response = await page.request.get(image_url)
            if response.status != 200:
                return False

            image_buffer = await response.body()
            image_base64 = base64.b64encode(image_buffer).decode("utf-8")

            if is_main:
                try:
                    upload_wrapper = page.locator(".ant-upload-wrapper").first
                    await upload_wrapper.wait_for(state="visible", timeout=5000)
                except:
                    await asyncio.sleep(2)
            else:
                try:
                    upload_wrappers = page.locator(".ant-upload-wrapper")
                    count = await upload_wrappers.count()
                    if count > 0:
                        pass
                except:
                    pass

            await asyncio.sleep(0.3)

            result = await page.evaluate(
                """
                async ({ imageBufferBase64, fileName, isMain }) => {
                    try {
                        const byteCharacters = atob(imageBufferBase64);
                        const byteNumbers = new Array(byteCharacters.length);
                        for (let i = 0; i < byteCharacters.length; i++) {
                            byteNumbers[i] = byteCharacters.charCodeAt(i);
                        }
                        const byteArray = new Uint8Array(byteNumbers);
                        const blob = new Blob([byteArray], { type: 'image/jpeg' });
                        const file = new File([blob], fileName, { type: 'image/jpeg' });

                        const allUploadWrappers = document.querySelectorAll('.ant-upload-wrapper');
                        if (allUploadWrappers.length === 0) {
                            return { success: false, error: '未找到上传区域' };
                        }

                        const targetWrapper = isMain
                            ? allUploadWrappers[0]
                            : allUploadWrappers[allUploadWrappers.length - 1];

                        const fileInput = targetWrapper.querySelector('input[type="file"]');
                        if (!fileInput) {
                            return { success: false, error: '未找到文件输入框' };
                        }

                        const dataTransfer = new DataTransfer();
                        dataTransfer.items.add(file);
                        fileInput.files = dataTransfer.files;

                        const changeEvent = new Event('change', { bubbles: true });
                        fileInput.dispatchEvent(changeEvent);

                        return { success: true };
                    } catch (error) {
                        return { success: false, error: error.message };
                    }
                }
                """,
                {
                    "imageBufferBase64": image_base64,
                    "fileName": f"upload_{is_main}.jpg",
                    "isMain": is_main,
                },
            )

            await asyncio.sleep(1.5)

            if result.get("success"):
                print(f"[ItemCopier] {'主图' if is_main else '详情图'}上传成功")
                return True
            else:
                return False

        except Exception as e:
            print(f"[ItemCopier] 上传失败：{e}")
            return False

    async def _fill_description(self, description: str) -> bool:
        """填充描述"""
        try:
            page = self.page
            if not page:
                return False

            editor = page.locator('[contenteditable="true"]').first
            if await editor.is_visible():
                await editor.click()
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Delete")
                await editor.fill(description)
                await editor.press("Tab")
                return True
            return False
        except:
            return False

    async def _fill_price(self, price: float, original_price: float) -> bool:
        """填充价格"""
        try:
            page = self.page
            if not page:
                return False

            price_inputs = page.locator('input[type="text"][placeholder="0.00"]')
            count = await price_inputs.count()

            if count >= 2:
                await price_inputs.nth(0).fill(str(price))
                await price_inputs.nth(1).fill(str(original_price))
                await price_inputs.nth(0).press("Tab")
                return True
            return False
        except:
            return False

    async def _select_category(self, category: str) -> bool:
        """选择分类"""
        try:
            page = self.page
            if not page:
                return False

            category_selector = page.locator('[class*="category"]').first
            if await category_selector.is_visible(timeout=3000):
                await category_selector.click()
                await asyncio.sleep(0.5)

                category_option = page.locator(f"text={category}").first
                if await category_option.is_visible():
                    await category_option.click()
                    return True
            return False
        except:
            return False

    async def _fill_brand(self, brand: str) -> bool:
        """填写品牌"""
        try:
            page = self.page
            if not page:
                return False

            brand_input = page.locator('input[placeholder*="品牌"]').first
            if await brand_input.is_visible(timeout=3000):
                await brand_input.click()
                await asyncio.sleep(0.5)
                await page.keyboard.type(brand)
                await asyncio.sleep(0.5)
                await page.keyboard.press("Enter")
                return True
            return False
        except:
            return False

    async def _fill_model(self, model: str) -> bool:
        """填写型号"""
        try:
            page = self.page
            if not page:
                return False

            model_input = page.locator('input[placeholder*="型号"]').first
            if await model_input.is_visible(timeout=3000):
                await model_input.click()
                await model_input.fill(model)
                await model_input.press("Tab")
                return True
            return False
        except:
            return False

    async def _select_condition(self, condition: str) -> bool:
        """选择成色"""
        try:
            page = self.page
            if not page:
                return False

            condition_selector = page.locator(f'text="{condition}"').first
            if await condition_selector.is_visible(timeout=3000):
                await condition_selector.click()
                await asyncio.sleep(0.5)
                return True
            return False
        except:
            return False

    async def _set_free_ship(self) -> bool:
        """设置包邮"""
        try:
            page = self.page
            if not page:
                return False

            free_ship_option = page.locator("text=包邮").first
            if await free_ship_option.is_visible():
                await free_ship_option.click()
                return True
            return False
        except:
            return False

    async def _try_publish_or_save_draft(self) -> bool:
        """尝试发布或保存草稿"""
        try:
            page = self.page
            if not page:
                return False

            await asyncio.sleep(1)

            qr_link = page.locator("text=点击展示二维码").first
            if await qr_link.is_visible(timeout=3000):
                await qr_link.click()
                await asyncio.sleep(1)
                print("[ItemCopier] 已保存为草稿")
                return True

            publish_btn = page.locator('button[class*="publish-button"]').first
            if await publish_btn.is_visible() and await publish_btn.is_enabled():
                print("[ItemCopier] 发布按钮可点击")
                return True

            return False
        except:
            return False


# ==================== 便捷函数 ====================


async def search(keyword: str, **options) -> List[SearchItem]:
    """便捷函数：搜索商品"""
    async with XianyuApp() as app:
        return await app.search(keyword, **options)


async def publish(item_url: str, **options) -> Dict[str, Any]:
    """便捷函数：根据对标商品发布"""
    async with XianyuApp() as app:
        return await app.publish(item_url, **options)


async def get_detail(item_url: str) -> Optional[CopiedItem]:
    """便捷函数：获取商品详情"""
    async with XianyuApp() as app:
        return await app.get_detail(item_url)
