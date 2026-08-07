from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes
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
        # 启用 DPI 感知：窗口 200% 缩放时，GetWindowRect/PrintWindow 必须用
        # 逻辑像素一致，否则 PrintWindow 截图会被裁剪/错位（实测修复）。
        self._enable_dpi_awareness()
        # 用 ctypes 直接调 GDI/user32（win32ui 的 MFC 封装在 ARM64 模拟层下
        # CreateCompatibleBitmap 会失败，ctypes 底层调用可靠）
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self._gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self._gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self._gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        self._gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        self._gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self._gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self._gdi32.GetDIBits.argtypes = [
            wintypes.HDC, wintypes.HBITMAP, ctypes.c_uint, ctypes.c_uint,
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
        ]
        self._gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self._gdi32.DeleteObject.restype = wintypes.BOOL
        self._gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self._gdi32.DeleteDC.restype = wintypes.BOOL
        self._user32.GetWindowDC.argtypes = [wintypes.HWND]
        self._user32.GetWindowDC.restype = wintypes.HDC
        self._user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self._user32.ReleaseDC.restype = ctypes.c_int
        self._user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
        self._user32.PrintWindow.restype = wintypes.BOOL

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

    @staticmethod
    def _enable_dpi_awareness() -> None:
        """启用进程 DPI 感知。

        高 DPI（如 200% 缩放）下，GetWindowRect 返回物理像素，而 PrintWindow
        需要逻辑像素。不启用 DPI 感知会导致 PrintWindow 截图像素错乱、
        窗口内容被裁剪（实测 ARM64 虚拟机 200% 缩放下弹窗只截到一角）。
        """
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor V2
            return
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    def capture(self, window: Window) -> Any:
        left, top, right, bottom = self._rect(window)
        width_px = right - left
        height_px = bottom - top
        image = None
        # 优先用 PrintWindow 捕获窗口自身内容（即使被遮挡也能拿到完整渲染）
        try:
            image = self._capture_with_printwindow(window.id, width_px, height_px)
        except Exception:
            image = None
        if image is None:
            # 回退：屏幕级抓取（窗口未被遮挡时效果一样，被遮挡时会取到遮挡窗口）
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

    def _capture_with_printwindow(self, hwnd: int, width: int, height: int) -> Any | None:
        """用 PrintWindow + PW_RENDERFULLCONTENT 捕获窗口的完整渲染内容。

        PrintWindow 让 DWM 把窗口内容绘制到指定 DC，即使窗口被其它窗口遮挡，
        也能得到窗口自身的图像（这是屏幕级 ImageGrab 做不到的）。
        """
        if width <= 0 or height <= 0:
            return None
        try:
            from PIL import Image
        except ImportError:
            return None
        hwnd_dc = self._user32.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None
        mem_dc = self._gdi32.CreateCompatibleDC(hwnd_dc)
        hbitmap = self._gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
        if not hbitmap or not mem_dc:
            if mem_dc:
                self._gdi32.DeleteDC(mem_dc)
            if hwnd_dc:
                self._user32.ReleaseDC(hwnd, hwnd_dc)
            return None
        old_bmp = self._gdi32.SelectObject(mem_dc, hbitmap)
        try:
            # 先尝试渲染完整内容（Win8.1+，DWM 合成窗口需要）
            result = self._user32.PrintWindow(hwnd, mem_dc, 0x00000002)
            if not result:
                # 回退：普通 PrintWindow
                result = self._user32.PrintWindow(hwnd, mem_dc, 0)
            if not result:
                return None
            # GetDIBits 读出 BGRA 位图
            class _BMIHeader(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD),
                    ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long),
                    ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            class _BMI(ctypes.Structure):
                _fields_ = [("bmiHeader", _BMIHeader), ("bmiColors", wintypes.DWORD * 3)]

            bmi = _BMI()
            bmi.bmiHeader.biSize = ctypes.sizeof(_BMIHeader)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height  # 负值 = 自顶向下
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0  # BI_RGB
            buf = ctypes.create_string_buffer(width * height * 4)
            got = self._gdi32.GetDIBits(mem_dc, hbitmap, 0, height, buf, ctypes.byref(bmi), 0)
            if not got:
                return None
            return Image.frombuffer(
                "RGB", (width, height), buf.raw, "raw", "BGRX", 0, 1
            )
        finally:
            self._gdi32.SelectObject(mem_dc, old_bmp)
            self._gdi32.DeleteObject(hbitmap)
            self._gdi32.DeleteDC(mem_dc)
            self._user32.ReleaseDC(hwnd, hwnd_dc)

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
