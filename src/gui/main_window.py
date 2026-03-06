from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPoint, Property, QPropertyAnimation, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QProgressBar,
    QListView,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import AudioProcess, OutputFormat, RecorderRequest, RecorderState, SaveMode
from core.process_service import ProcessService
from core.recorder_controller import RecorderController
from core.settings import AppSettings, SettingsManager
from core.updater import GitHubReleaseUpdater, ReleaseInfo, UpdateCheckResult, UpdateError
from core.version import APP_NAME

_DEFAULT_EFFECTS_ENABLED = sys.platform != "win32"
ENABLE_VISUAL_EFFECTS = os.environ.get(
    "PID_RECORDER_ENABLE_EFFECTS",
    "1" if _DEFAULT_EFFECTS_ENABLED else "0",
) == "1"


class UpdateCheckThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, updater: GitHubReleaseUpdater, current_version: str) -> None:
        super().__init__()
        self._updater = updater
        self._current_version = current_version

    def run(self) -> None:
        try:
            result = self._updater.check_for_updates(self._current_version)
        except UpdateError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # pragma: no cover
            self.failed.emit(f"检查更新失败: {exc}")
            return
        self.succeeded.emit(result)


class UpdateDownloadThread(QThread):
    progress_changed = Signal(int, int)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, updater: GitHubReleaseUpdater, release: ReleaseInfo) -> None:
        super().__init__()
        self._updater = updater
        self._release = release
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            installer_path = self._updater.download_installer(
                self._release,
                progress_callback=self._emit_progress,
                cancelled=self._is_cancelled,
            )
        except UpdateError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # pragma: no cover
            self.failed.emit(f"下载更新失败: {exc}")
            return
        self.succeeded.emit(installer_path)

    def _emit_progress(self, downloaded: int, total: int) -> None:
        self.progress_changed.emit(downloaded, total)

    def _is_cancelled(self) -> bool:
        return self._cancelled


