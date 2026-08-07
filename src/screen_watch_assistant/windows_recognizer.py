"""Windows 专用识别器：优先用系统自带 OCR（winsdk），tesseract 兜底。

不依赖 Apple Vision / ScreenCaptureKit，与 macOS 代码完全隔离。
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from typing import Any

from .models import ALLOWED_PROMPTS, TextMatch
from .recognizer_base import BaseRecognizer


def _make_windows_ocr() -> Any | None:
    """创建 Windows 自带 OCR 引擎（仅 Windows 可用），失败返回 None。"""
    if sys.platform != "win32":
        return None
    try:
        from .windows_ocr import WindowsOCREngine

        return WindowsOCREngine()
    except Exception:
        return None


def _bundled_tesseract_cmd() -> str | None:
    """返回 PyInstaller 打包时内置的 tesseract.exe 路径；源码运行返回 None。"""
    try:
        base = sys._MEIPASS  # type: ignore[attr-defined]
    except AttributeError:
        return None
    path = os.path.join(base, "tesseract", "tesseract.exe")
    return path if os.path.exists(path) else None


class WindowsRecognizer(BaseRecognizer):
    """Windows 识别器：系统自带 OCR（winsdk）优先，tesseract 兜底。"""

    def __init__(self, prompts: tuple[str, ...] = ALLOWED_PROMPTS) -> None:
        super().__init__(prompts)
        try:
            import pytesseract  # type: ignore
        except ImportError:
            pytesseract = None
        self.pytesseract = pytesseract
        self._tesseract_langs: tuple[str, ...] = ()
        self._bundled = False
        # Windows 自带 OCR（准确率高，优先使用）
        self.win_ocr = _make_windows_ocr()
        if self.win_ocr is not None and self.win_ocr.available:
            self._engine_ready = True
            self.engine_status = "✓ OCR 引擎就绪（系统 OCR）"
        else:
            self._configure_tesseract()

    def _configure_tesseract(self) -> None:
        """配置 tesseract 作为兜底引擎。"""
        if self.pytesseract is None:
            self._engine_ready = False
            self.engine_status = "⚠ OCR 引擎未就绪：未找到可用的 OCR 引擎"
            return
        bundled = _bundled_tesseract_cmd()
        if bundled:
            self.pytesseract.pytesseract.tesseract_cmd = bundled
            self._bundled = True
            self._engine_ready = True
            self._tesseract_langs = self._probe_languages(bundled)
            self.engine_status = "✓ OCR 引擎就绪（内置 Tesseract）"
        elif shutil.which("tesseract"):
            self._bundled = False
            self._engine_ready = True
            self._tesseract_langs = self._probe_languages(shutil.which("tesseract"))
            self.engine_status = "✓ OCR 引擎就绪（系统 Tesseract）"
        else:
            self._bundled = False
            self._engine_ready = False
            self._tesseract_langs = ()
            self.engine_status = "⚠ OCR 引擎未就绪：未找到 Tesseract"

    @staticmethod
    def _probe_languages(tesseract_cmd: str) -> tuple[str, ...]:
        """运行 `tesseract --list-langs` 探测可用语言（避免 windowed 弹黑窗）。"""
        import subprocess
        kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "errors": "replace",
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run([tesseract_cmd, "--list-langs"], **kwargs)
        except OSError:
            return ()
        if proc.returncode not in (0, 1):
            return ()
        langs = []
        for line in (proc.stdout or "").splitlines():
            lang = line.strip()
            if re.fullmatch(r"[a-z_]+", lang):
                langs.append(lang)
        return tuple(langs)

    def find(self, image: Any) -> TextMatch | None:
        if not self._engine_ready:
            return None
        frame = image
        image = getattr(frame, "pil_image", frame)
        scale_x = getattr(frame, "scale_x", 1.0)
        scale_y = getattr(frame, "scale_y", 1.0)
        # Windows 优先用系统自带 OCR
        if self.win_ocr is not None and self.win_ocr.available:
            return self._find_with_windows_ocr(image, scale_x, scale_y)
        if self.pytesseract is None:
            return None
        lang = "eng"
        if "chi_sim" in self._tesseract_langs:
            lang = "chi_sim+eng"
        preprocessed = self._preprocess_for_tesseract(image)
        data = self.pytesseract.image_to_data(preprocessed, output_type=self.pytesseract.Output.DICT, lang=lang)
        return self._match_from_tesseract_data(data, scale_x, scale_y)

    def _find_with_windows_ocr(self, image: Any, scale_x: float, scale_y: float) -> TextMatch | None:
        lines = self.win_ocr.recognize(image)
        best: tuple[float, TextMatch] | None = None
        for line in lines:
            line_text = self._normalize(line.get("text", ""))
            if not line_text:
                continue
            words = line.get("words") or []
            for prompt in self.prompts:
                target = self._normalize(prompt)
                start = line_text.find(target)
                if start < 0:
                    continue
                start_word = end_word = -1
                acc = 0
                for k, w in enumerate(words):
                    wtext = self._normalize(w.get("text", ""))
                    if not wtext:
                        continue
                    end = acc + len(wtext)
                    if start_word < 0 and acc <= start < end:
                        start_word = k
                    if acc < start + len(target) <= end:
                        end_word = k
                    acc = end
                if start_word < 0:
                    start_word = 0
                if end_word < start_word:
                    end_word = start_word
                sel = words[start_word:end_word + 1]
                if not sel:
                    continue
                left = min(w["x"] for w in sel) / scale_x
                top = min(w["y"] for w in sel) / scale_y
                right = max(w["x"] + w["w"] for w in sel) / scale_x
                bottom = max(w["y"] + w["h"] for w in sel) / scale_y
                confidence = 0.9
                match = TextMatch(prompt, confidence, (left + right) / 2, (top + bottom) / 2)
                score = confidence + (2 if line_text == target else 0)
                if best is None or score > best[0]:
                    best = (score, match)
        return best[1] if best else None

    @staticmethod
    def _preprocess_for_tesseract(image: Any) -> Any:
        """tesseract OCR 前预处理（灰度 + 增强对比度，提升按钮识别）。"""
        from PIL import Image, ImageEnhance
        if isinstance(image, Image.Image):
            gray = image.convert("L")
            return ImageEnhance.Contrast(gray).enhance(2.0)
        return image

    def _match_from_tesseract_data(
        self, data: dict[str, list[Any]], scale_x: float, scale_y: float
    ) -> TextMatch | None:
        """从 pytesseract image_to_data 结果匹配提示词（按行合并匹配）。"""
        text_list = data.get("text") or []
        n = len(text_list)
        lines: dict[tuple[int, int, int], list[int]] = {}
        for index in range(n):
            raw = text_list[index]
            text = self._normalize(raw)
            if not text:
                continue
            key = (
                int(data["block_num"][index]),
                int(data["par_num"][index]),
                int(data["line_num"][index]),
            )
            lines.setdefault(key, []).append(index)

        best: tuple[float, TextMatch] | None = None
        for indices in lines.values():
            indices = sorted(indices, key=lambda i: float(data["left"][i]))
            words: list[tuple[str, float, float, float, float, float]] = []
            for i in indices:
                w = self._normalize(data["text"][i])
                if not w:
                    continue
                words.append((
                    w,
                    float(data["left"][i]) / scale_x,
                    float(data["top"][i]) / scale_y,
                    float(data["width"][i]) / scale_x,
                    float(data["height"][i]) / scale_y,
                    float(data["conf"][i]) / 100,
                ))
            if not words:
                continue
            joined = "".join(w[0] for w in words)
            if not joined:
                continue
            for prompt in self.prompts:
                target = self._normalize(prompt)
                start = joined.find(target)
                if start < 0:
                    continue
                start_word = end_word = -1
                acc = 0
                for k, (w, *_rest) in enumerate(words):
                    end = acc + len(w)
                    if start_word < 0 and acc <= start < end:
                        start_word = k
                    if acc < start + len(target) <= end:
                        end_word = k
                    acc = end
                if start_word < 0:
                    start_word = 0
                if end_word < start_word:
                    end_word = start_word
                sel = words[start_word:end_word + 1]
                left = min(w[1] for w in sel)
                top = min(w[2] for w in sel)
                right = max(w[1] + w[3] for w in sel)
                bottom = max(w[2] + w[4] for w in sel)
                confidence = sum(w[5] for w in sel) / len(sel)
                if confidence < 0.75:
                    continue
                match = TextMatch(prompt, confidence, (left + right) / 2, (top + bottom) / 2)
                score = confidence + (2 if joined == target else 0)
                if best is None or score > best[0]:
                    best = (score, match)
        return best[1] if best else None
