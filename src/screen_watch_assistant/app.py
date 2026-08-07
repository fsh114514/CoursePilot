from __future__ import annotations

import sys

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, QSettings, Qt, Signal, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from .controller import MonitorController
from .models import ALLOWED_PROMPTS, BLOCKED_PROMPT_WORDS, Window
from .platforms.macos import MacOSAdapter
from .platforms.windows import WindowsAdapter


class LogBus(QObject):
    message = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CoursePilot · 视频播放辅助")
        self.setMinimumSize(700, 680)
        self.resize(820, 900)
        self.adapter = WindowsAdapter() if sys.platform == "win32" else MacOSAdapter()
        self.log_bus = LogBus()
        self.log_bus.message.connect(self.add_log)
        self.controller = MonitorController(self.adapter, self.log_bus.message.emit)
        self.window_map: dict[int, Window] = {}
        self.preview_pixmap: QPixmap | None = None
        self.settings = QSettings("ScreenWatchAssistant", "ScreenWatchAssistant")
        saved = self.settings.value("custom_prompts", [])
        if isinstance(saved, str):
            saved = [saved]
        self.custom_prompts = [str(item) for item in (saved or [])]

        self.window_picker = QComboBox()
        self.refresh_button = QPushButton("刷新窗口")
        self.refresh_button.clicked.connect(self.refresh_windows)
        self.start_button = QPushButton("开始监控")
        self.start_button.setEnabled(False)
        self.start_button.setMinimumHeight(44)
        self.start_button.clicked.connect(self.toggle_monitoring)
        self.status = QLabel("请选择要监控的视频窗口")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setMinimumHeight(38)
        self.screen_permission = QLabel()
        self.control_permission = QLabel()
        self.ocr_engine = QLabel()
        self.ocr_engine.setWordWrap(True)
        self.preview = QLabel("选择窗口后显示预览")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(180)
        self.preview.setStyleSheet("QLabel { background: #181a20; color: #9da3b4; border-radius: 8px; }")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(170)
        self.log.setMaximumHeight(240)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        intro_text = "本地识别指定窗口中的继续观看提示，只点击白名单文字附近的按钮。Windows 版需要先安装 Tesseract 中文语言包。" if sys.platform == "win32" else "本地识别指定窗口中的继续观看提示，只点击白名单文字附近的按钮。台前调度收起的窗口无法提供有效预览，请先把视频窗口放到当前调度组。"
        intro = QLabel(intro_text)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        window_box = QGroupBox("1. 选择视频窗口")
        window_layout = QFormLayout(window_box)
        window_layout.addRow(self.window_picker, self.refresh_button)
        layout.addWidget(window_box)

        preview_box = QGroupBox("窗口预览")
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.addWidget(self.preview)
        layout.addWidget(preview_box)

        prompt_box = QGroupBox("3. 自定义提示词（可选）")
        prompt_layout = QVBoxLayout(prompt_box)
        built_in_prompts = QLabel("程序已经认识这些词（无需添加）：\n" + "、".join(ALLOWED_PROMPTS))
        built_in_prompts.setWordWrap(True)
        built_in_prompts.setContentsMargins(8, 8, 8, 8)
        prompt_layout.addWidget(built_in_prompts)
        prompt_help = QLabel("如果实际按钮使用了其它文字，请在这里添加，例如：继续学习。不要添加提交、交卷、支付、删除等页面操作词。")
        prompt_help.setWordWrap(True)
        prompt_layout.addWidget(prompt_help)
        prompt_row = QFormLayout()
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("例如：继续学习")
        self.add_prompt_button = QPushButton("添加")
        self.add_prompt_button.clicked.connect(self.add_prompt)
        self.prompt_input.returnPressed.connect(self.add_prompt)
        prompt_row.addRow(self.prompt_input, self.add_prompt_button)
        prompt_layout.addLayout(prompt_row)
        self.prompt_list = QListWidget()
        self.prompt_list.setMaximumHeight(100)
        self.delete_prompt_button = QPushButton("删除选中的词")
        self.delete_prompt_button.setEnabled(False)
        self.delete_prompt_button.clicked.connect(self.delete_prompt)
        self.prompt_list.currentRowChanged.connect(
            lambda row: self.delete_prompt_button.setEnabled(row >= 0)
        )
        prompt_layout.addWidget(self.prompt_list)
        prompt_layout.addWidget(self.delete_prompt_button)
        permission_box = QGroupBox("2. 权限")
        permission_layout = QVBoxLayout(permission_box)
        permission_layout.addWidget(self.screen_permission)
        permission_layout.addWidget(self.control_permission)
        permission_layout.addWidget(self.ocr_engine)
        if sys.platform == "darwin":
            self.request_perm_button = QPushButton("请求屏幕录制权限")
            self.request_perm_button.clicked.connect(self.request_permissions)
            permission_layout.addWidget(self.request_perm_button)
            permission_layout.addWidget(QLabel(
                "macOS 请在系统设置 → 隐私与安全性 → 屏幕录制 中允许 CoursePilot（注意：不是允许 Python 或终端）。"
                "授权后需重启本应用才能生效。"
            ))
        else:
            permission_layout.addWidget(QLabel("Windows 通常不需要额外权限。"))
        layout.addWidget(permission_box)

        layout.addWidget(self.start_button)
        layout.addWidget(self.status)
        layout.addWidget(prompt_box)
        layout.addWidget(QLabel("运行日志"))
        layout.addWidget(self.log, stretch=1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self.setCentralWidget(scroll)

        self.window_picker.currentIndexChanged.connect(self.selection_changed)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_permissions)
        self.refresh_timer.start(2000)
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self.sync_monitoring_state)
        self.ui_timer.start(300)
        self.refresh_windows()
        self.refresh_permissions()
        self.reload_prompt_list()
        self.set_monitoring_ui(False)
        geometry = self.settings.value("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def refresh_windows(self) -> None:
        selected_window_id = self.window_picker.currentData()
        try:
            windows = self.adapter.windows()
        except RuntimeError as exc:
            self.add_log(str(exc))
            return
        self.window_map = {window.id: window for window in windows}
        self.window_picker.blockSignals(True)
        self.window_picker.clear()
        self.window_picker.addItem("请选择一个窗口" if windows else "没有可用窗口，请调整台前调度后刷新", None)
        for window in windows:
            self.window_picker.addItem(f"{window.owner} · {window.title}", window.id)
        if selected_window_id in self.window_map:
            self.window_picker.setCurrentIndex(self.window_picker.findData(selected_window_id))
        self.window_picker.blockSignals(False)
        self.selection_changed(self.window_picker.currentIndex())
        self.add_log(f"刷新窗口列表：{len(windows)} 个")

    def request_permissions(self) -> None:
        """主动弹出 macOS 屏幕录制授权框。"""
        if hasattr(self.adapter, "request_screen_permission"):
            self.adapter.request_screen_permission()
            self.add_log("已请求屏幕录制权限，请在系统弹窗中允许 CoursePilot，授权后重启应用。")

    def refresh_permissions(self) -> None:
        screen, control = self.adapter.permissions()
        self.screen_permission.setText(("✓ " if screen else "⚠ ") + ("屏幕录制权限已允许" if screen else "需要屏幕录制权限"))
        self.control_permission.setText(("✓ " if control else "⚠ ") + ("辅助功能权限已允许" if control else "需要辅助功能权限"))
        # 权限从无到有时提示重启（macOS TCC 在进程启动时加载权限）
        if sys.platform == "darwin" and screen and not getattr(self, "_prev_screen", False):
            self.add_log("检测到屏幕录制权限已允许，请重启本应用以完全生效。")
        self._prev_screen = screen
        self.refresh_ocr_status()
        running = self.start_button.text() == "停止监控"
        self.start_button.setEnabled(running or (bool(self.window_picker.currentData()) and screen and control and self.controller.ocr_ready))

    def refresh_ocr_status(self) -> None:
        self.ocr_engine.setText(self.controller.ocr_status)
        if not self.controller.ocr_ready and sys.platform == "win32":
            self.ocr_engine.setStyleSheet("color: #e6a23c;")
        else:
            self.ocr_engine.setStyleSheet("")

    def selection_changed(self, index: int) -> None:
        self.refresh_permissions()
        self.update_preview()

    def update_preview(self) -> None:
        window = self.window_map.get(self.window_picker.currentData())
        if window is None:
            self.preview_pixmap = None
            self.preview.clear()
            self.preview.setText("选择窗口后显示预览")
            return
        self.preview_pixmap = None
        self.preview.clear()
        self.preview.setText("正在生成预览…")
        QApplication.processEvents()
        try:
            frame = self.adapter.capture(window)
        except Exception as exc:
            self.preview_pixmap = None
            self.preview.clear()
            self.preview.setText("预览失败，请刷新后重试")
            self.add_log(f"预览错误：{exc}")
            return
        if frame is None:
            self.preview_pixmap = None
            self.preview.clear()
            self.preview.setText("暂时无法预览，请把窗口放回当前台前调度组")
            return
        self.preview_pixmap = QPixmap.fromImage(ImageQt(frame.pil_image.convert("RGB")))
        self.render_preview()

    def render_preview(self) -> None:
        if self.preview_pixmap is None:
            return
        self.preview.setPixmap(self.preview_pixmap.scaled(
            self.preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.render_preview()

    def toggle_monitoring(self) -> None:
        if self.start_button.text() == "停止监控":
            self.controller.stop()
            self.set_monitoring_ui(False)
            return
        window = self.window_map.get(self.window_picker.currentData())
        if window is None:
            return
        self.controller.start(window)
        self.set_monitoring_ui(True, window)

    def all_prompts(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*ALLOWED_PROMPTS, *self.custom_prompts)))

    def reload_prompt_list(self) -> None:
        self.prompt_list.clear()
        for prompt in self.custom_prompts:
            self.prompt_list.addItem(prompt)
        has_custom_prompts = bool(self.custom_prompts)
        self.prompt_list.setFixedHeight(min(100, 28 * len(self.custom_prompts) + 4))
        self.prompt_list.setVisible(has_custom_prompts)
        self.delete_prompt_button.setVisible(has_custom_prompts)
        self.delete_prompt_button.setEnabled(False)
        self.controller.set_prompts(self.all_prompts())

    def add_prompt(self) -> None:
        prompt = " ".join(self.prompt_input.text().split()).strip()
        normalized = prompt.lower().replace(" ", "")
        if len(prompt) < 2 or len(prompt) > 30:
            QMessageBox.information(self, "提示词不合适", "请输入 2 到 30 个字，并填写按钮上真实显示的文字。")
            return
        if any(word.lower().replace(" ", "") in normalized for word in BLOCKED_PROMPT_WORDS):
            QMessageBox.warning(self, "不能添加这个词", "请只添加“继续观看”类按钮文字，不要添加提交、支付、删除等操作词。")
            return
        if normalized in {item.lower().replace(" ", "") for item in ALLOWED_PROMPTS}:
            QMessageBox.information(self, "程序已经认识这个词", "这个词已经是程序自带提示词，无需重复添加。")
            return
        if normalized in {item.lower().replace(" ", "") for item in self.custom_prompts}:
            QMessageBox.information(self, "已经添加过了", "这个提示词已经在识别列表中。")
            return
        self.custom_prompts.append(prompt)
        self.settings.setValue("custom_prompts", self.custom_prompts)
        self.prompt_input.clear()
        self.reload_prompt_list()
        self.add_log(f"已添加自定义提示词：{prompt}")

    def delete_prompt(self) -> None:
        row = self.prompt_list.currentRow()
        if row < 0:
            return
        prompt = self.custom_prompts.pop(row)
        self.settings.setValue("custom_prompts", self.custom_prompts)
        self.reload_prompt_list()
        self.add_log(f"已删除自定义提示词：{prompt}")

    def set_monitoring_ui(self, running: bool, window: Window | None = None) -> None:
        self.window_picker.setEnabled(not running)
        self.refresh_button.setEnabled(not running)
        if running:
            self.start_button.setText("停止监控")
            self.start_button.setStyleSheet("QPushButton { background: #c9353b; color: white; font-weight: 600; }")
            self.status.setText(f"● 正在监视：{window.owner} · {window.title}" if window else "● 正在监视")
            self.status.setStyleSheet("QLabel { background: #173c2b; color: #71e6a1; border-radius: 8px; font-weight: 600; }")
        else:
            self.start_button.setText("开始监控")
            self.start_button.setStyleSheet("")
            self.status.setText("○ 已停止监控")
            self.status.setStyleSheet("QLabel { background: #2c2f38; color: #c7cad3; border-radius: 8px; }")
            self.refresh_permissions()

    def sync_monitoring_state(self) -> None:
        if self.start_button.text() == "停止监控" and not self.controller.is_running:
            self.set_monitoring_ui(False)

    def add_log(self, message: str) -> None:
        self.log.insertPlainText(message + "\n")
        self.log.ensureCursorVisible()

    def closeEvent(self, event) -> None:
        self.settings.setValue("window_geometry", self.saveGeometry())
        self.controller.stop()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
