from __future__ import annotations

import sys
from typing import Any

from ..models import Window
from .base import PlatformAdapter


class WindowsAdapter(PlatformAdapter):
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WindowsAdapter 只能在 Windows 上使用")
        raise NotImplementedError("Windows 窗口捕获适配器将在 macOS MVP 验证后接入")

    def windows(self) -> list[Window]:
        raise NotImplementedError

    def capture(self, window: Window) -> Any:
        raise NotImplementedError

    def click(self, window: Window, x: float, y: float) -> None:
        raise NotImplementedError

    def permissions(self) -> tuple[bool, bool]:
        return True, True
