from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

from ..models import Window
from .base import PlatformAdapter


class CapturedFrame:
    def __init__(self, pil_image: Any, scale_x: float, scale_y: float) -> None:
        self.pil_image = pil_image
        self.native_image = None
        self.scale_x = scale_x
        self.scale_y = scale_y


class WindowsAdapter(PlatformAdapter):
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WindowsAdapter 只能在 Windows 上使用")
        try:
            import win32api  # type: ignore
            import win32con  # type: ignore
            import win32gui  # type: ignore
            import win32process  # type: ignore
            from PIL import ImageGrab
        except ImportError as exc:
            raise RuntimeError("缺少 Windows 依赖，请安装 windows 依赖") from exc
        self.win32api = win32api
        self.win32con = win32con
        self.win32gui = win32gui
        self.win32process = win32process
        self.image_grab = ImageGrab

    def windows(self) -> list[Window]:
        result: list[Window] = []
        current_pid = os.getpid()

        def collect(hwnd: int, _: Any) -> None:
            if not self.win32gui.IsWindowVisible(hwnd) or self.win32gui.IsIconic(hwnd):
                return
            title = self.win32gui.GetWindowText(hwnd).strip()
            if not title or self.win32gui.GetClassName(hwnd) in {"Progman", "WorkerW"}:
                return
            ex_style = self.win32gui.GetWindowLong(hwnd, self.win32con.GWL_EXSTYLE)
            if ex_style & self.win32con.WS_EX_TOOLWINDOW:
                return
            left, top, right, bottom = self.win32gui.GetWindowRect(hwnd)
            if right - left < 300 or bottom - top < 200:
                return
            _, pid = self.win32process.GetWindowThreadProcessId(hwnd)
            if pid == current_pid:
                return
            result.append(Window(hwnd, title, self._owner_name(pid)))

        self.win32gui.EnumWindows(collect, None)
        return sorted(result, key=lambda window: (window.owner.casefold(), window.title.casefold()))

    def capture(self, window: Window) -> Any:
        left, top, right, bottom = self._rect(window)
        try:
            image = self.image_grab.grab(bbox=(left, top, right, bottom), all_screens=True)
        except Exception as exc:
            raise RuntimeError(f"窗口截图失败：{exc}") from exc
        logical_width, logical_height = image.size
        scale = min(1.0, 1600 / logical_width, 1000 / logical_height)
        width = max(1, int(logical_width * scale))
        height = max(1, int(logical_height * scale))
        if (width, height) != image.size:
            image = image.resize((width, height))
        return CapturedFrame(image, width / logical_width, height / logical_height)

    def click(self, window: Window, x: float, y: float) -> None:
        left, top, _, _ = self._rect(window)
        self.win32gui.ShowWindow(window.id, self.win32con.SW_RESTORE)
        self.win32gui.SetForegroundWindow(window.id)
        time.sleep(0.12)
        self.win32api.SetCursorPos((round(left + x), round(top + y)))
        self.win32api.mouse_event(self.win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        self.win32api.mouse_event(self.win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def permissions(self) -> tuple[bool, bool]:
        return True, True

    def _rect(self, window: Window) -> tuple[int, int, int, int]:
        if not self.win32gui.IsWindow(window.id):
            raise RuntimeError("目标窗口已不可用")
        left, top, right, bottom = self.win32gui.GetWindowRect(window.id)
        if right <= left or bottom <= top:
            raise RuntimeError("目标窗口尺寸无效")
        return left, top, right, bottom

    def _owner_name(self, pid: int) -> str:
        handle = None
        try:
            access = self.win32con.PROCESS_QUERY_INFORMATION | self.win32con.PROCESS_VM_READ
            handle = self.win32api.OpenProcess(access, False, pid)
            path = self.win32process.GetModuleFileNameEx(handle, 0)
            return Path(path).stem or "未知应用"
        except Exception:
            return "未知应用"
        finally:
            if handle is not None:
                self.win32api.CloseHandle(handle)
