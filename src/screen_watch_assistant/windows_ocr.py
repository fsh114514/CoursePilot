"""Windows 10/11 自带 OCR 引擎封装（基于 winsdk / Windows.Media.Ocr）。

tesseract 对彩色反色 UI 小字（如蓝色按钮上的白字）识别不可靠，
而 Windows 自带 OCR 对这类内容识别准确率高（已在 ARM64 Win11 实测，
能准确识别「我还在看」按钮）。本模块封装 winsdk 的 OcrEngine。

注意：winsdk 只提供到 cp312 的 wheel，Windows 版必须用 Python ≤3.12 运行。
"""

from __future__ import annotations

import io
import threading
from typing import Any


class WindowsOCREngine:
    """Windows 自带 OCR 引擎封装。

    用法：
        engine = WindowsOCREngine()
        if engine.available:
            lines = engine.recognize(pil_image)  # 每行 {text, words:[{text,x,y,w,h}]}
    """

    def __init__(self) -> None:
        self._engine: Any = None
        self._error: str | None = None
        self._lock = threading.Lock()
        try:
            from winsdk.windows.media.ocr import OcrEngine
            from winsdk.windows.globalization import Language

            # 优先用简体中文语言创建引擎
            try:
                self._engine = OcrEngine.try_create_from_language(Language("zh-Hans"))
            except Exception:
                self._engine = None
            if self._engine is None:
                # 回退：用用户配置文件语言
                self._engine = OcrEngine.try_create_from_user_profile_languages()
        except Exception as exc:  # 非 Windows / 未装 winsdk
            self._error = str(exc)
            self._engine = None

    @property
    def available(self) -> bool:
        return self._engine is not None

    @property
    def error(self) -> str | None:
        return self._error

    def recognize(self, pil_image: Any) -> list[dict[str, Any]]:
        """识别 PIL 图像，返回整行列表。

        每行：{"text": 行文本, "words": [{"text", "x", "y", "w", "h"}, ...]}
        坐标是图像像素坐标（bounding_rect 直接来自 OCR）。
        """
        if self._engine is None:
            return []
        try:
            return self._run_async(pil_image)
        except Exception:
            return []

    def _run_async(self, pil_image: Any) -> list[dict[str, Any]]:
        """winsdk 是异步 API，用 asyncio.run 包装执行。"""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._recognize_async(pil_image))
        finally:
            loop.close()

    async def _recognize_async(self, pil_image: Any) -> list[dict[str, Any]]:
        from winsdk.windows.graphics.imaging import BitmapDecoder
        from winsdk.windows.storage.streams import (
            DataWriter,
            InMemoryRandomAccessStream,
        )

        # PIL 图像 → PNG bytes
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        # PNG bytes → InMemoryRandomAccessStream
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream.get_output_stream_at(0))
        writer.write_bytes(png_bytes)
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)

        # → SoftwareBitmap
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        # OCR
        result = await self._engine.recognize_async(bitmap)

        lines: list[dict[str, Any]] = []
        for line in result.lines:
            words = []
            for word in line.words:
                rect = word.bounding_rect
                words.append({
                    "text": word.text,
                    "x": float(rect.x),
                    "y": float(rect.y),
                    "w": float(rect.width),
                    "h": float(rect.height),
                })
            lines.append({"text": line.text, "words": words})
        return lines
