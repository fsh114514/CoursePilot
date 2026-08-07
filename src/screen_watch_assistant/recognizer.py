from __future__ import annotations

import os
import re
import shutil
import sys
from typing import Any

from .models import ALLOWED_PROMPTS, TextMatch


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
    """返回 PyInstaller 打包时内置的 tesseract.exe 路径；源码运行返回 None。

    PyInstaller 会把 --add-binary 的数据解包到 sys._MEIPASS 临时目录，
    内置引擎位于 sys._MEIPASS/tesseract/tesseract.exe。
    """
    try:
        base = sys._MEIPASS  # type: ignore[attr-defined]
    except AttributeError:
        return None
    path = os.path.join(base, "tesseract", "tesseract.exe")
    return path if os.path.exists(path) else None


class PromptRecognizer:
    """OCR-first recognizer with a strict prompt whitelist."""

    def __init__(self, prompts: tuple[str, ...] = ALLOWED_PROMPTS) -> None:
        try:
            import Vision  # type: ignore
        except ImportError:
            Vision = None
        try:
            import pytesseract  # type: ignore
        except ImportError:
            pytesseract = None
        self.vision = Vision
        self.pytesseract = pytesseract
        self.prompts = prompts
        self.engine_status = ""
        self._engine_ready = False
        # 兜底默认值（Windows OCR 可用时 _configure_tesseract 不会执行）
        self._tesseract_langs: tuple[str, ...] = ()
        self._bundled = False
        # Windows 自带 OCR（准确率高，优先使用）
        self.win_ocr = _make_windows_ocr()
        if self.win_ocr is not None and self.win_ocr.available:
            self._engine_ready = True
            self.engine_status = "✓ OCR 引擎就绪（系统 OCR）"
        else:
            self._configure_tesseract()
        if self.vision is None and not self._engine_ready:
            self.engine_status = "未找到 OCR 引擎（macOS 需 Apple Vision 框架，Windows 需系统 OCR 或 Tesseract）"

    def _configure_tesseract(self) -> None:
        """决定 tesseract 命令路径与引擎状态。"""
        if self.pytesseract is None:
            return
        bundled = _bundled_tesseract_cmd()
        if bundled:
            # 打包环境：使用内置引擎（用户免安装）
            self.pytesseract.pytesseract.tesseract_cmd = bundled
            self._bundled = True
            self._engine_ready = True
            self._tesseract_langs = self._probe_languages(bundled)
            self.engine_status = "✓ OCR 引擎就绪（内置 Tesseract）"
        elif shutil.which("tesseract"):
            # 源码运行 + 系统已装 tesseract
            self._bundled = False
            self._engine_ready = True
            self._tesseract_langs = self._probe_languages(shutil.which("tesseract"))
            self.engine_status = "✓ OCR 引擎就绪（系统 Tesseract）"
        else:
            self._bundled = False
            self._engine_ready = False
            self._tesseract_langs = ()
            self.engine_status = "⚠ OCR 引擎未就绪：未找到 Tesseract，无法在 Windows 上识别提示词"

    @staticmethod
    def _probe_languages(tesseract_cmd: str) -> tuple[str, ...]:
        """运行 `tesseract --list-langs` 探测可用语言。

        用 CREATE_NO_WINDOW 避免 --windowed 打包应用里闪黑窗；
        pytesseract 内置的 get_languages 没设该标志，这里自己跑一次。
        """
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
        native_image = getattr(image, "native_image", None)
        if native_image is not None and self.vision is not None:
            match = self._find_with_vision(native_image, getattr(image, "scale_x", 1.0), getattr(image, "scale_y", 1.0))
            # macOS 用 Vision，识别到就直接返回；未识别到则回退 pytesseract（若引擎就绪）
            if match is not None or not self._engine_ready:
                return match

        if not self._engine_ready:
            return None
        frame = image
        image = getattr(frame, "pil_image", frame)
        scale_x = getattr(frame, "scale_x", 1.0)
        scale_y = getattr(frame, "scale_y", 1.0)
        # Windows 优先用系统自带 OCR（对彩色按钮识别准确）。
        # 关键：Windows OCR 可用时只用它——不要回退 tesseract，
        # 因为此时 tesseract 可能未配置（tesseract_cmd 未指向内置引擎），
        # 一旦回退会抛 TesseractNotFoundError 导致监控崩溃。
        if self.win_ocr is not None and self.win_ocr.available:
            return self._find_with_windows_ocr(image, scale_x, scale_y)
        if self.pytesseract is None:
            return None
        lang = "eng"
        if "chi_sim" in getattr(self, "_tesseract_langs", ()):
            lang = "chi_sim+eng"
        preprocessed = self._preprocess_for_tesseract(image)
        data = self.pytesseract.image_to_data(preprocessed, output_type=self.pytesseract.Output.DICT, lang=lang)
        return self._match_from_tesseract_data(data, scale_x, scale_y)

    def _find_with_windows_ocr(self, image: Any, scale_x: float, scale_y: float) -> TextMatch | None:
        """用 Windows 自带 OCR 识别，并匹配提示词。

        Windows OCR 返回整行文本 + 每个 word 的边界框。逐行匹配提示词，
        匹配到后用该行 words 的边界框计算提示词中心点坐标。
        """
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
                # 找出 target 覆盖的 word 下标范围
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
                # Windows OCR 不给置信度，用 0.9 保守估计；整行精确匹配加分
                confidence = 0.9
                match = TextMatch(prompt, confidence, (left + right) / 2, (top + bottom) / 2)
                score = confidence + (2 if line_text == target else 0)
                if best is None or score > best[0]:
                    best = (score, match)
        return best[1] if best else None

    @staticmethod
    def _preprocess_for_tesseract(image: Any) -> Any:
        """tesseract OCR 前的图像预处理。

        tesseract 对低对比度的彩色 UI（如蓝色按钮上的白字）识别很差。
        实测：灰度 + 增强对比度后，按钮"我还在看"能被准确识别。
        这里的增强不影响坐标计算（scale_x/scale_y 不变，识别坐标同比例）。
        """
        from PIL import Image, ImageEnhance
        if isinstance(image, Image.Image):
            gray = image.convert("L")
            return ImageEnhance.Contrast(gray).enhance(2.0)
        return image

    def _match_from_tesseract_data(
        self, data: dict[str, list[Any]], scale_x: float, scale_y: float
    ) -> TextMatch | None:
        """从 pytesseract image_to_data 结果中匹配提示词。

        tesseract 常把「我还在看」拆成多个独立 word（每个字一行）。
        因此先按 (block, par, line) 把同行 word 合并成行文本，
        再对整行匹配提示词，并计算提示词在行内的位置用于点击。
        """
        text_list = data.get("text") or []
        n = len(text_list)
        # 收集每个 word：按行分组
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
            # 组内按 left 排序，保证文本顺序正确
            indices = sorted(indices, key=lambda i: float(data["left"][i]))
            # 收集该行的 word 文本与几何信息
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
                # 找出 target 覆盖的 word 下标范围
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
                # 用覆盖的 word 计算包围盒与置信度
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

    def _find_with_vision(self, image: Any, scale_x: float, scale_y: float) -> TextMatch | None:
        import Quartz  # type: ignore

        request = self.vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(self.vision.VNRequestTextRecognitionLevelAccurate)
        request.setRecognitionLanguages_(["zh-Hans", "en-US"])
        request.setUsesLanguageCorrection_(True)
        handler = self.vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, {})
        success, error = handler.performRequests_error_([request], None)
        if not success or error is not None:
            return None

        width = float(Quartz.CGImageGetWidth(image))
        height = float(Quartz.CGImageGetHeight(image))
        best: tuple[float, TextMatch] | None = None
        for observation in request.results() or []:
            candidate = observation.topCandidates_(1)
            if not candidate:
                continue
            raw = str(candidate[0].string())
            normalized = self._normalize(raw)
            for prompt in self.prompts:
                target = self._normalize(prompt)
                if not self._is_exact_prompt(normalized, target):
                    continue
                confidence = float(candidate[0].confidence())
                if confidence < 0.75:
                    continue
                box = observation.boundingBox()
                x = (box.origin.x * width + box.size.width * width / 2) / scale_x
                y = ((1 - box.origin.y - box.size.height / 2) * height) / scale_y
                match = TextMatch(prompt, confidence, x, y)
                score = confidence + (2 if normalized == target else 0)
                if best is None or score > best[0]:
                    best = (score, match)
        return best[1] if best else None

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", "", value).lower()

    @classmethod
    def _is_exact_prompt(cls, text: str, prompt: str) -> bool:
        return cls._normalize(text) == cls._normalize(prompt)
