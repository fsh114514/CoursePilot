from __future__ import annotations

import re
import shutil
import sys
from typing import Any

from .models import ALLOWED_PROMPTS, TextMatch


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
        if self.vision is None and self.pytesseract is None:
            raise RuntimeError("缺少本地 OCR 后端")

    def find(self, image: Any) -> TextMatch | None:
        native_image = getattr(image, "native_image", None)
        if native_image is not None and self.vision is not None:
            match = self._find_with_vision(native_image, getattr(image, "scale_x", 1.0), getattr(image, "scale_y", 1.0))
            if match is not None or shutil.which("tesseract") is None:
                return match

        if self.pytesseract is None:
            return None
        frame = image
        image = getattr(frame, "pil_image", frame)
        scale_x = getattr(frame, "scale_x", 1.0)
        scale_y = getattr(frame, "scale_y", 1.0)
        lang = "eng"
        if sys.platform == "win32":
            try:
                if "chi_sim" in self.pytesseract.get_languages(config=""):
                    lang = "chi_sim+eng"
            except Exception:
                pass
        data = self.pytesseract.image_to_data(image, output_type=self.pytesseract.Output.DICT, lang=lang)
        best: tuple[float, TextMatch] | None = None
        for index, raw in enumerate(data.get("text", [])):
            text = self._normalize(raw)
            if not text:
                continue
            for prompt in self.prompts:
                target = self._normalize(prompt)
                if not self._is_exact_prompt(text, target):
                    continue
                confidence = float(data["conf"][index]) / 100
                if confidence < 0.75:
                    continue
                left = float(data["left"][index]) / scale_x
                top = float(data["top"][index]) / scale_y
                width = float(data["width"][index]) / scale_x
                height = float(data["height"][index]) / scale_y
                match = TextMatch(prompt, confidence, left + width / 2, top + height / 2)
                score = confidence + (2 if text == target else 0)
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
