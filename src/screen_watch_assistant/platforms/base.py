from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import Window


class PlatformAdapter(ABC):
    @abstractmethod
    def windows(self) -> list[Window]:
        raise NotImplementedError

    @abstractmethod
    def capture(self, window: Window) -> Any:
        raise NotImplementedError

    @abstractmethod
    def click(self, window: Window, x: float, y: float) -> None:
        raise NotImplementedError

    @abstractmethod
    def permissions(self) -> tuple[bool, bool]:
        """Return (screen_capture_allowed, input_control_allowed)."""
        raise NotImplementedError
