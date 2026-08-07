from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any

if sys.platform == "darwin":
    import Quartz  # type: ignore
else:
    Quartz = None  # type: ignore

from ..models import Window
from .base import PlatformAdapter


class CapturedFrame:
    def __init__(self, pil_image: Any, native_image: Any, scale_x: float, scale_y: float) -> None:
        self.pil_image = pil_image
        self.native_image = native_image
        self.scale_x = scale_x
        self.scale_y = scale_y


class MacOSAdapter(PlatformAdapter):
    """macOS 适配器，用 CoreGraphics（CGWindowList）捕捉窗口。

    为什么不用 ScreenCaptureKit（SCShareableContent/SCStream）：
    SCShareableContent 在 macOS Sequoia+ 上每次调用都会触发
    "系统私有窗口选择器"权限弹窗，且依赖稳定的代码签名身份
    （adhoc 签名的无证书 app 权限反复失效）。
    而 CGWindowListCopyWindowInfo / CGWindowListCreateImage 是
    老牌 API，无需屏幕录制权限弹窗，adhoc 签名也可用（已实测）。
    """

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("MacOSAdapter 只能在 macOS 上使用")
        if Quartz is None:
            raise RuntimeError("缺少 macOS 屏幕捕捉依赖（Quartz）")
        self.quartz = Quartz
        self._capture_lock = threading.Lock()
        self._window_cache: dict[int, dict[str, Any]] = {}

    def windows(self) -> list[Window]:
        hidden_owners = {
            "Control Center", "Dock", "Notification Center", "Spotlight",
            "SystemUIServer", "Wallpaper", "Window Server", "WindowManager",
            "ChatGPT Computer Use",
            "程序坞", "通知中心", "聚焦", "问题报告程序",
        }
        info_list = self.quartz.CGWindowListCopyWindowInfo(
            self.quartz.kCGWindowListOptionOnScreenOnly,
            self.quartz.kCGNullWindowID,
        ) or []
        result: list[Window] = []
        self._window_cache = {}
        current_pid = os.getpid()
        for info in info_list:
            # 关键：kCGWindowName（窗口标题）在无屏幕录制权限时会被省略。
            # 此时 title 为空，但 kCGWindowOwnerName（应用名）和 bounds 仍可用。
            # 因此用 owner 识别窗口，不依赖 title（无权限时 title 为空也保留）。
            title = str(info.get(self.quartz.kCGWindowName, "") or "").strip()
            owner = str(info.get(self.quartz.kCGWindowOwnerName, "") or "")
            window_id = int(info.get(self.quartz.kCGWindowNumber, 0))
            pid = int(info.get(self.quartz.kCGWindowOwnerPID, 0))
            bounds = info.get(self.quartz.kCGWindowBounds, {})
            width = float(bounds.get("Width", 0))
            height = float(bounds.get("Height", 0))
            if (
                not owner
                or owner in hidden_owners
                or pid == current_pid
                or width < 300
                or height < 200
            ):
                continue
            # 无标题时用 owner 作为显示名（无权限环境）
            display_title = title or owner
            window = Window(window_id, display_title, owner)
            self._window_cache[window.id] = info
            result.append(window)
        return sorted(result, key=lambda window: (window.owner.casefold(), window.title.casefold()))

    def capture(self, window: Window) -> Any:
        with self._capture_lock:
            return self._capture_window(window)

    def _capture_window(self, window: Window) -> Any:
        # 获取窗口信息（优先用缓存的，避免频繁枚举）
        info = self._window_cache.get(window.id)
        if info is None:
            self.windows()
            info = self._window_cache.get(window.id)
        if info is None:
            return None
        bounds = info.get(self.quartz.kCGWindowBounds, {})
        logical_width = int(float(bounds.get("Width", 0)))
        logical_height = int(float(bounds.get("Height", 0)))
        if logical_width < 300 or logical_height < 200:
            return None

        # 用 CGWindowListCreateImage 捕捉窗口内容（无需屏幕录制权限弹窗）
        cg_image = self.quartz.CGWindowListCreateImage(
            self.quartz.CGRectMake(0, 0, logical_width, logical_height),
            self.quartz.kCGWindowListOptionIncludingWindow,
            window.id,
            self.quartz.kCGWindowImageBoundsIgnoreFraming | self.quartz.kCGWindowImageShouldBeOpaque,
        )
        if cg_image is None:
            return None

        cg_width = int(self.quartz.CGImageGetWidth(cg_image))
        cg_height = int(self.quartz.CGImageGetHeight(cg_image))
        if cg_width <= 0 or cg_height <= 0:
            return None

        # CGImage → PIL 图像（RGBA/BGRA）
        from PIL import Image

        provider = self.quartz.CGImageGetDataProvider(cg_image)
        data = self.quartz.CGDataProviderCopyData(provider)
        if data is None:
            return None
        raw = bytes(data)
        # 关键：CGImage 数据每行可能有 padding（stride ≠ width*bpp）。
        # 必须用 CGImageGetBytesPerRow 的 stride，否则 frombytes 会错乱/空白。
        bits_per_pixel = self.quartz.CGImageGetBitsPerPixel(cg_image)
        bytes_per_row = self.quartz.CGImageGetBytesPerRow(cg_image)
        if bits_per_pixel >= 32:
            pil = Image.frombytes(
                "RGBA", (cg_width, cg_height), raw, "raw", "BGRA", bytes_per_row, 1
            ).convert("RGB")
        else:
            pil = Image.frombytes(
                "RGB", (cg_width, cg_height), raw, "raw", "RGB", bytes_per_row, 1
            )

        # 缩放控制尺寸（避免过大的图拖慢 OCR）
        scale = min(1.0, 1600 / cg_width, 1000 / cg_height)
        width = max(1, int(cg_width * scale))
        height = max(1, int(cg_height * scale))
        if (width, height) != pil.size:
            pil = pil.resize((width, height))
        # 坐标换算：Vision OCR 基于 native_image（CGImage，Retina 可能是 2x）。
        # scale_x 用于把 CGImage 像素坐标换算回窗口逻辑坐标：
        #   逻辑坐标 = CGImage坐标 / scale_x
        # 因此 scale_x = cg_width / logical_width（Retina 下通常是 2.0）。
        # 注意：不是 width/logical_width（那是缩放后 PIL 的比例，会算错）。
        scale_x = cg_width / logical_width
        scale_y = cg_height / logical_height
        return CapturedFrame(pil, cg_image, scale_x, scale_y)

    def click(self, window: Window, x: float, y: float) -> None:
        # The adapter intentionally exposes only a point click. It does not inject
        # into browser pages or alter page visibility/focus checks.
        if threading.current_thread() is threading.main_thread():
            self._click_now(window, x, y)
            return

        from PyObjCTools import AppHelper  # type: ignore

        completed = threading.Event()
        errors: list[Exception] = []

        def perform() -> None:
            try:
                self._click_now(window, x, y)
            except Exception as exc:
                errors.append(exc)
            finally:
                completed.set()

        AppHelper.callAfter(perform)
        if not completed.wait(3):
            raise RuntimeError("点击操作等待主线程超时")
        if errors:
            raise errors[0]

    def _click_now(self, window: Window, x: float, y: float) -> None:
        info = self.quartz.CGWindowListCopyWindowInfo(
            self.quartz.kCGWindowListOptionIncludingWindow, window.id
        ) or []
        if not info:
            raise RuntimeError("目标窗口已不可用")
        bounds = info[0].get(self.quartz.kCGWindowBounds) or {}
        pid = int(info[0].get(self.quartz.kCGWindowOwnerPID, 0))
        if pid:
            from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication  # type: ignore

            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            if app is not None:
                app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                time.sleep(0.15)
                refreshed = self.quartz.CGWindowListCopyWindowInfo(
                    self.quartz.kCGWindowListOptionIncludingWindow, window.id
                ) or []
                if refreshed:
                    bounds = refreshed[0].get(self.quartz.kCGWindowBounds) or bounds
        # 坐标换算：CGWindowBounds 的 Y 是底部原点（窗口底边到屏幕底部的距离）。
        # OCR 坐标 (x, y) 是相对窗口左上角的向下距离（顶部原点）。
        # 因此按钮的屏幕 Y（底部原点）= 窗口顶部(底部原点) - y
        #   = (bounds.Y + bounds.Height) - y
        window_x = float(bounds.get("X", 0))
        window_bottom = float(bounds.get("Y", 0))
        window_height = float(bounds.get("Height", 0))
        screen_x = window_x + x
        screen_y = window_bottom + window_height - y
        event_source = self.quartz.CGEventSourceCreate(self.quartz.kCGEventSourceStateHIDSystemState)
        # 先移动鼠标到目标，再点击（Chrome 等对突然点击可能不响应）
        move = self.quartz.CGEventCreateMouseEvent(event_source, self.quartz.kCGEventMouseMoved, (screen_x, screen_y), self.quartz.kCGMouseButtonLeft)
        down = self.quartz.CGEventCreateMouseEvent(event_source, self.quartz.kCGEventLeftMouseDown, (screen_x, screen_y), self.quartz.kCGMouseButtonLeft)
        up = self.quartz.CGEventCreateMouseEvent(event_source, self.quartz.kCGEventLeftMouseUp, (screen_x, screen_y), self.quartz.kCGMouseButtonLeft)
        self.quartz.CGEventPost(self.quartz.kCGHIDEventTap, move)
        time.sleep(0.05)
        self.quartz.CGEventPost(self.quartz.kCGHIDEventTap, down)
        time.sleep(0.05)
        self.quartz.CGEventPost(self.quartz.kCGHIDEventTap, up)

    def permissions(self) -> tuple[bool, bool]:
        # CGWindowList 捕捉不需要屏幕录制权限；辅助功能用于点击
        from ApplicationServices import AXIsProcessTrusted  # type: ignore

        control = bool(AXIsProcessTrusted())
        return True, control

    def request_screen_permission(self) -> None:
        """主动弹出辅助功能授权框（用于自动点击）。

        AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        会弹出 macOS 的辅助功能授权框，用户无需手动去系统设置找。
        """
        try:
            from ApplicationServices import (
                AXIsProcessTrustedWithOptions,
                kAXTrustedCheckOptionPrompt,
            )
            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        except Exception:
            pass