class TrafficButton(QPushButton):
    def __init__(self, color: str, symbol: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._symbol = symbol
        self._color = color
        self._base_size = 13
        self._hover_scale = 1.0
        self._hover_animation = QPropertyAnimation(self, b"hoverScale", self)
        self._hover_animation.setDuration(140)
        self._hover_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.setFixedSize(self._base_size, self._base_size)
        self.setCursor(Qt.PointingHandCursor)
        self.setText("")
        self._apply_style(self._base_size)

    def _get_hover_scale(self) -> float:
        return self._hover_scale

    def _set_hover_scale(self, value: float) -> None:
        self._hover_scale = value
        size = max(self._base_size, int(round(self._base_size * value)))
        self.setFixedSize(size, size)
        self._apply_style(size)

    hoverScale = Property(float, _get_hover_scale, _set_hover_scale)

    def _animate_hover_scale(self, target: float) -> None:
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover_scale)
        self._hover_animation.setEndValue(target)
        self._hover_animation.start()

    def enterEvent(self, event):  # type: ignore[override]
        self._animate_hover_scale(1.15)
        super().enterEvent(event)

    def leaveEvent(self, event):  # type: ignore[override]
        self._animate_hover_scale(1.0)
        super().leaveEvent(event)

    def _apply_style(self, size: int) -> None:
        radius = max(1, size // 2)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {self._color};
                border: 1px solid rgba(0, 0, 0, 0.22);
                border-radius: {radius}px;
                padding: 0;
                margin: 0;
                min-width: 0px;
                min-height: 0px;
                color: transparent;
            }}
            QPushButton:hover {{
                border: 1px solid rgba(0, 0, 0, 0.32);
            }}
            QPushButton:pressed {{
                border: 1px solid rgba(0, 0, 0, 0.38);
            }}
            """
        )


class MacTitleBar(QWidget):
    def __init__(self, window: QMainWindow, app_version: str) -> None:
        super().__init__(window)
        self.setObjectName("TitleBar")
        self._window = window
        self._drag_pos: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 14, 9)
        layout.setSpacing(8)

        self.btn_close = TrafficButton("#ff5f57", "x", self)
        self.btn_min = TrafficButton("#ffbd2e", "-", self)
        self.btn_max = TrafficButton("#28c840", "+", self)
        self.btn_close.clicked.connect(window.close)
        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_max.clicked.connect(self._toggle_maximize)

        title_box = QWidget(self)
        title_box.setObjectName("TitleBox")
        title_layout = QVBoxLayout(title_box)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)
        title = QLabel(APP_NAME, title_box)
        title.setObjectName("TitleLabel")
        subtitle = QLabel(f"进程回环采集 · v{app_version}", title_box)
        subtitle.setObjectName("SubtitleLabel")
        title_layout.addWidget(title, alignment=Qt.AlignCenter)
        title_layout.addWidget(subtitle, alignment=Qt.AlignCenter)

        self.update_button = QPushButton("检查更新", self)
        self.update_button.setObjectName("TitleActionButton")
        self.update_button.setCursor(Qt.PointingHandCursor)
        self.update_button.setAutoDefault(False)

        self.state_chip = QLabel("就绪", self)
        self.state_chip.setObjectName("StatusChip")

        layout.addWidget(self.btn_close)
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addSpacing(8)
        layout.addStretch()
        layout.addWidget(title_box)
        layout.addStretch()
        layout.addWidget(self.update_button)
        layout.addWidget(self.state_chip)

    def set_chip_text(self, text: str) -> None:
        self.state_chip.setText(text)

    def mousePressEvent(self, event):  # type: ignore[override]
        if event.button() == Qt.LeftButton and not self._window.isMaximized():
            self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):  # type: ignore[override]
        if self._drag_pos is None:
            return
        if event.buttons() & Qt.LeftButton and not self._window.isMaximized():
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        self._drag_pos = None
        event.accept()

    def mouseDoubleClickEvent(self, event):  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()
        event.accept()

    def _toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()


class RecordingBadge(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.dot = QFrame(self)
        self.dot.setFixedSize(10, 10)
        self.dot.setStyleSheet("border-radius: 5px; background: #b9c2d3;")

        self.text = QLabel("未录制", self)
        self.text.setStyleSheet("font-size: 12px; color: #6f7889;")

        self.opacity_effect: QGraphicsOpacityEffect | None = None
        self.pulse: QPropertyAnimation | None = None
        if ENABLE_VISUAL_EFFECTS:
            self.opacity_effect = QGraphicsOpacityEffect(self.dot)
            self.dot.setGraphicsEffect(self.opacity_effect)
            self.pulse = QPropertyAnimation(self.opacity_effect, b"opacity", self)
            self.pulse.setStartValue(1.0)
            self.pulse.setEndValue(0.25)
            self.pulse.setDuration(900)
            self.pulse.setLoopCount(-1)
            self.pulse.setEasingCurve(QEasingCurve.InOutSine)

        layout.addWidget(self.dot)
        layout.addWidget(self.text)
        layout.addStretch()

    def set_state(self, state: RecorderState) -> None:
        if state == RecorderState.RECORDING:
            self.dot.setStyleSheet("border-radius: 5px; background: #ff5f57;")
            self.text.setText("录制中")
            self.text.setStyleSheet("font-size: 12px; color: #db4d47; font-weight: 600;")
            if self.pulse and self.pulse.state() != QAbstractAnimation.Running:
                self.pulse.start()
            return

        if state == RecorderState.PAUSED:
            self.dot.setStyleSheet("border-radius: 5px; background: #ffbd2e;")
            self.text.setText("已暂停")
            self.text.setStyleSheet("font-size: 12px; color: #9f7e24; font-weight: 600;")
            if self.pulse:
                self.pulse.stop()
            if self.opacity_effect:
                self.opacity_effect.setOpacity(1.0)
            return

        self.dot.setStyleSheet("border-radius: 5px; background: #b9c2d3;")
        self.text.setText("未录制")
        self.text.setStyleSheet("font-size: 12px; color: #6f7889;")
        if self.pulse:
            self.pulse.stop()
        if self.opacity_effect:
            self.opacity_effect.setOpacity(1.0)


class MainWindow(QMainWindow):
    def __init__(
        self,
        process_service: ProcessService,
        controller: RecorderController,
        settings_manager: SettingsManager,
        settings: AppSettings,
        updater: GitHubReleaseUpdater,
        app_version: str,
    ) -> None:
        super().__init__()
        self.process_service = process_service
        self.controller = controller
        self.settings_manager = settings_manager
        self.settings = settings
        self.updater = updater
        self.app_version = app_version
        self._selected_process: AudioProcess | None = None
        self._supported = self.controller.is_supported()
        self._did_fade_in = False
        self._did_schedule_update_check = False
        self.fade_effect: QGraphicsOpacityEffect | None = None
        self.fade_animation: QPropertyAnimation | None = None
        self._update_check_thread: UpdateCheckThread | None = None
        self._download_thread: UpdateDownloadThread | None = None
        self._download_dialog: QProgressDialog | None = None

        self.setWindowTitle(f"{APP_NAME} v{self.app_version}")
        self.resize(settings.window_width, settings.window_height)
        self.setMinimumSize(980, 650)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._build_ui()
        self._bind_signals()
        self.refresh_processes()
        self._apply_state(self.controller.state)

        if not self._supported:
            self.start_button.setEnabled(False)
            self._set_status("当前系统不支持按 PID 录音（需要 Windows 10 2004+）。")

    def _build_ui(self) -> None:
        outer = QWidget(self)
        outer.setObjectName("OuterShell")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        self.setCentralWidget(outer)

        root = QWidget(outer)
        root.setObjectName("RootContainer")
        outer_layout.addWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.root_container = root

        self._apply_shadow(root, blur=28, alpha=58, offset_y=5)

        self.title_bar = MacTitleBar(self, self.app_version)
        root_layout.addWidget(self.title_bar)

        content = QWidget(root)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 12)
        content_layout.setSpacing(14)
        root_layout.addWidget(content, 1)

        left_card = QFrame(content)
        left_card.setObjectName("PanelCard")
        self._apply_shadow(left_card, blur=20, alpha=38, offset_y=2)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(13, 13, 13, 13)
        left_layout.setSpacing(10)

        left_header = QHBoxLayout()
        left_title = QLabel("可录制进程", left_card)
        left_title.setObjectName("SectionTitle")
        self.refresh_button = QPushButton("刷新", left_card)
        self.search_input = QLineEdit(left_card)
        self.search_input.setPlaceholderText("搜索进程名 / 窗口名 / PID")
        left_header.addWidget(left_title)
        left_header.addStretch()
        left_header.addWidget(self.refresh_button)

        self.process_table = QTableWidget(left_card)
        self.process_table.setObjectName("ProcessTable")
        self.process_table.setColumnCount(3)
        self.process_table.setHorizontalHeaderLabels(["PID", "进程", "窗口标题"])
        self.process_table.verticalHeader().setVisible(False)
        self.process_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.process_table.setSelectionMode(QTableWidget.SingleSelection)
        self.process_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.process_table.setAlternatingRowColors(True)
        self.process_table.setShowGrid(False)
        self.process_table.setWordWrap(False)
        self.process_table.verticalHeader().setDefaultSectionSize(28)
        header = self.process_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)

        manual_label = QLabel("手动输入 PID（优先）", left_card)
        manual_label.setStyleSheet("font-size: 12px; color: #657083;")
        self.manual_pid_input = QLineEdit(left_card)
        self.manual_pid_input.setPlaceholderText("例如：12345")
        self.manual_pid_input.setValidator(QIntValidator(1, 2_147_483_647, self))

        left_layout.addLayout(left_header)
        left_layout.addWidget(self.search_input)
        left_layout.addWidget(self.process_table, 1)
        left_layout.addWidget(manual_label)
        left_layout.addWidget(self.manual_pid_input)

        right_card = QFrame(content)
        right_card.setObjectName("PanelCard")
        self._apply_shadow(right_card, blur=20, alpha=34, offset_y=2)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(12)

        info_title = QLabel("录制控制", right_card)
        info_title.setObjectName("SectionTitle")
        self.record_badge = RecordingBadge(right_card)
        self.target_label = QLabel("目标进程：未选择", right_card)
        self.target_label.setStyleSheet("font-size: 13px; color: #5f6a7c;")

        elapsed_title = QLabel("录制时长", right_card)
        elapsed_title.setStyleSheet("font-size: 12px; color: #687488;")
        self.elapsed_label = QLabel("00:00", right_card)
        self.elapsed_label.setStyleSheet("font-size: 40px; font-weight: 700; letter-spacing: 1px; color: #253044;")
        self.elapsed_label.setAlignment(Qt.AlignCenter)

        vu_title = QLabel("实时电平", right_card)
        vu_title.setStyleSheet("font-size: 12px; color: #687488;")
        self.level_bar = QProgressBar(right_card)
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        self.level_bar.setTextVisible(False)

        output_title = QLabel("输出目录", right_card)
        output_title.setStyleSheet("font-size: 12px; color: #687488;")
        output_row = QHBoxLayout()
        self.output_dir_input = QLineEdit(right_card)
        self.output_dir_input.setText(self.settings.output_dir)
        self.browse_button = QPushButton("选择目录", right_card)
        output_row.addWidget(self.output_dir_input, 1)
        output_row.addWidget(self.browse_button)

        format_title = QLabel("保存格式", right_card)
        format_title.setObjectName("SettingLabel")
        self.format_combo = QComboBox(right_card)
        self.format_combo.setObjectName("FormatCombo")
        self.format_combo.setToolTip("选择录音输出文件格式")
        self._configure_setting_combo(self.format_combo)
        self.format_combo.addItem("MP3", OutputFormat.MP3.value)
        self.format_combo.addItem("WAV", OutputFormat.WAV.value)
        self._set_combo_value(self.format_combo, self.settings.output_format, OutputFormat.MP3.value)

        save_mode_title = QLabel("保存方式", right_card)
        save_mode_title.setObjectName("SettingLabel")
        self.save_mode_combo = QComboBox(right_card)
        self.save_mode_combo.setObjectName("SaveModeCombo")
        self.save_mode_combo.setToolTip("选择停止后导出，或录制时实时写入文件")
        self._configure_setting_combo(self.save_mode_combo)
        self.save_mode_combo.addItem("停止后一次性保存", SaveMode.DEFERRED.value)
        self.save_mode_combo.addItem("实时保存（边录边写）", SaveMode.REALTIME.value)
        self._set_combo_value(self.save_mode_combo, self.settings.save_mode, SaveMode.DEFERRED.value)
        self._apply_save_mode_ui()

        action_row = QHBoxLayout()
        self.start_button = QPushButton("开始录音", right_card)
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setToolTip("开始录制所选进程音频")
        self.start_button.setShortcut("Ctrl+R")
        self.stop_button = QPushButton("停止", right_card)
        self.stop_button.setObjectName("StopButton")
        self.stop_button.setToolTip("停止录制并保存文件")
        self.stop_button.setShortcut("Ctrl+S")
        self.pause_button = QPushButton("暂停", right_card)
        self.pause_button.setObjectName("PauseButton")
        self.pause_button.setProperty("paused", False)
        self.pause_button.setToolTip("暂停或继续当前录制")
        self.pause_button.setShortcut("Ctrl+P")
        for button in (self.start_button, self.pause_button, self.stop_button):
            button.setCursor(Qt.PointingHandCursor)
            button.setAutoDefault(False)
        action_row.addWidget(self.start_button, 1)
        action_row.addWidget(self.pause_button)
        action_row.addWidget(self.stop_button)

        right_layout.addWidget(info_title)
        right_layout.addWidget(self.record_badge)
        right_layout.addWidget(self.target_label)
        right_layout.addSpacing(4)
        right_layout.addWidget(elapsed_title)
        right_layout.addWidget(self.elapsed_label)
        right_layout.addWidget(vu_title)
        right_layout.addWidget(self.level_bar)
        right_layout.addSpacing(6)
        right_layout.addWidget(output_title)
        right_layout.addLayout(output_row)
        right_layout.addWidget(format_title)
        right_layout.addWidget(self.format_combo)
        right_layout.addWidget(save_mode_title)
        right_layout.addWidget(self.save_mode_combo)
        right_layout.addStretch()
        right_layout.addLayout(action_row)

        content_layout.addWidget(left_card, 7)
        content_layout.addWidget(right_card, 5)

        self.status_label = QLabel("准备就绪", root)
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root_layout.addWidget(self.status_label)

        if ENABLE_VISUAL_EFFECTS:
            self.fade_effect = QGraphicsOpacityEffect(self.root_container)
            self.root_container.setGraphicsEffect(self.fade_effect)
            self.fade_animation = QPropertyAnimation(self.fade_effect, b"opacity", self)
            self.fade_animation.setStartValue(0.0)
            self.fade_animation.setEndValue(1.0)
            self.fade_animation.setDuration(320)
            self.fade_animation.setEasingCurve(QEasingCurve.OutCubic)

    def _bind_signals(self) -> None:
        self.refresh_button.clicked.connect(self.refresh_processes)
        self.search_input.textChanged.connect(self.refresh_processes)
        self.process_table.itemSelectionChanged.connect(self._on_select_process)
        self.manual_pid_input.textChanged.connect(self._on_manual_pid_change)

        self.browse_button.clicked.connect(self._select_output_dir)
        self.start_button.clicked.connect(self._start_recording)
        self.stop_button.clicked.connect(self._stop_recording)
        self.pause_button.clicked.connect(self.controller.toggle_pause_resume)
        self.save_mode_combo.currentIndexChanged.connect(lambda _: self._on_save_mode_changed())
        self.format_combo.currentIndexChanged.connect(lambda _: self._on_format_changed())
        self.title_bar.update_button.clicked.connect(self._check_for_updates_manually)

        self.controller.state_changed.connect(self._on_state_changed)
        self.controller.level_changed.connect(self._on_level_changed)
        self.controller.elapsed_changed.connect(self._on_elapsed_changed)
        self.controller.finished.connect(self._on_finished)
        self.controller.failed.connect(self._on_failed)

    def showEvent(self, event):  # type: ignore[override]
        super().showEvent(event)
        if self.fade_animation and not self._did_fade_in:
            self._did_fade_in = True
            self.fade_animation.start()
        if not self._did_schedule_update_check:
            self._did_schedule_update_check = True
            QTimer.singleShot(1200, self._check_for_updates_on_startup)

    def refresh_processes(self) -> None:
        selected_pid = self._selected_process.pid if self._selected_process else None

        try:
            processes = self.process_service.list_audio_processes(self.search_input.text())
        except Exception as exc:
            self._set_status(f"刷新进程失败: {exc}")
            return

        restore_row = -1
        self.process_table.setRowCount(len(processes))
        for row, item in enumerate(processes):
            pid_item = QTableWidgetItem(str(item.pid))
            name_item = QTableWidgetItem(item.name)
            title_item = QTableWidgetItem(item.window_title or "-")
            pid_item.setData(Qt.UserRole, item)
            self.process_table.setItem(row, 0, pid_item)
            self.process_table.setItem(row, 1, name_item)
            self.process_table.setItem(row, 2, title_item)
            if selected_pid is not None and item.pid == selected_pid:
                restore_row = row

        if restore_row >= 0:
            self.process_table.setCurrentCell(restore_row, 0)
            self.process_table.selectRow(restore_row)
        elif not self.manual_pid_input.text().strip():
            self._selected_process = None
            self.target_label.setText("目标进程：未选择")

        self._set_status(f"已加载 {len(processes)} 个可录制进程")

    def _on_select_process(self) -> None:
        row = self.process_table.currentRow()
        if row < 0:
            self._selected_process = None
            self.target_label.setText("目标进程：未选择")
            return

        item = self.process_table.item(row, 0)
        process = item.data(Qt.UserRole) if item else None
        if isinstance(process, AudioProcess):
            self._selected_process = process
            self.target_label.setText(f"目标进程：{process.name} ({process.pid})")

    def _on_manual_pid_change(self, text: str) -> None:
        if not text.strip():
            if self._selected_process:
                self.target_label.setText(
                    f"目标进程：{self._selected_process.name} ({self._selected_process.pid})"
                )
            else:
                self.target_label.setText("目标进程：未选择")
            return
        self.target_label.setText(f"目标进程：手动 PID {text.strip()}")

    def _select_output_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_dir_input.text().strip())
        if selected:
            self.output_dir_input.setText(selected)

    def _resolve_target(self) -> tuple[int, str] | None:
        manual_text = self.manual_pid_input.text().strip()
        if manual_text:
            try:
                pid = self.process_service.parse_pid(manual_text)
            except ValueError as exc:
                self._set_status(str(exc))
                return None

            resolved = self.process_service.resolve_capture_target(pid)
            if not resolved.ok or not resolved.capture_pid:
                self._set_status(resolved.message or "PID 无效")
                return None

            if resolved.hint:
                self._set_status(resolved.hint)

            return resolved.capture_pid, resolved.process_name

        if self._selected_process:
            return self._selected_process.pid, self._selected_process.name

        self._set_status("请先选择进程或手动输入 PID。")
        return None

    def _start_recording(self) -> None:
        if not self._supported:
            self._set_status("当前系统不支持按 PID 录音。")
            return

        target = self._resolve_target()
        if not target:
            return

        output_dir_text = self.output_dir_input.text().strip()
        if not output_dir_text:
            self._set_status("请选择输出目录。")
            return
        output_dir = Path(output_dir_text)

        pid, process_name = target
        output_format = self.format_combo.currentData()
        if output_format not in {OutputFormat.MP3.value, OutputFormat.WAV.value}:
            output_format = OutputFormat.MP3.value

        save_mode = self.save_mode_combo.currentData()
        if save_mode not in {SaveMode.DEFERRED.value, SaveMode.REALTIME.value}:
            save_mode = SaveMode.DEFERRED.value

        request = RecorderRequest(
            pid=pid,
            process_name=process_name,
            output_dir=output_dir,
            output_format=OutputFormat(output_format),
            save_mode=SaveMode(save_mode),
        )
        self.controller.start_recording(request)

        self.settings.output_dir = str(output_dir)
        self.settings.output_format = request.output_format.value
        self.settings.save_mode = request.save_mode.value
        self.settings_manager.save(self.settings)

    def _on_save_mode_changed(self) -> None:
        self._apply_save_mode_ui()

    def _on_format_changed(self) -> None:
        output_format = self.format_combo.currentData()
        if output_format in {OutputFormat.MP3.value, OutputFormat.WAV.value}:
            self.settings.output_format = output_format

    def _check_for_updates_on_startup(self) -> None:
        self._start_update_check(manual=False)

    def _check_for_updates_manually(self) -> None:
        self._start_update_check(manual=True)

    def _start_update_check(self, manual: bool) -> None:
        if not self.updater.is_supported():
            if manual:
                QMessageBox.information(self, "检查更新", "开发模式不检查更新，请使用打包后的安装版。")
            return

        if self._update_check_thread and self._update_check_thread.isRunning():
            if manual:
                self._set_status("正在检查更新，请稍候。")
            return

        self._set_update_button_busy(True, "检查中")
        self._set_status("正在检查更新...")

        thread = UpdateCheckThread(self.updater, self.app_version)
        self._update_check_thread = thread
        thread.succeeded.connect(lambda result, is_manual=manual: self._on_update_check_succeeded(result, is_manual))
        thread.failed.connect(lambda message, is_manual=manual: self._on_update_check_failed(message, is_manual))
        thread.finished.connect(self._on_update_check_finished)
        thread.start()

    def _on_update_check_succeeded(self, result: UpdateCheckResult, manual: bool) -> None:
        if not result.update_available or result.release is None:
            self._set_status("当前已是最新版本。")
            if manual:
                QMessageBox.information(
                    self,
                    "检查更新",
                    f"当前版本 v{result.current_version} 已是最新版本。",
                )
            return

        release = result.release
        message = (
            f"当前版本: v{result.current_version}\n"
            f"最新版本: v{result.latest_version}\n\n"
            f"版本标题: {release.title}\n\n"
            f"{self._build_release_notes_text(release.notes)}\n\n"
            "是否立即下载并安装更新？"
        )
        answer = QMessageBox.question(self, "发现新版本", message, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer == QMessageBox.Yes:
            self._start_update_download(release)
        else:
            self._set_status("已取消更新。")

    def _on_update_check_failed(self, message: str, manual: bool) -> None:
        self._set_status(message)
        if manual:
            QMessageBox.warning(self, "检查更新失败", message)

    def _on_update_check_finished(self) -> None:
        self._set_update_button_busy(False, "检查更新")
        self._update_check_thread = None

    def _start_update_download(self, release: ReleaseInfo) -> None:
        if self._download_thread and self._download_thread.isRunning():
            self._set_status("正在下载更新，请稍候。")
            return

        dialog = QProgressDialog("正在下载更新安装包...", "取消", 0, 0, self)
        dialog.setWindowTitle("下载更新")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.canceled.connect(self._cancel_update_download)
        self._download_dialog = dialog

        thread = UpdateDownloadThread(self.updater, release)
        self._download_thread = thread
        thread.progress_changed.connect(self._on_update_download_progress)
        thread.succeeded.connect(self._on_update_download_succeeded)
        thread.failed.connect(self._on_update_download_failed)
        thread.finished.connect(self._on_update_download_finished)

        dialog.show()
        self._set_status(f"正在下载更新：v{release.version}")
        thread.start()

    def _cancel_update_download(self) -> None:
        if self._download_thread and self._download_thread.isRunning():
            self._download_thread.cancel()

    def _on_update_download_progress(self, downloaded: int, total: int) -> None:
        dialog = self._download_dialog
        if dialog is None:
            return

        if total > 0:
            if dialog.maximum() == 0:
                dialog.setRange(0, total)
            dialog.setValue(downloaded)
            dialog.setLabelText(f"正在下载更新安装包... {downloaded // 1024} / {total // 1024} KB")
        else:
            dialog.setLabelText(f"正在下载更新安装包... 已下载 {downloaded // 1024} KB")

    def _on_update_download_succeeded(self, installer_path: Path) -> None:
        self._set_status(f"更新下载完成：{installer_path.name}")
        QMessageBox.information(self, "更新已下载", "安装包下载完成，程序将关闭并启动更新安装器。")
        self._launch_installer(installer_path)

    def _on_update_download_failed(self, message: str) -> None:
        self._set_status(message)
        if message != "已取消下载。":
            QMessageBox.warning(self, "下载更新失败", message)

    def _on_update_download_finished(self) -> None:
        if self._download_dialog is not None:
            self._download_dialog.close()
            self._download_dialog.deleteLater()
            self._download_dialog = None
        self._download_thread = None

    def _launch_installer(self, installer_path: Path) -> None:
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(installer_path))  # type: ignore[attr-defined]
            else:  # pragma: no cover
                subprocess.Popen([str(installer_path)])
        except OSError as exc:
            QMessageBox.warning(self, "启动安装器失败", f"无法启动安装器: {exc}")
            return

        QApplication.instance().quit()

    @staticmethod
    def _build_release_notes_text(notes: str) -> str:
        cleaned = notes.strip()
        if not cleaned:
            return "该版本未提供更新说明。"

        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        preview = "\n".join(lines[:6])
        if len(lines) > 6:
            preview += "\n..."
        return preview

    def _stop_recording(self) -> None:
        self.controller.stop_recording("已手动停止录音。")

    def _on_state_changed(self, state: RecorderState, message: str) -> None:
        self._apply_state(state)
        self._set_status(message)

    def _on_level_changed(self, level: float) -> None:
        self.level_bar.setValue(int(max(0.0, min(1.0, level)) * 100))

    def _on_elapsed_changed(self, seconds: int) -> None:
        mm, ss = divmod(seconds, 60)
        hh, mm = divmod(mm, 60)
        if hh:
            self.elapsed_label.setText(f"{hh:02d}:{mm:02d}:{ss:02d}")
        else:
            self.elapsed_label.setText(f"{mm:02d}:{ss:02d}")

    def _on_finished(self, output_path: Path) -> None:
        self._set_status(f"录音完成：{output_path}")

    def _on_failed(self, message: str) -> None:
        self._set_status(message)
        QMessageBox.warning(self, "录音失败", message)

    def _apply_state(self, state: RecorderState) -> None:
        start_ready = self._supported and state in {
            RecorderState.IDLE,
            RecorderState.COMPLETED,
            RecorderState.ERROR,
        }
        stop_ready = state in {RecorderState.STARTING, RecorderState.RECORDING, RecorderState.PAUSED}
        pause_ready = state in {RecorderState.RECORDING, RecorderState.PAUSED}

        self.start_button.setEnabled(start_ready)
        self.stop_button.setEnabled(stop_ready)
        self.pause_button.setEnabled(pause_ready)
        pause_is_resume = state == RecorderState.PAUSED
        self.pause_button.setText("继续" if pause_is_resume else "暂停")
        self.pause_button.setProperty("paused", pause_is_resume)
        # Refresh style immediately when pause/resume state flips.
        self.pause_button.style().unpolish(self.pause_button)
        self.pause_button.style().polish(self.pause_button)
        self.pause_button.update()
        self.record_badge.set_state(state)
        self._sync_title_chip(state)

    def _sync_title_chip(self, state: RecorderState) -> None:
        if state == RecorderState.RECORDING:
            self.title_bar.set_chip_text("录制中")
            return
        if state == RecorderState.PAUSED:
            self.title_bar.set_chip_text("已暂停")
            return
        if state == RecorderState.TRANSCODING:
            self.title_bar.set_chip_text("导出中")
            return
        if state == RecorderState.ERROR:
            self.title_bar.set_chip_text("错误")
            return
        self.title_bar.set_chip_text("就绪")

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str, fallback: str) -> None:
        index = combo.findData(value)
        if index < 0:
            index = combo.findData(fallback)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _apply_save_mode_ui(self) -> None:
        save_mode = self.save_mode_combo.currentData()
        is_realtime = save_mode == SaveMode.REALTIME.value

        if is_realtime:
            self._set_combo_value(self.format_combo, OutputFormat.WAV.value, OutputFormat.WAV.value)
            self.format_combo.setEnabled(False)
            self.format_combo.setToolTip("实时保存模式固定为 WAV")
            self.settings.save_mode = SaveMode.REALTIME.value
            self.settings.output_format = OutputFormat.WAV.value
            return

        self.format_combo.setEnabled(True)
        self.format_combo.setToolTip("选择录音输出文件格式")
        self.settings.save_mode = SaveMode.DEFERRED.value

    @staticmethod
    def _configure_setting_combo(combo: QComboBox) -> None:
        combo.setMinimumHeight(30)
        combo.setMaximumHeight(30)
        combo.setMaxVisibleItems(8)
        popup = QListView(combo)
        popup.setObjectName("SettingComboPopup")
        popup.setSpacing(2)
        combo.setView(popup)

    def _set_update_button_busy(self, busy: bool, label: str) -> None:
        self.title_bar.update_button.setEnabled(not busy)
        self.title_bar.update_button.setText(label)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def closeEvent(self, event):  # type: ignore[override]
        if self._download_thread and self._download_thread.isRunning():
            self._download_thread.cancel()
        self.settings.window_width = self.width()
        self.settings.window_height = self.height()
        self.settings_manager.save(self.settings)
        self.controller.stop_recording("窗口关闭，自动停止录音。")
        return super().closeEvent(event)

    @staticmethod
    def _apply_shadow(widget: QWidget, blur: int, alpha: int, offset_y: int) -> None:
        if not ENABLE_VISUAL_EFFECTS:
            return

        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur)
        shadow.setColor(Qt.black)
        shadow.setOffset(0, offset_y)
        widget.setGraphicsEffect(shadow)
        color = shadow.color()
        color.setAlpha(alpha)
        shadow.setColor(color)
