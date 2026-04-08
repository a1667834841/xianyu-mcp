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
except ImportError:
    from browser import AsyncChromeManager
    from session import SessionManager
    from settings import AppSettings, load_settings
    from keepalive import CookieKeepaliveService


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
        self._work_lock = asyncio.Lock()
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
        return await self.session.show_qr_code()

    async def refresh_token(self) -> Optional[Dict[str, str]]:
        """刷新 Token"""
        return await self.session.refresh_token()

    async def check_session(self) -> bool:
        """检查 Cookie 是否有效"""
        return await self.session.check_cookie_valid()

    # ==================== 搜索功能 ====================

    async def search(self, keyword: str, **options) -> List[SearchItem]:
        outcome = await self.search_with_meta(keyword, **options)
        return outcome.items

    async def search_with_meta(self, keyword: str, **options) -> SearchOutcome:
        """
        搜索商品

        Args:
            keyword: 搜索关键词
            **options: 搜索选项 (rows, min_price, max_price, free_ship, sort_field, sort_order)

        Returns:
            搜索结果列表
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

        async with self._work_lock:
            page = await self.browser.get_work_page()
            self.browser.page = page
            print(
                f"[Search] 开始搜索 keyword={params.keyword!r} rows={params.rows} current_url={getattr(page, 'url', '')!r}",
                flush=True,
            )

            try:
                from .search_api import PageApiSearchError
            except ImportError:
                from search_api import PageApiSearchError

            fallback_reason = None
            try:
                runner = _build_page_api_runner(
                    self.browser,
                    params,
                    self.settings.search.max_stale_pages,
                )
                outcome = await runner.search(params)
                print(
                    f"[Search] PageApi 结束 engine={outcome.engine_used} returned={outcome.returned_rows} stop_reason={outcome.stop_reason} stale_pages={outcome.stale_pages} pages_fetched={outcome.pages_fetched}",
                    flush=True,
                )
                if outcome.returned_rows == 0:
                    fallback_reason = "page_api_zero_items"
                else:
                    return outcome
            except PageApiSearchError as exc:
                fallback_reason = str(exc)

            searcher = _BrowserSearchImpl(
                self.browser,
                max_stale_pages=self.settings.search.max_stale_pages,
            )
            outcome = await searcher.search(params)
            outcome.fallback_reason = fallback_reason
            print(
                f"[Search] Fallback 结束 engine={outcome.engine_used} returned={outcome.returned_rows} stop_reason={outcome.stop_reason} stale_pages={outcome.stale_pages} pages_fetched={outcome.pages_fetched} fallback_reason={outcome.fallback_reason!r}",
                flush=True,
            )
            return outcome

    async def get_search_detail(self, item_ids: List[str]) -> Dict[str, Dict]:
        """
        获取商品详情（用于获取发布时间等详细信息）

        Args:
            item_ids: 商品 ID 列表

        Returns:
            字典，key 为 item_id，value 为详细信息
        """
        searcher = _BrowserSearchImpl(self.browser)
        return await searcher.get_item_details(item_ids)

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
        copier = _ItemCopierImpl(self.browser)
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
        copier = _ItemCopierImpl(self.browser)
        return await copier.capture_item_detail(item_url)


# ==================== 搜索实现（从 browser_search.py 迁移） ====================


def _build_page_api_runner(
    browser: AsyncChromeManager, params: SearchParams, max_stale_pages: int
):
    try:
        from .search_api import PageApiSearchClient, StableSearchRunner
    except ImportError:
        from search_api import PageApiSearchClient, StableSearchRunner
    page = browser.page

    async def ensure_page_ready():
        current_url = getattr(page, "url", "") or ""
        if "goofish.com" in current_url:
            return
        await browser.navigate("https://www.goofish.com", wait_until="domcontentloaded")

    client = PageApiSearchClient(page, ensure_page_ready=ensure_page_ready)
    return StableSearchRunner(client=client, max_stale_pages=max_stale_pages)


class _BrowserSearchImpl:
    """浏览器搜索管理器（内部实现）"""

    def __init__(self, chrome_manager: AsyncChromeManager, max_stale_pages: int = 3):
        self.chrome_manager = chrome_manager
        self.max_stale_pages = max_stale_pages
        self.search_results: List[Dict[str, Any]] = []

    def _finalize_items(
        self, items: List[SearchItem], requested_rows: int
    ) -> List[SearchItem]:
        items.sort(key=lambda x: x.exposure_score, reverse=True)
        return items[:requested_rows]

    async def search(self, params: SearchParams, timeout: int = 30) -> SearchOutcome:
        """执行搜索（带自动去重和 stale page 控制）"""
        self.search_results = []
        all_items: List[SearchItem] = []
        seen_item_ids: set = set()  # 用于去重的 item_id 集合
        stale_pages = 0

        if not await self.chrome_manager.ensure_running():
            raise RuntimeError("无法启动浏览器")

        try:
            await self.chrome_manager.navigate("about:blank")
            await asyncio.sleep(0.5)
            await self._setup_response_listener()
            await self._navigate_to_search(params.keyword)
            await asyncio.sleep(2)
            await self._apply_filters(params)

            page = 1
            while len(all_items) < params.rows:
                print(f"[BrowserSearch] 获取第 {page} 页数据...")

                if page == 1:
                    has_new_response = await self._wait_for_api_response(timeout)
                else:
                    prev_count = len(self._captured_responses)
                    await self._next_page(page)
                    has_new_response = await self._wait_for_new_api_response(
                        timeout, prev_count
                    )

                items = self._parse_results() if has_new_response else []

                # 去重：只添加未见过的商品
                new_count = 0
                for item in items:
                    if item.item_id not in seen_item_ids:
                        seen_item_ids.add(item.item_id)
                        all_items.append(item)
                        new_count += 1

                print(
                    f"[BrowserSearch] 第 {page} 页获取 {len(items)} 条，新增 {new_count} 条，累计 {len(all_items)} 条"
                )

                if len(all_items) >= params.rows:
                    result = self._finalize_items(all_items, params.rows)
                    print(
                        f"[BrowserSearch] 搜索完成：请求 {params.rows} 条，返回 {len(result)} 条"
                    )
                    return SearchOutcome(
                        items=result,
                        requested_rows=params.rows,
                        returned_rows=len(result),
                        stop_reason="target_reached",
                        stale_pages=stale_pages,
                        engine_used="browser_fallback",
                        fallback_reason=None,
                        pages_fetched=page,
                    )

                if new_count == 0:
                    stale_pages += 1
                else:
                    stale_pages = 0

                if stale_pages >= self.max_stale_pages:
                    result = self._finalize_items(all_items, params.rows)
                    print(f"[BrowserSearch] 搜索停止：连续无新增页达到 {stale_pages}")
                    return SearchOutcome(
                        items=result,
                        requested_rows=params.rows,
                        returned_rows=len(result),
                        stop_reason="stale_limit",
                        stale_pages=stale_pages,
                        engine_used="browser_fallback",
                        fallback_reason=None,
                        pages_fetched=page,
                    )

                page += 1

            result = self._finalize_items(all_items, params.rows)
            print(
                f"[BrowserSearch] 搜索完成：请求 {params.rows} 条，返回 {len(result)} 条"
            )
            return SearchOutcome(
                items=result,
                requested_rows=params.rows,
                returned_rows=len(result),
                stop_reason="target_reached",
                stale_pages=stale_pages,
                engine_used="browser_fallback",
                fallback_reason=None,
                pages_fetched=page,
            )

        except Exception as e:
            print(f"[BrowserSearch] 搜索失败：{e}")
            import traceback

            traceback.print_exc()
            return SearchOutcome(
                items=[],
                requested_rows=params.rows,
                returned_rows=0,
                stop_reason="error",
                stale_pages=stale_pages,
                engine_used="browser_fallback",
                fallback_reason=None,
                pages_fetched=page,
            )

    async def _next_page(self, page: int):
        """翻页（优化速度）"""
        page_obj = self.chrome_manager.page
        if not page_obj:
            return

        try:
            next_btn_selectors = [
                'button:has-text("下一页")',
                'a:has-text("下一页")',
                'li[title="下一页"]',
                ".pagination-next",
            ]

            for selector in next_btn_selectors:
                try:
                    next_btn = await page_obj.wait_for_selector(selector, timeout=1000)
                    if next_btn:
                        await next_btn.click()
                        await asyncio.sleep(1.5)
                        print(f"[BrowserSearch] 已翻到第 {page} 页")
                        return
                except:
                    continue

            try:
                page_btn = await page_obj.wait_for_selector(
                    f'li:has-text("{page}"), a:has-text("{page}")', timeout=1000
                )
                if page_btn:
                    await page_btn.click()
                    await asyncio.sleep(1.5)
                    print(f"[BrowserSearch] 已翻到第 {page} 页 (点击页码)")
                    return
            except:
                pass

            print(f"[BrowserSearch] 尝试滚动加载第 {page} 页...")
            await page_obj.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)
            await page_obj.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)

        except Exception as e:
            print(f"[BrowserSearch] 翻页失败：{e}")

    async def _navigate_to_home(self):
        """导航到闲鱼首页"""
        print("[BrowserSearch] 导航到闲鱼首页...")
        await self.chrome_manager.navigate(
            "https://www.goofish.com", wait_until="domcontentloaded"
        )

    async def _input_search_keyword(self, keyword: str):
        """输入搜索关键词"""
        page = self.chrome_manager.page
        if not page:
            return

        try:
            search_input = await page.wait_for_selector(
                "input.search-input--WY2l9QD3", timeout=5000
            )
            if search_input:
                print(f"[BrowserSearch] 输入关键词：{keyword}")
                await search_input.triple_click()
                await asyncio.sleep(0.3)
                await search_input.fill(keyword)
                await asyncio.sleep(0.5)

                search_btn = await page.wait_for_selector(
                    "button.search-icon--bewLHteU", timeout=5000
                )
                if search_btn:
                    await search_btn.click()
                    print("[BrowserSearch] 已点击搜索按钮")
            else:
                print("[BrowserSearch] 未找到搜索框，直接导航到搜索页")
                await self._navigate_to_search(keyword)

        except Exception as e:
            print(f"[BrowserSearch] 输入关键词失败：{e}")
            await self._navigate_to_search(keyword)

    async def _setup_response_listener(self):
        """设置响应监听器"""
        page = self.chrome_manager.page
        if not page:
            return

        response_event = asyncio.Event()
        self._captured_responses = []

        def on_response(response):
            url = response.url
            if "mtop.taobao.idlemtopsearch.pc.search" in url:
                print(f"[BrowserSearch] 监听到搜索 API 响应")

                async def get_response():
                    try:
                        data = await response.json()
                        if data and data.get("data"):
                            self._captured_responses.append(data)
                            response_event.set()
                            print(f"[BrowserSearch] 成功解析响应数据")
                    except Exception as e:
                        print(f"[BrowserSearch] 解析响应失败：{e}")

                asyncio.create_task(get_response())

        page.on("response", on_response)

        self._response_event = response_event

    async def _navigate_to_search(self, keyword: str):
        """通过首页搜索框导航到搜索页面"""
        page = self.chrome_manager.page
        if not page:
            return

        print("[BrowserSearch] 导航到闲鱼首页...")
        await self.chrome_manager.navigate(
            "https://www.goofish.com", wait_until="domcontentloaded"
        )
        await asyncio.sleep(2)

        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
        except:
            pass

        try:
            search_input = page.locator("input.search-input--WY2l9QD3").first
            if await search_input.is_visible(timeout=5000):
                print(f"[BrowserSearch] 输入关键词：{keyword}")
                await search_input.click()
                await asyncio.sleep(0.3)
                await page.keyboard.press("Control+a")
                await asyncio.sleep(0.1)
                await page.keyboard.type(keyword)
                await asyncio.sleep(0.5)
                await page.keyboard.press("Enter")
                print("[BrowserSearch] 已按回车搜索")
                await asyncio.sleep(3)
                return
        except Exception as e:
            print(f"[BrowserSearch] 搜索框交互失败：{e}")

        try:
            search_input = page.locator("input").filter(has_text="").first
            if await search_input.is_visible(timeout=3000):
                print(f"[BrowserSearch] 使用备用搜索框输入：{keyword}")
                await search_input.click()
                await asyncio.sleep(0.3)
                await page.keyboard.press("Control+a")
                await asyncio.sleep(0.1)
                await page.keyboard.type(keyword)
                await asyncio.sleep(0.5)
                await page.keyboard.press("Enter")
                print("[BrowserSearch] 已按回车搜索")
                await asyncio.sleep(3)
                return
        except Exception as e:
            print(f"[BrowserSearch] 备用搜索框失败：{e}")

    async def _apply_filters(self, params: SearchParams):
        """应用筛选条件"""
        page = self.chrome_manager.page
        if not page:
            return

        if params.min_price or params.max_price:
            try:
                await asyncio.sleep(1)
                filter_container = await page.wait_for_selector(
                    'div[id*="filter"], div[class*="filter"], div[class*="screen"]',
                    timeout=2000,
                )

                if filter_container:
                    inputs = await filter_container.query_selector_all(
                        'input[type="number"], input[type="text"]'
                    )
                    if inputs and len(inputs) >= 2:
                        if params.min_price:
                            await inputs[0].fill(str(params.min_price))
                        if params.max_price and len(inputs) > 1:
                            await inputs[1].fill(str(params.max_price))

                        confirm_btn = await filter_container.query_selector(
                            'button, a:has-text("确认")'
                        )
                        if confirm_btn:
                            await confirm_btn.click()
                            await asyncio.sleep(2)
                            print(
                                f"[BrowserSearch] 已应用价格筛选：{params.min_price}-{params.max_price}"
                            )

            except Exception as e:
                print(f"[BrowserSearch] 应用价格筛选失败：{e}")

        if params.free_ship:
            try:
                free_ship_selectors = [
                    'label:has-text("包邮")',
                    'span:has-text("包邮")',
                ]
                for selector in free_ship_selectors:
                    try:
                        element = await page.wait_for_selector(selector, timeout=1000)
                        if element:
                            await element.click()
                            await asyncio.sleep(2)
                            print("[BrowserSearch] 已应用包邮筛选")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"[BrowserSearch] 应用包邮筛选失败：{e}")

        if params.sort_field and params.sort_order:
            try:
                sort_text = "最新发布" if params.sort_field == "pub_time" else "价格"
                sort_element = await page.wait_for_selector(
                    f'div[role="button"]:has-text("{sort_text}")', timeout=2000
                )
                if sort_element:
                    await sort_element.click()
                    await asyncio.sleep(2)
                    print(f"[BrowserSearch] 已应用排序：{sort_text}")
            except Exception as e:
                print(f"[BrowserSearch] 应用排序失败：{e}")

    async def _wait_for_api_response(self, timeout: int = 30, clear: bool = False):
        """等待 API 响应"""
        if not hasattr(self, "_captured_responses"):
            print("[BrowserSearch] 响应监听器未设置")
            return False

        prev_count = 0
        if clear:
            self._captured_responses.clear()
        else:
            prev_count = len(self._captured_responses)
            if prev_count > 0:
                self.search_results = self._captured_responses
                print(
                    f"[BrowserSearch] 已有响应 count={prev_count}",
                    flush=True,
                )
                return True

        print(
            f"[BrowserSearch] 等待 API 响应（最多{timeout}秒）... 初始 count={prev_count}",
            flush=True,
        )
        start_time = time.time()
        while time.time() - start_time < timeout:
            if len(self._captured_responses) > prev_count:
                print(
                    f"[BrowserSearch] 捕获到 API 响应 count={len(self._captured_responses)}",
                    flush=True,
                )
                self.search_results = self._captured_responses
                return True
            await asyncio.sleep(0.5)

        print(
            f"[BrowserSearch] 等待响应超时 当前count={len(self._captured_responses)}",
            flush=True,
        )
        return False

    async def _wait_for_new_api_response(self, timeout: int = 30, prev_count: int = 0):
        """等待新的 API 响应"""
        if not hasattr(self, "_captured_responses"):
            print("[BrowserSearch] 响应监听器未设置")
            return False

        print(
            f"[BrowserSearch] 等待新页面的 API 响应... prev_count={prev_count}",
            flush=True,
        )
        start_time = time.time()
        while time.time() - start_time < timeout:
            if len(self._captured_responses) > prev_count:
                print(
                    f"[BrowserSearch] 捕获到新页面响应 count={len(self._captured_responses)}",
                    flush=True,
                )
                self.search_results = self._captured_responses
                return True
            await asyncio.sleep(0.5)

        print(
            f"[BrowserSearch] 等待新页面响应超时 当前count={len(self._captured_responses)}",
            flush=True,
        )
        return False

    def _parse_results(self) -> List[SearchItem]:
        """解析搜索结果（带曝光度计算）"""
        items = []

        if not self.search_results:
            return []

        result = self.search_results[-1]
        data = result.get("data", {})
        result_list = data.get("resultList", [])

        # 获取当前时间（用于计算曝光度）
        from datetime import datetime

        now = datetime.now()

        for item_data in result_list:
            try:
                main = item_data.get("data", {}).get("item", {}).get("main", {})
                if not main:
                    continue

                ex_content = main.get("exContent", {})
                click_param = main.get("clickParam", {}).get("args", {})

                item_id = click_param.get("item_id") or ex_content.get("itemId", "")
                if not item_id:
                    continue

                publish_time_str = None
                publish_time_ms = click_param.get("publishTime")
                publish_dt = None
                if publish_time_ms:
                    try:
                        import datetime

                        publish_dt = datetime.datetime.fromtimestamp(
                            int(publish_time_ms) / 1000
                        )
                        publish_time_str = publish_dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        pass

                want_cnt = 0
                fish_tags = ex_content.get("fishTags", {})
                for region in fish_tags.values():
                    tag_list = region.get("tagList", []) if region else []
                    for tag in tag_list:
                        content = tag.get("data", {}).get("content", "")
                        if content and content.endswith("人想要"):
                            want_cnt = int(content.replace("人想要", ""))

                # 计算曝光度：(想要人数 × 100) / (天数差 + 1)
                exposure_score = 0.0
                if publish_dt:
                    hours_diff = (now - publish_dt).total_seconds() / 3600
                    days_diff = hours_diff / 24
                    exposure_score = (want_cnt * 100) / (days_diff + 1)
                else:
                    # 没有发布时间时，假设刚发布
                    exposure_score = want_cnt * 100

                price_list = ex_content.get("price", [])
                price_str = (
                    "".join(p.get("text", "") for p in price_list)
                    if price_list
                    else "0"
                )

                pic_url = ex_content.get("picUrl", "")
                image_infos = ex_content.get("imageInfos", [])
                image_urls = (
                    [img.get("url", "") for img in image_infos] if image_infos else []
                )
                if pic_url and pic_url not in image_urls:
                    image_urls.insert(0, pic_url)

                is_free_ship = "包邮" in click_param.get("tagname", "")

                item = SearchItem(
                    item_id=item_id,
                    title=ex_content.get("title", ""),
                    price=price_str,
                    original_price=ex_content.get("oriPrice", "0"),
                    want_cnt=want_cnt,
                    seller_nick=ex_content.get("userNickName", ""),
                    seller_city=ex_content.get("area", ""),
                    image_urls=image_urls,
                    detail_url=f"https://www.goofish.com/item?id={item_id}",
                    is_free_ship=is_free_ship,
                    publish_time=publish_time_str,
                    exposure_score=exposure_score,
                )
                items.append(item)

            except Exception as e:
                print(f"[BrowserSearch] 解析商品数据出错：{e}")
                continue

        return items

    async def get_item_details(self, item_ids: List[str]) -> Dict[str, Dict]:
        """获取商品详情"""
        if not await self.chrome_manager.ensure_running():
            return {}

        details = {}

        async def process_response(response):
            if "mtop.taobao.idle.pc.detail" in response.url:
                try:
                    data = await response.json()
                    item_do = data.get("data", {}).get("itemDO", {})
                    seller_do = data.get("data", {}).get("sellerDO", {})

                    detail_info = {
                        "publish_time": item_do.get("GMT_CREATE_DATE_KEY"),
                        "last_visit_time": seller_do.get("lastVisitTime"),
                        "seller_register_time": seller_do.get("registerTime"),
                    }

                    target_url = item_do.get("targetUrl", "")
                    if "itemId=" in target_url:
                        item_id = target_url.split("itemId=")[1].split("&")[0]
                        details[item_id] = detail_info
                except Exception as e:
                    print(f"[BrowserSearch] 解析详情页失败：{e}")

        def on_response(response):
            asyncio.create_task(process_response(response))

        self.chrome_manager.page.on("response", on_response)

        for item_id in item_ids:
            try:
                url = f"https://www.goofish.com/item?id={item_id}"
                await self.chrome_manager.navigate(url, wait_until="domcontentloaded")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"[BrowserSearch] 获取商品 {item_id} 详情失败：{e}")

        return details


# ==================== 发布实现（从 item_copier.py 迁移） ====================


class _ItemCopierImpl:
    """商品复制发布器（内部实现）"""

    def __init__(self, chrome_manager: AsyncChromeManager):
        self.chrome_manager = chrome_manager
        self.captured_data: Dict[str, Any] = {}

    async def capture_item_detail(
        self, item_url: str, timeout: int = 15
    ) -> Optional[CopiedItem]:
        """打开商品链接并捕获详情 API 数据"""
        self.captured_data = {}

        if not await self.chrome_manager.ensure_running():
            print("[ItemCopier] 浏览器启动失败")
            return None

        page = self.chrome_manager.page
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
        await self.chrome_manager.navigate(item_url)

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
        await self.chrome_manager.navigate("https://www.goofish.com/publish")
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

        page = self.chrome_manager.page
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
            page = self.chrome_manager.page
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
            page = self.chrome_manager.page
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
            page = self.chrome_manager.page
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
            page = self.chrome_manager.page
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
            page = self.chrome_manager.page
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
            page = self.chrome_manager.page
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
            page = self.chrome_manager.page
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
            page = self.chrome_manager.page
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
            page = self.chrome_manager.page
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
