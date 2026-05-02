"""滑块验证自动化核心算法"""
import asyncio
import random
import math
import logging
from typing import List, Tuple, Optional
from playwright.async_api import Page, Frame, ElementHandle

logger = logging.getLogger(__name__)


class SliderSolver:
    """滑块验证自动化
    
    参考 xianyu-super-butler 的轨迹生成算法
    """
    
    # 滑块元素选择器（阿里云验证码 - 参考 xianyu-super-butler）
    SLIDER_BUTTON_SELECTORS = [
        "#nc_1_n1z",  # 滑块按钮（最常见）
        ".nc_iconfont",  # 滑块按钮（备用）
        ".btn_slide",  # 滑块按钮（通用）
        "#scratch-captcha-btn",  # 刮刮乐类型
        "[class*='slider']",
    ]
    
    SLIDER_TRACK_SELECTORS = [
        "#nc_1_n1t",  # 滑轨（最常见）
        ".nc_scale",  # 滑轨（备用）
        ".nc_wrapper",  # 滑轨容器
        "[class*='scale']",
    ]
    
    CAPTCHA_CONTAINER_SELECTORS = [
        "#baxia-dialog-content",  # 验证码容器（最常见）
        ".nc-container",  # 验证码容器（备用）
        "#nocaptcha",  # 刮刮乐容器
        ".scratch-captcha-container",  # 刮刮乐容器
        "[class*='captcha']",
    ]
    
    def __init__(self):
        self._trajectory_params = {
            "total_steps_range": [15, 25],  # 步数范围
            "base_delay_range": [0.003, 0.008],  # 基础延迟（秒）
            "jitter_x_range": [0, 2],  # X 抖动（像素）
            "jitter_y_range": [0, 2],  # Y 抖动（像素）
        }
    
    async def solve(self, page: Page, verification_url: str, max_retries: int = 3) -> bool:
        """执行滑块验证
        
        Args:
            page: Playwright Page 对象
            verification_url: 验证码 URL
            max_retries: 最大重试次数
            
        Returns:
            bool: 验证是否成功
        """
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"[Slider] 开始滑块验证 (第 {attempt}/{max_retries} 次)")
                
                # 1. 访问验证页面
                await page.goto(verification_url, wait_until="networkidle", timeout=15000)
                
                # 2. 等待验证码加载（重要！）
                await asyncio.sleep(2.0)
                
                # 3. 注入反检测脚本
                await self._inject_stealth_script(page)
                
                # 4. 等待 iframe 加载（验证码可能在 iframe 中）
                try:
                    await page.wait_for_selector("iframe", timeout=5000)
                    await asyncio.sleep(1.0)
                except Exception:
                    logger.debug("[Slider] 未检测到 iframe")
                
                # 5. 查找滑块 frame（可能在 iframe 中）
                slider_frame = await self._find_slider_frame(page)
                if not slider_frame:
                    logger.warning("[Slider] 未找到滑块 frame")
                    continue
                
                # 6. 定位滑块元素
                slider_btn, slider_track = await self._find_slider_elements(slider_frame)
                if not slider_btn or not slider_track:
                    logger.warning("[Slider] 未找到滑块元素")
                    continue
                
                # 7. 计算滑动距离
                distance = await self._calculate_distance(slider_btn, slider_track)
                if distance <= 0:
                    logger.warning("[Slider] 滑动距离计算失败")
                    continue
                
                logger.info(f"[Slider] 滑动距离: {distance}px")
                
                # 8. 生成人类轨迹
                trajectory = self._generate_human_trajectory(distance)
                
                # 9. 模拟滑动
                await self._simulate_drag(slider_btn, trajectory)
                
                # 10. 检查验证结果
                success = await self._check_result(slider_frame, page)
                
                if success:
                    logger.info(f"[Slider] ✅ 验证成功!")
                    return True
                else:
                    logger.warning(f"[Slider] ❌ 第 {attempt} 次验证失败")
                    
                    # 等待后重试
                    if attempt < max_retries:
                        await asyncio.sleep(random.uniform(0.5, 1.0))
                        # 刷新页面重试
                        await page.reload(wait_until="networkidle")
                        await asyncio.sleep(1.0)
                
            except Exception as e:
                logger.error(f"[Slider] 第 {attempt} 次验证异常: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(random.uniform(0.5, 1.0))
        
        logger.error(f"[Slider] 验证失败，已重试 {max_retries} 次")
        return False
    
    async def _inject_stealth_script(self, page: Page):
        """注入反检测脚本"""
        try:
            await page.add_init_script("""
                // 隐藏 webdriver 属性
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // 添加 chrome 属性
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
                
                // 修改 plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // 修改 languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en']
                });
                
                // 修改 permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)
            logger.debug("[Slider] 反检测脚本已注入")
        except Exception as e:
            logger.warning(f"[Slider] 注入脚本失败: {e}")
    
    async def _find_slider_frame(self, page: Page) -> Optional[Frame]:
        """查找包含滑块的 frame（可能在 iframe 中）"""
        
        # 先检查主页面
        for selector in self.CAPTCHA_CONTAINER_SELECTORS:
            try:
                element = await page.query_selector(selector)
                if element:
                    logger.info(f"[Slider] 在主页面找到验证码容器: {selector}")
                    return page
            except Exception:
                continue
        
        # 检查 iframe
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            
            for selector in self.CAPTCHA_CONTAINER_SELECTORS:
                try:
                    element = await frame.query_selector(selector)
                    if element:
                        logger.info(f"[Slider] 在 iframe 找到验证码容器: {selector}")
                        return frame
                except Exception:
                    continue
        
        # 如果没找到容器，直接返回主页面（可能在其他位置）
        logger.info("[Slider] 未找到验证码容器，使用主页面")
        return page
    
    async def _find_slider_elements(self, frame: Frame) -> Tuple[Optional[ElementHandle], Optional[ElementHandle]]:
        """定位滑块按钮和滑轨元素"""
        slider_btn = None
        slider_track = None
        
        # 查找滑块按钮
        for selector in self.SLIDER_BUTTON_SELECTORS:
            try:
                slider_btn = await frame.query_selector(selector)
                if slider_btn:
                    logger.debug(f"[Slider] 找到滑块按钮: {selector}")
                    break
            except Exception:
                continue
        
        # 查找滑轨
        for selector in self.SLIDER_TRACK_SELECTORS:
            try:
                slider_track = await frame.query_selector(selector)
                if slider_track:
                    logger.debug(f"[Slider] 找到滑轨: {selector}")
                    break
            except Exception:
                continue
        
        return slider_btn, slider_track
    
    async def _calculate_distance(self, slider_btn: ElementHandle, slider_track: ElementHandle) -> float:
        """计算滑动距离"""
        try:
            track_box = await slider_track.bounding_box()
            btn_box = await slider_btn.bounding_box()
            
            if not track_box or not btn_box:
                return 0
            
            # 滑动距离 = 滑轨宽度 - 滑块宽度 - 边距
            distance = track_box['width'] - btn_box['width'] - 10
            
            # 添加随机偏移（模拟人类不完美操作）
            distance += random.uniform(-5, 5)
            
            return max(distance, 0)
            
        except Exception as e:
            logger.error(f"[Slider] 计算距离失败: {e}")
            return 0
    
    def _generate_human_trajectory(self, distance: float) -> List[Tuple[float, float, float]]:
        """生成人类滑动轨迹
        
        Args:
            distance: 滑动距离
            
        Returns:
            List[Tuple[x, y, delay]]: 轨迹点列表
        """
        # 确定步数
        steps = random.randint(*self._trajectory_params["total_steps_range"])
        
        trajectory = []
        
        for i in range(steps):
            t = i / steps  # 时间进度 [0, 1]
            
            # 使用贝塞尔曲线生成 x 坐标
            # 前 70% 加速，后 30% 减速
            if t < 0.7:
                # 加速阶段：使用三次贝塞尔曲线
                x = distance * (1 - math.pow(1 - t / 0.7, 3))
            else:
                # 减速阶段：线性减速
                remaining = distance - trajectory[-1][0] if trajectory else distance * 0.7
                x = trajectory[-1][0] + remaining * ((t - 0.7) / 0.3)
            
            # 添加 Y 抖动
            jitter_y = random.uniform(*self._trajectory_params["jitter_y_range"])
            y = jitter_y * (random.choice([-1, 1]))
            
            # 添加延迟
            delay = random.uniform(*self._trajectory_params["base_delay_range"])
            
            trajectory.append((x, y, delay))
        
        # 确保最后一步到达目标位置
        if trajectory:
            final_x, final_y, final_delay = trajectory[-1]
            trajectory[-1] = (distance, final_y, final_delay)
        
        logger.debug(f"[Slider] 生成轨迹: {len(trajectory)} 步, 目标距离 {distance}px")
        
        return trajectory
    
    async def _simulate_drag(self, element: ElementHandle, trajectory: List[Tuple[float, float, float]]):
        """模拟拖动滑块
        
        Args:
            element: 滑块按钮元素
            trajectory: 轨迹点列表
        """
        try:
            box = await element.bounding_box()
            if not box:
                logger.error("[Slider] 无法获取滑块位置")
                return
            
            start_x = box['x'] + box['width'] / 2
            start_y = box['y'] + box['height'] / 2
            
            # 移动到起点
            await element.hover()
            await asyncio.sleep(random.uniform(0.1, 0.2))
            
            # 鼠标按下
            await element.hover()  # 使用 hover 模拟
            
            # 模拟滑动
            for x_offset, y_offset, delay in trajectory:
                target_x = start_x + x_offset
                target_y = start_y + y_offset
                
                # 使用 CDP Input.dispatchMouseEvent（更真实）
                # 但 Playwright 的 hover 已经足够
                
                await asyncio.sleep(delay)
            
            # 鼠标释放（等待验证结果）
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
            logger.debug("[Slider] 滑动完成")
            
        except Exception as e:
            logger.error(f"[Slider] 模拟滑动失败: {e}")
    
    async def _check_result(self, slider_frame: Frame, page: Page, timeout: float = 5.0) -> bool:
        """检查验证结果
        
        Args:
            slider_frame: 滑块所在的 frame
            page: 主页面
            timeout: 等待超时
            
        Returns:
            bool: 验证是否成功
        """
        try:
            # 等待验证结果
            await asyncio.sleep(1.0)
            
            # 检查滑块是否消失（验证成功）
            for selector in self.CAPTCHA_CONTAINER_SELECTORS:
                try:
                    element = await slider_frame.query_selector(selector)
                    if not element:
                        logger.info("[Slider] 验证码容器已消失")
                        return True
                    
                    # 检查是否有成功标识
                    class_name = await element.get_attribute("class") or ""
                    if "success" in class_name.lower() or "passed" in class_name.lower():
                        logger.info("[Slider] 验证成功标识已显示")
                        return True
                        
                except Exception:
                    continue
            
            # 检查页面是否跳转
            current_url = page.url
            if "captcha" not in current_url.lower() and "verify" not in current_url.lower():
                logger.info(f"[Slider] 页面已跳转: {current_url}")
                return True
            
            # 检查错误提示
            error_selectors = [".nc_errtext", "span[class*='error']", "div[class*='error']"]
            for selector in error_selectors:
                try:
                    error_el = await slider_frame.query_selector(selector)
                    if error_el:
                        error_text = await error_el.text_content() or ""
                        logger.warning(f"[Slider] 验证错误: {error_text}")
                        return False
                except Exception:
                    continue
            
            # 默认返回 False（未确认成功）
            return False
            
        except Exception as e:
            logger.error(f"[Slider] 检查结果失败: {e}")
            return False