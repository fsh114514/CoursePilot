from __future__ import annotations

import threading
import time
from collections.abc import Callable

from .models import ALLOWED_PROMPTS, TextMatch, Window
from .platforms.base import PlatformAdapter
from .recognizer_base import BaseRecognizer


class MonitorController:
    def __init__(
        self,
        adapter: PlatformAdapter,
        on_log: Callable[[str], None],
        recognizer_cls: type[BaseRecognizer],
    ) -> None:
        self.adapter = adapter
        self.on_log = on_log
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.ocr_error: str | None = None
        try:
            self.recognizer = recognizer_cls(ALLOWED_PROMPTS)
        except RuntimeError as exc:
            self.recognizer = None
            self.ocr_error = str(exc)

    @property
    def ocr_ready(self) -> bool:
        return bool(self.recognizer is not None and self.recognizer._engine_ready)

    @property
    def ocr_status(self) -> str:
        if self.recognizer is not None:
            return self.recognizer.engine_status
        return f"⚠ OCR 引擎未就绪：{self.ocr_error or '初始化失败'}"

    def start(self, window: Window) -> None:
        if self._thread and self._thread.is_alive():
            return
        if self.recognizer is None or not self.recognizer._engine_ready:
            self.on_log(self.ocr_status)
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(window,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def set_prompts(self, prompts: tuple[str, ...]) -> None:
        if self.recognizer is not None:
            self.recognizer.prompts = prompts

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def _run(self, window: Window) -> None:
        self.on_log(f"开始监控：{window.owner} · {window.title}")
        scan_count = 0
        unavailable_count = 0
        failed_clicks = 0
        while not self._stop.is_set():
            try:
                image = self.adapter.capture(window)
                if image is None:
                    unavailable_count += 1
                    if unavailable_count == 3:
                        self.on_log("暂时看不到目标窗口，请把它放回当前台前调度组")
                    self._stop.wait(1.0)
                    continue
                if unavailable_count >= 3:
                    self.on_log("目标窗口已恢复，继续监控")
                unavailable_count = 0
                match = self.recognizer.find(image)
                scan_count += 1
                if scan_count == 1 or scan_count % 10 == 0:
                    self.on_log(f"已扫描 {scan_count} 次" + ("，未发现提示" if match is None else ""))
                if match and self._confirmed(window, match):
                    self.on_log(f"识别到白名单提示：{match.text}（{match.confidence:.0%}），执行一次点击")
                    self.adapter.click(window, match.center_x, match.center_y)
                    time.sleep(1.5)  # 等待弹窗关闭动画完成
                    verification = self.adapter.capture(window)
                    if verification is not None and self.recognizer.find(verification):
                        # 提示仍存在：可能点击未生效或弹窗动画未完成。
                        # 不立即停止——避免误停。连续多次点击无效才停止。
                        failed_clicks += 1
                        self.on_log(f"点击后提示仍在（第 {failed_clicks} 次）")
                        if failed_clicks >= 5:
                            self.on_log("连续多次点击无效，自动停止以避免重复操作")
                            self.stop()
                            return
                        continue
                    failed_clicks = 0
                    self.on_log("点击成功：提示已消失")
            except Exception as exc:
                self.on_log(f"监控已停止：{exc}")
                self.stop()
                return
            self._stop.wait(1.0)
        self.on_log("监控已停止")

    def _confirmed(self, window: Window, first: TextMatch) -> bool:
        time.sleep(0.15)
        image = self.adapter.capture(window)
        second = self.recognizer.find(image) if image is not None else None
        return bool(second and second.text == first.text)
