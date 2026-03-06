from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, QTimer, Signal

from .file_naming import build_output_name, sanitize_process_name
from .models import CaptureBackend, CaptureBackendError, OutputFormat, RecorderRequest, RecorderState, SaveMode
from .transcoder import Mp3Transcoder, TranscodeError

LOGGER = logging.getLogger(__name__)


CAPTURE_ERROR_TEXT = {
    "NOT_SUPPORTED": "系统不支持按 PID 录音（需要 Windows 10 2004+）。",
    "PROCESS_NOT_FOUND": "未找到可录制音频会话。浏览器建议先让页面发声，再从左侧列表选择 PID。",
    "AUDIO_INIT_FAILED": "音频初始化失败，请检查音频设备。",
    "FILE_CREATE_FAILED": "无法创建录音文件，请检查目录权限。",
    "ALREADY_RECORDING": "当前已有录音任务正在运行。",
    "NOT_RECORDING": "当前没有正在录制的任务。",
    "INVALID_PARAM": "录制参数无效。",
    "UNKNOWN": "录音模块发生未知错误。",
}


class RecorderController(QObject):
    state_changed = Signal(object, str)
    level_changed = Signal(float)
    elapsed_changed = Signal(int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        backend: CaptureBackend,
        transcoder: Mp3Transcoder,
        temp_recordings_dir: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend
        self._transcoder = transcoder
        self._temp_recordings_dir = temp_recordings_dir
        self._state = RecorderState.IDLE
        self._request: RecorderRequest | None = None
        self._capture_wav_path: Path | None = None
        self._output_path: Path | None = None
        self._elapsed_seconds = 0

        self._level_timer = QTimer(self)
        self._level_timer.setInterval(100)
        self._level_timer.timeout.connect(self._on_level_tick)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._on_elapsed_tick)

        self._process_timer = QTimer(self)
        self._process_timer.setInterval(500)
        self._process_timer.timeout.connect(self._on_process_tick)

    @property
    def state(self) -> RecorderState:
        return self._state

    def is_supported(self) -> bool:
        return self._backend.is_supported()

    def start_recording(self, request: RecorderRequest) -> None:
        if self._state not in {RecorderState.IDLE, RecorderState.COMPLETED, RecorderState.ERROR}:
            self._emit_failure("当前状态不能开始录音。")
            return

        if not self._backend.is_supported():
            self._set_error("当前系统不支持按 PID 录音（需要 Windows 10 2004+）。")
            return

        if request.pid <= 0 or not psutil.pid_exists(request.pid):
            self._set_error(f"PID {request.pid} 不存在。")
            return

        if request.save_mode == SaveMode.REALTIME and request.output_format != OutputFormat.WAV:
            self._set_error("实时保存当前仅支持 WAV 格式。")
            return

        request.output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = sanitize_process_name(request.process_name)
        output_name = build_output_name(safe_name, request.pid, request.output_format.value, datetime.now())
        output_path = request.output_dir / output_name
        capture_wav_path = self._resolve_capture_wav_path(request, safe_name, output_path)
        capture_wav_path.parent.mkdir(parents=True, exist_ok=True)

        self._request = request
        self._capture_wav_path = capture_wav_path
        self._output_path = output_path
        self._elapsed_seconds = 0
        self.elapsed_changed.emit(self._elapsed_seconds)
        self.level_changed.emit(0.0)
        self._set_state(RecorderState.STARTING, f"正在启动录音：{safe_name} ({request.pid})")

        try:
            self._backend.start(request.pid, capture_wav_path)
        except CaptureBackendError as exc:
            self._handle_capture_error(exc)
            return
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Unexpected backend failure while starting recording.")
            self._set_error(f"启动录音失败: {exc}")
            return

        self._start_timers()
        self._set_state(RecorderState.RECORDING, f"正在录制：{safe_name} ({request.pid})")

    def pause_recording(self) -> None:
        if self._state != RecorderState.RECORDING:
            return
        try:
            self._backend.pause()
            self._set_state(RecorderState.PAUSED, "录制已暂停。")
        except CaptureBackendError as exc:
            self._handle_capture_error(exc)

    def resume_recording(self) -> None:
        if self._state != RecorderState.PAUSED:
            return
        try:
            self._backend.resume()
            self._set_state(RecorderState.RECORDING, "录制已继续。")
        except CaptureBackendError as exc:
            self._handle_capture_error(exc)

    def toggle_pause_resume(self) -> None:
        if self._state == RecorderState.RECORDING:
            self.pause_recording()
        elif self._state == RecorderState.PAUSED:
            self.resume_recording()

    def stop_recording(self, reason: str = "") -> None:
        if self._state not in {RecorderState.RECORDING, RecorderState.PAUSED, RecorderState.STARTING}:
            return

        self._set_state(RecorderState.STOPPING, reason or "正在停止录音...")
        self._stop_timers()
        self.level_changed.emit(0.0)

        try:
            self._backend.stop()
        except CaptureBackendError as exc:
            self._handle_capture_error(exc)
            return
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Unexpected backend failure while stopping recording.")
            self._set_error(f"停止录音失败: {exc}")
            return

        request = self._request
        capture_wav_path = self._capture_wav_path
        output_path = self._output_path
        if not request or not capture_wav_path or not output_path:
            self._set_error("录制会话状态损坏，无法保存输出文件。")
            return

        try:
            final_output_path = self._finalize_output_file(request, capture_wav_path, output_path)
        except Exception as exc:
            self._set_error(str(exc))
            return

        self._set_state(RecorderState.COMPLETED, f"录音完成：{final_output_path}")
        self.finished.emit(final_output_path)
        self._clear_session()

    def _on_level_tick(self) -> None:
        if self._state not in {RecorderState.RECORDING, RecorderState.PAUSED}:
            return
        if not self._backend.is_capturing():
            self.level_changed.emit(0.0)
            return
        db = self._backend.get_level_db()
        self.level_changed.emit(self._db_to_level(db))

    def _on_elapsed_tick(self) -> None:
        if self._state != RecorderState.RECORDING:
            return
        self._elapsed_seconds += 1
        self.elapsed_changed.emit(self._elapsed_seconds)

    def _on_process_tick(self) -> None:
        if self._state not in {RecorderState.RECORDING, RecorderState.PAUSED}:
            return
        if not self._request:
            return
        if not psutil.pid_exists(self._request.pid):
            self.stop_recording("目标进程已退出，已自动停止录音。")

    def _start_timers(self) -> None:
        self._level_timer.start()
        self._elapsed_timer.start()
        self._process_timer.start()

    def _stop_timers(self) -> None:
        self._level_timer.stop()
        self._elapsed_timer.stop()
        self._process_timer.stop()

    def _handle_capture_error(self, exc: CaptureBackendError) -> None:
        LOGGER.exception("Capture backend error: %s", exc)
        message = CAPTURE_ERROR_TEXT.get(exc.code, f"{CAPTURE_ERROR_TEXT['UNKNOWN']} {exc.message}")
        self._set_error(message)

    def _set_state(self, state: RecorderState, message: str) -> None:
        self._state = state
        self.state_changed.emit(state, message)

    def _set_error(self, message: str) -> None:
        self._stop_timers()
        self.level_changed.emit(0.0)
        self._set_state(RecorderState.ERROR, message)
        self._emit_failure(message)
        self._clear_session()

    def _emit_failure(self, message: str) -> None:
        self.failed.emit(message)

    def _clear_session(self) -> None:
        self._request = None
        self._capture_wav_path = None
        self._output_path = None
        self._elapsed_seconds = 0
        self.elapsed_changed.emit(self._elapsed_seconds)

    def _resolve_capture_wav_path(self, request: RecorderRequest, safe_name: str, output_path: Path) -> Path:
        if request.save_mode == SaveMode.REALTIME and request.output_format == OutputFormat.WAV:
            return output_path
        return self._build_temp_wav_path(safe_name, request.pid)

    def _finalize_output_file(self, request: RecorderRequest, capture_wav_path: Path, output_path: Path) -> Path:
        if request.output_format == OutputFormat.MP3:
            self._set_state(RecorderState.TRANSCODING, "正在转换为 MP3...")
            try:
                self._transcoder.transcode(capture_wav_path, output_path, request.bitrate_kbps)
            except TranscodeError as exc:
                LOGGER.exception("Failed to transcode wav to mp3.")
                raise RuntimeError(self._map_transcode_error(exc)) from exc
            except Exception as exc:  # pragma: no cover
                LOGGER.exception("Unexpected transcode failure.")
                raise RuntimeError(f"转码失败: {exc}") from exc

            self._cleanup_temp_wav(capture_wav_path, output_path)
            return output_path

        self._set_state(RecorderState.TRANSCODING, "正在保存 WAV...")
        if capture_wav_path != output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(capture_wav_path), str(output_path))
        return output_path

    @staticmethod
    def _cleanup_temp_wav(capture_wav_path: Path, output_path: Path) -> None:
        if capture_wav_path == output_path:
            return
        try:
            capture_wav_path.unlink(missing_ok=True)
        except OSError:
            LOGGER.warning("Temporary wav file cleanup failed: %s", capture_wav_path)

    @staticmethod
    def _db_to_level(db_value: float) -> float:
        clamped = max(-60.0, min(0.0, db_value))
        return (clamped + 60.0) / 60.0

    def _build_temp_wav_path(self, process_name: str, pid: int) -> Path:
        local_app_data = self._temp_recordings_dir or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PidRecorder" / "tmp"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return local_app_data / f"{process_name}_{pid}_{ts}.wav"

    @staticmethod
    def _map_transcode_error(exc: TranscodeError) -> str:
        if exc.code == "FFMPEG_MISSING":
            return "未找到 ffmpeg，无法导出 MP3。"
        if exc.code == "TRANSCODE_FAILED":
            return f"MP3 转码失败：{exc.message}"
        return f"转码失败：{exc.message}"
