"""共享的 OCR 匹配基础逻辑（平台无关）。

各平台的识别器继承自此类，复用提示词规范化与精确匹配逻辑。
"""

from __future__ import annotations

import re
from typing import Any

from .models import ALLOWED_PROMPTS, TextMatch


class BaseRecognizer:
    """平台无关的提示词匹配基类。"""

    def __init__(self, prompts: tuple[str, ...] = ALLOWED_PROMPTS) -> None:
        self.prompts = prompts
        self.engine_status = ""
        self._engine_ready = False

    def find(self, image: Any) -> TextMatch | None:
        raise NotImplementedError

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", "", value).lower()

    @classmethod
    def _is_exact_prompt(cls, text: str, prompt: str) -> bool:
        return cls._normalize(text) == cls._normalize(prompt)
