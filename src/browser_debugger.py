from __future__ import annotations

from datetime import datetime, timezone

from .utils.r2_uploader import upload_image_bytes


class BrowserDebugger:
    def __init__(self, browser):
        self.browser = browser

    async def capture_snapshot(
        self,
        *,
        user_id: str,
        slot_id: str,
        selected_by: str,
        full_page: bool = True,
    ) -> dict:
        try:
            page_kind, page = await self.browser.pick_debug_page()
        except RuntimeError as exc:
            message = str(exc)
            if "调试页面" in message or "浏览器" in message:
                raise RuntimeError("browser_not_ready") from exc
            raise RuntimeError("no_debug_page") from exc

        metadata = await self.browser.get_page_snapshot_metadata(page)
        try:
            image_bytes = await self.browser.capture_page_screenshot(
                page,
                full_page=full_page,
            )
        except Exception as exc:
            raise RuntimeError("screenshot_failed") from exc

        public_url = upload_image_bytes(
            image_data=image_bytes,
            content_type="image/png",
            key_prefix="xianyu/debug",
            custom_filename=f"debug-{user_id}",
        )
        if not public_url:
            raise RuntimeError("r2_upload_failed")

        return {
            "success": True,
            "user_id": user_id,
            "slot_id": slot_id,
            "selected_by": selected_by,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "page": {**metadata, "kind": page_kind},
            "screenshot": {"uploaded": True, "public_url": public_url},
            "recent_errors": [],
            "recent_failed_requests": [],
        }
