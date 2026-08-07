"""macOS 专用识别器：用 Apple Vision 做本地 OCR。

不依赖 tesseract / winsdk / pytesseract，与 Windows 代码完全隔离。
"""

from __future__ import annotations

from typing import Any

from .models import ALLOWED_PROMPTS, TextMatch
from .recognizer_base import BaseRecognizer


class MacOSRecognizer(BaseRecognizer):
    """macOS 用 Apple Vision 识别窗口中的白名单提示词。"""

    def __init__(self, prompts: tuple[str, ...] = ALLOWED_PROMPTS) -> None:
        super().__init__(prompts)
        try:
            import Vision  # type: ignore
        except ImportError:
            Vision = None
        self.vision = Vision
        if self.vision is not None:
            self._engine_ready = True
            self.engine_status = "✓ OCR 引擎就绪（Apple Vision）"
        else:
            self._engine_ready = False
            self.engine_status = "⚠ OCR 引擎未就绪：缺少 Apple Vision 框架"

    def find(self, image: Any) -> TextMatch | None:
        native_image = getattr(image, "native_image", None)
        if native_image is None or self.vision is None:
            return None
        scale_x = getattr(image, "scale_x", 1.0)
        scale_y = getattr(image, "scale_y", 1.0)
        return self._find_with_vision(native_image, scale_x, scale_y)

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
