from __future__ import annotations

import sys
import os
import threading
import time
from typing import Any

if sys.platform == "darwin":
    from Foundation import NSObject  # type: ignore
else:
    NSObject = object  # type: ignore[misc,assignment]

from ..models import Window
from .base import PlatformAdapter


class CapturedFrame:
    def __init__(self, pil_image: Any, native_image: Any, scale_x: float, scale_y: float) -> None:
        self.pil_image = pil_image
        self.native_image = native_image
        self.scale_x = scale_x
        self.scale_y = scale_y


class ScreenCaptureOutputDelegate(NSObject):
    def stream_didOutputSampleBuffer_ofType_(
        self, stream: Any, sample_buffer: Any, output_type: int
    ) -> None:
        self.handle_sample(sample_buffer)


class MacOSAdapter(PlatformAdapter):
    """macOS 适配器，用 ScreenCaptureKit 捕捉窗口（稳定截图 + 预览）。"""

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("MacOSAdapter 只能在 macOS 上使用")
        # ScreenCaptureKit 的 SCStream 需要 NSApplication 已初始化，
        # 否则报 CGS_REQUIRE_INIT 导致截图失败（打包 app 里必须显式初始化）。
        try:
            from AppKit import NSApplication  # type: ignore

            NSApplication.sharedApplication()
        except Exception:
            pass
        try:
            import Quartz  # type: ignore
            import ScreenCaptureKit  # type: ignore
        except ImportError as exc:
            raise RuntimeError("缺少 macOS 屏幕捕捉依赖，请安装 macos 依赖") from exc
        self.quartz = Quartz
        self.screen_capture_kit = ScreenCaptureKit
        self._shareable_windows: dict[int, Any] = {}
        self._capture_lock = threading.Lock()

    def windows(self) -> list[Window]:
        hidden_owners = {
            "Control Center", "Dock", "Notification Center", "Spotlight",
            "SystemUIServer", "Wallpaper", "Window Server", "WindowManager",
            "ChatGPT Computer Use",
            "程序坞", "通知中心", "聚焦", "问题报告程序",
        }
        content = self._get_shareable_content()
        result: list[Window] = []
        self._shareable_windows = {}
        for sc_window in content.windows():
            title = str(sc_window.title() or "").strip()
            application = sc_window.owningApplication()
            owner = str(application.applicationName() if application else "未知应用")
            pid = int(application.processID()) if application else 0
            frame = sc_window.frame()
            if (
                not title
                or title.lower() == "undefined"
                or not owner
                or owner in hidden_owners
                or (owner == "ChatGPT" and ("Codex Pet" in title or "Voice Controls Glass" in title))
                or pid == os.getpid()
                # Stage Manager exposes windows in other groups as tiny
                # thumbnails. They are not valid capture targets.
                or frame.size.width < 300
                or frame.size.height < 200
            ):
                continue
            window = Window(int(sc_window.windowID()), title, owner)
            self._shareable_windows[window.id] = sc_window
            result.append(window)
        return sorted(result, key=lambda window: (window.owner.casefold(), window.title.casefold()))

    def _get_shareable_content(self) -> Any:
        event = threading.Event()
        result: dict[str, Any] = {}

        def completed(content: Any, error: Any) -> None:
            result["content"] = content
            result["error"] = error
            event.set()

        self.screen_capture_kit.SCShareableContent.getShareableContentWithCompletionHandler_(completed)
        if not event.wait(3):
            raise RuntimeError("获取可捕捉窗口超时")
        if result.get("error") is not None or result.get("content") is None:
            raise RuntimeError(f"获取可捕捉窗口失败：{result.get('error')}")
        return result["content"]

    def capture(self, window: Window) -> Any:
        with self._capture_lock:
            return self._capture_window(window)

    def _capture_window(self, window: Window) -> Any:
        sc_window = self._shareable_windows.get(window.id)
        if sc_window is None:
            self.windows()
            sc_window = self._shareable_windows.get(window.id)
        if sc_window is None:
            return None

        from PIL import Image
        import CoreMedia  # type: ignore

        frame = sc_window.frame()
        if frame.size.width < 300 or frame.size.height < 200:
            return None
        logical_width = max(1, int(frame.size.width))
        logical_height = max(1, int(frame.size.height))
        scale = min(1.0, 1600 / logical_width, 1000 / logical_height)
        width = max(1, int(logical_width * scale))
        height = max(1, int(logical_height * scale))
        config = self.screen_capture_kit.SCStreamConfiguration.alloc().init()
        config.setWidth_(width)
        config.setHeight_(height)
        config.setPixelFormat_(1111970369)  # kCVPixelFormatType_32BGRA
        config.setMinimumFrameInterval_(CoreMedia.CMTimeMake(1, 30))
        config.setShowsCursor_(False)
        config.setIgnoreShadowsSingleWindow_(True)
        content_filter = self.screen_capture_kit.SCContentFilter.alloc().initWithDesktopIndependentWindow_(sc_window)
        event = threading.Event()
        result: dict[str, Any] = {}

        def handle_sample(sample_buffer: Any) -> None:
            if event.is_set():
                return
            try:
                pixel_buffer = CoreMedia.CMSampleBufferGetImageBuffer(sample_buffer)
                if pixel_buffer is None:
                    return
                quartz = self.quartz
                quartz.CVPixelBufferLockBaseAddress(pixel_buffer, 0)
                try:
                    base_address = quartz.CVPixelBufferGetBaseAddress(pixel_buffer)
                    size = quartz.CVPixelBufferGetDataSize(pixel_buffer)
                    raw = b"".join(base_address[:size])
                    result["image"] = Image.frombytes(
                        "RGBA",
                        (quartz.CVPixelBufferGetWidth(pixel_buffer), quartz.CVPixelBufferGetHeight(pixel_buffer)),
                        raw,
                        "raw",
                        "BGRA",
                        quartz.CVPixelBufferGetBytesPerRow(pixel_buffer),
                        1,
                    )
                    provider = quartz.CGDataProviderCreateWithCFData(raw)
                    result["native_image"] = quartz.CGImageCreate(
                        quartz.CVPixelBufferGetWidth(pixel_buffer),
                        quartz.CVPixelBufferGetHeight(pixel_buffer),
                        8,
                        32,
                        quartz.CVPixelBufferGetBytesPerRow(pixel_buffer),
                        quartz.CGColorSpaceCreateDeviceRGB(),
                        quartz.kCGImageAlphaPremultipliedFirst | quartz.kCGBitmapByteOrder32Little,
                        provider,
                        None,
                        False,
                        quartz.kCGRenderingIntentDefault,
                    )
                finally:
                    quartz.CVPixelBufferUnlockBaseAddress(pixel_buffer, 0)
            except Exception as exc:
                result["error"] = exc
            finally:
                event.set()

        delegate = ScreenCaptureOutputDelegate.alloc().init()
        delegate.handle_sample = handle_sample
        stream = self.screen_capture_kit.SCStream.alloc().initWithFilter_configuration_delegate_(
            content_filter, config, delegate
        )
        added, error = stream.addStreamOutput_type_sampleHandlerQueue_error_(
            delegate, self.screen_capture_kit.SCStreamOutputTypeScreen, None, None
        )
        if not added or error is not None:
            return None
        def started(start_error: Any) -> None:
            if start_error is not None:
                result["error"] = start_error
                event.set()

        stream.startCaptureWithCompletionHandler_(started)
        event.wait(3)
        stopped = threading.Event()
        stream.stopCaptureWithCompletionHandler_(lambda stop_error: stopped.set())
        stopped.wait(1)
        if result.get("error") is not None:
            raise RuntimeError(f"窗口捕捉失败：{result['error']}")
        image = result.get("image")
        if image is None:
            return None
        return CapturedFrame(
            image,
            result.get("native_image"),
            width / logical_width,
            height / logical_height,
        )

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
        # 坐标换算：
        # CGWindowBounds 的 Y 是窗口顶部距屏幕顶部的距离（顶部原点）。
        # CGEvent 用的是底部原点坐标系（屏幕左下角为原点）。
        # 因此：
        #   screen_x = bounds.X + x                    （X 两个坐标系一致）
        #   screen_y = 屏幕高度 - (bounds.Y + y)       （转底部原点）
        # 其中 y 是 OCR 返回的窗口相对坐标（从窗口顶部向下）。
        main = self.quartz.CGDisplayBounds(self.quartz.CGMainDisplayID())
        screen_height = float(main.size.height)
        window_x = float(bounds.get("X", 0))
        window_top = float(bounds.get("Y", 0))
        screen_x = window_x + x
        screen_y = screen_height - (window_top + y)
        event_source = self.quartz.CGEventSourceCreate(self.quartz.kCGEventSourceStateHIDSystemState)
        move = self.quartz.CGEventCreateMouseEvent(event_source, self.quartz.kCGEventMouseMoved, (screen_x, screen_y), self.quartz.kCGMouseButtonLeft)
        down = self.quartz.CGEventCreateMouseEvent(event_source, self.quartz.kCGEventLeftMouseDown, (screen_x, screen_y), self.quartz.kCGMouseButtonLeft)
        up = self.quartz.CGEventCreateMouseEvent(event_source, self.quartz.kCGEventLeftMouseUp, (screen_x, screen_y), self.quartz.kCGMouseButtonLeft)
        self.quartz.CGEventPost(self.quartz.kCGHIDEventTap, move)
        time.sleep(0.05)
        self.quartz.CGEventPost(self.quartz.kCGHIDEventTap, down)
        time.sleep(0.05)
        self.quartz.CGEventPost(self.quartz.kCGHIDEventTap, up)

    def permissions(self) -> tuple[bool, bool]:
        screen = bool(self.quartz.CGPreflightScreenCaptureAccess())
        from ApplicationServices import AXIsProcessTrusted  # type: ignore

        control = bool(AXIsProcessTrusted())
        return screen, control

    def request_screen_permission(self) -> None:
        """主动弹出屏幕录制授权框（macOS 10.15+）。"""
        request = getattr(self.quartz, "CGRequestScreenCaptureAccess", None)
        if request is not None:
            try:
                request()
            except Exception:
                pass

    def request_accessibility_permission(self) -> None:
        """主动弹出辅助功能授权框。"""
        try:
            from ApplicationServices import (
                AXIsProcessTrustedWithOptions,
                kAXTrustedCheckOptionPrompt,
            )
            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        except Exception:
            pass
