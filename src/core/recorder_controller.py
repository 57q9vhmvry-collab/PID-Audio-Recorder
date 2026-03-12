from __future__ import annotations

import json
import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, QTimer, Signal

from .file_naming import build_output_name, sanitize_process_name
from .models import CaptureBackend, CaptureBackendError, OutputFormat, RecorderRequest, RecorderState, SaveMode
from .transcoder import Mp3Transcoder, TranscodeError
from .wav_repair import repair_wav_header

LOGGER = logging.getLogger(__name__)

DEFAULT_SEGMENT_ROTATE_BYTES = 256 * 1024 * 1024

CAPTURE_ERROR_TEXT = {
    "NOT_SUPPORTED": "系统不支持按 PID 录音（需要 Windows 10 2004+）。",
    "PROCESS_NOT_FOUND": "未找到可录制的音频会话。请先让目标进程发声后再选择。",
    "AUDIO_INIT_FAILED": "音频初始化失败，请检查音频设备。",
    "FILE_CREATE_FAILED": "无法创建录音文件，请检查目录权限。",
    "ALREADY_RECORDING": "当前已有录音任务正在运行。",
    "NOT_RECORDING": "当前没有正在录制的任务。",
    "INVALID_PARAM": "录音参数无效。",
    "UNKNOWN": "录音模块发生未知错误。",
}


@dataclass(slots=True)
class RecordingSegment:
    index: int
    wav_path: Path
    mp3_path: Path | None = None

    def to_payload(self) -> dict[str, str | int | None]:
        return {
            "index": self.index,
            "wav_path": str(self.wav_path),
            "mp3_path": str(self.mp3_path) if self.mp3_path else None,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> RecordingSegment | None:
        try:
            index = int(payload["index"])
            wav_raw = payload["wav_path"]
        except (KeyError, TypeError, ValueError):
            return None

        if not isinstance(wav_raw, str) or not wav_raw:
            return None

        mp3_raw = payload.get("mp3_path")
        mp3_path = Path(mp3_raw) if isinstance(mp3_raw, str) and mp3_raw else None
        return cls(index=index, wav_path=Path(wav_raw), mp3_path=mp3_path)


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
        segment_rotate_bytes: int = DEFAULT_SEGMENT_ROTATE_BYTES,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend
        self._transcoder = transcoder
        self._temp_recordings_dir = temp_recordings_dir
        self._segment_rotate_bytes = max(segment_rotate_bytes, 1)
        self._state = RecorderState.IDLE
        self._request: RecorderRequest | None = None
        self._capture_wav_path: Path | None = None
        self._output_path: Path | None = None
        self._elapsed_seconds = 0
        self._runtime_dir = self._resolve_runtime_dir()
        self._realtime_session_path = self._runtime_dir / "active_realtime_recording.json"
        self._segments: list[RecordingSegment] = []
        self._active_segment: RecordingSegment | None = None
        self._segment_jobs: dict[int, Future[Path]] = {}
        self._segment_executor: ThreadPoolExecutor | None = None

        self._level_timer = QTimer(self)
        self._level_timer.setInterval(100)
        self._level_timer.timeout.connect(self._on_level_tick)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._on_elapsed_tick)

        self._process_timer = QTimer(self)
        self._process_timer.setInterval(500)
        self._process_timer.timeout.connect(self._on_process_tick)

        self._header_timer = QTimer(self)
        self._header_timer.setInterval(1200)
        self._header_timer.timeout.connect(self._on_header_tick)

        self._segment_timer = QTimer(self)
        self._segment_timer.setInterval(2000)
        self._segment_timer.timeout.connect(self._on_segment_tick)

        self._recover_interrupted_realtime_recording()

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

        request.output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = sanitize_process_name(request.process_name)
        output_name = build_output_name(safe_name, request.pid, request.output_format.value, datetime.now())
        output_path = request.output_dir / output_name

        self._request = request
        self._output_path = output_path
        self._elapsed_seconds = 0
        self._reset_segment_state()
        self.elapsed_changed.emit(self._elapsed_seconds)
        self.level_changed.emit(0.0)

        active_segment = self._create_segment(output_path)
        self._segments.append(active_segment)
        self._active_segment = active_segment
        self._capture_wav_path = active_segment.wav_path
        self._set_state(RecorderState.STARTING, f"正在启动录音：{safe_name} ({request.pid})")

        if request.save_mode == SaveMode.REALTIME and request.output_format == OutputFormat.MP3:
            self._segment_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pid-recorder-mp3")

        self._persist_realtime_session()
        try:
            self._backend.start(request.pid, active_segment.wav_path)
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
        output_path = self._output_path
        if not request or not output_path or not self._segments:
            self._set_error("录音会话状态损坏，无法保存输出文件。")
            return

        active_segment = self._active_segment
        if active_segment is not None:
            self._repair_wav_header_if_needed(active_segment.wav_path)

        try:
            final_output_path = self._finalize_output_file(request, output_path)
        except Exception as exc:
            self._set_error(str(exc))
            return

        self._set_state(RecorderState.COMPLETED, f"录音完成：{final_output_path}")
        self.finished.emit(final_output_path)
        self._cleanup_segment_files(self._segments, keep={final_output_path})
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

    def _on_header_tick(self) -> None:
        self._poll_segment_jobs()
        if self._state != RecorderState.RECORDING:
            return
        request = self._request
        active_segment = self._active_segment
        if request is None or active_segment is None:
            return
        if request.save_mode != SaveMode.REALTIME:
            return
        self._repair_wav_header_if_needed(active_segment.wav_path)

    def _on_segment_tick(self) -> None:
        self._poll_segment_jobs()
        if self._state != RecorderState.RECORDING:
            return
        if self._capture_wav_path is None:
            return
        try:
            current_size = self._capture_wav_path.stat().st_size
        except OSError:
            return
        if current_size >= self._segment_rotate_bytes:
            self._rotate_segment()

    def _start_timers(self) -> None:
        self._level_timer.start()
        self._elapsed_timer.start()
        self._process_timer.start()
        self._header_timer.start()
        self._segment_timer.start()

    def _stop_timers(self) -> None:
        self._level_timer.stop()
        self._elapsed_timer.stop()
        self._process_timer.stop()
        self._header_timer.stop()
        self._segment_timer.stop()

    def _rotate_segment(self) -> None:
        request = self._request
        output_path = self._output_path
        active_segment = self._active_segment
        if request is None or output_path is None or active_segment is None:
            return

        LOGGER.info("Rotating recording segment: %s", active_segment.wav_path)
        try:
            self._backend.stop()
        except CaptureBackendError as exc:
            self._handle_capture_error(exc)
            return
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Unexpected backend failure while rotating recording.")
            self._set_error(f"分段录音失败: {exc}")
            return

        self._repair_wav_header_if_needed(active_segment.wav_path)
        next_segment = self._create_segment(output_path)

        try:
            self._backend.start(request.pid, next_segment.wav_path)
        except CaptureBackendError as exc:
            self._handle_capture_error(exc)
            return
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Unexpected backend restart failure while rotating recording.")
            self._set_error(f"分段录音失败: {exc}")
            return

        self._segments.append(next_segment)
        self._active_segment = next_segment
        self._capture_wav_path = next_segment.wav_path
        self._submit_realtime_mp3_export(active_segment)
        self._persist_realtime_session()

    def _submit_realtime_mp3_export(self, segment: RecordingSegment) -> None:
        request = self._request
        executor = self._segment_executor
        if request is None or executor is None:
            return
        if request.save_mode != SaveMode.REALTIME or request.output_format != OutputFormat.MP3:
            return
        if segment.index in self._segment_jobs:
            return

        mp3_path = segment.wav_path.with_suffix(".mp3")
        future = executor.submit(self._transcode_segment_file, segment.wav_path, mp3_path, request.bitrate_kbps)
        self._segment_jobs[segment.index] = future

    def _poll_segment_jobs(self, wait: bool = False) -> None:
        completed: list[int] = []
        for index, future in list(self._segment_jobs.items()):
            if not wait and not future.done():
                continue

            segment = self._find_segment(index)
            try:
                mp3_path = future.result()
            except Exception as exc:  # pragma: no cover - best effort background job
                LOGGER.warning("Background MP3 segment transcode failed for segment %s: %s", index, exc)
            else:
                if segment is not None:
                    segment.mp3_path = mp3_path
                    self._persist_realtime_session()
            completed.append(index)

        for index in completed:
            self._segment_jobs.pop(index, None)

    def _wait_for_segment_jobs(self) -> None:
        self._poll_segment_jobs(wait=True)
        executor = self._segment_executor
        self._segment_executor = None
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=False)

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
        self._persist_realtime_session()
        self._clear_session(clear_marker=False)

    def _emit_failure(self, message: str) -> None:
        self.failed.emit(message)

    def _clear_session(self, clear_marker: bool = True) -> None:
        self._request = None
        self._capture_wav_path = None
        self._output_path = None
        self._elapsed_seconds = 0
        self.elapsed_changed.emit(self._elapsed_seconds)
        self._reset_segment_state()
        if clear_marker:
            self._clear_realtime_session_marker()

    def _reset_segment_state(self) -> None:
        self._wait_for_segment_jobs()
        self._segments = []
        self._active_segment = None

    def _create_segment(self, output_path: Path) -> RecordingSegment:
        request = self._request
        if request is None:
            raise RuntimeError("录音请求不存在。")

        index = len(self._segments)
        segment_dir = output_path.parent if request.save_mode == SaveMode.REALTIME else self._runtime_dir
        segment_dir.mkdir(parents=True, exist_ok=True)
        wav_path = segment_dir / f"{output_path.stem}.part{index:04d}.wav"
        return RecordingSegment(index=index, wav_path=wav_path)

    def _finalize_output_file(self, request: RecorderRequest, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if request.output_format == OutputFormat.MP3:
            self._set_state(RecorderState.TRANSCODING, "正在导出 MP3...")
            try:
                if request.save_mode == SaveMode.REALTIME:
                    segment_paths = self._prepare_realtime_mp3_segments(request)
                    self._transcoder.concat_mp3_segments(segment_paths, output_path)
                else:
                    wav_paths = self._existing_wav_segments()
                    self._transcoder.concat_wavs_to_mp3(wav_paths, output_path, request.bitrate_kbps)
            except TranscodeError as exc:
                LOGGER.exception("Failed to export MP3 output.")
                raise RuntimeError(self._map_transcode_error(exc)) from exc
            except Exception as exc:  # pragma: no cover
                LOGGER.exception("Unexpected MP3 export failure.")
                raise RuntimeError(f"导出 MP3 失败: {exc}") from exc
            return output_path

        self._set_state(RecorderState.TRANSCODING, "正在保存 WAV...")
        try:
            wav_paths = self._existing_wav_segments()
            self._transcoder.concat_wavs_to_wav(wav_paths, output_path)
        except TranscodeError as exc:
            LOGGER.exception("Failed to export WAV output.")
            raise RuntimeError(self._map_transcode_error(exc)) from exc
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Unexpected WAV export failure.")
            raise RuntimeError(f"保存 WAV 失败: {exc}") from exc

        self._repair_wav_header_if_needed(output_path)
        return output_path

    def _prepare_realtime_mp3_segments(self, request: RecorderRequest) -> list[Path]:
        self._wait_for_segment_jobs()
        mp3_paths: list[Path] = []

        for segment in sorted(self._segments, key=lambda item: item.index):
            if segment.mp3_path is not None and segment.mp3_path.exists():
                mp3_paths.append(segment.mp3_path)
                continue

            if not segment.wav_path.exists():
                raise RuntimeError(f"缺少录音分段文件: {segment.wav_path}")

            self._repair_wav_header_if_needed(segment.wav_path)
            mp3_path = segment.wav_path.with_suffix(".mp3")
            self._transcoder.transcode(segment.wav_path, mp3_path, request.bitrate_kbps)
            segment.mp3_path = mp3_path
            mp3_paths.append(mp3_path)
            try:
                segment.wav_path.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Failed to remove temporary WAV segment: %s", segment.wav_path)

        if not mp3_paths:
            raise RuntimeError("未生成任何 MP3 分段。")
        return mp3_paths

    def _existing_wav_segments(self) -> list[Path]:
        wav_paths: list[Path] = []
        for segment in sorted(self._segments, key=lambda item: item.index):
            if segment.wav_path.exists():
                self._repair_wav_header_if_needed(segment.wav_path)
                wav_paths.append(segment.wav_path)
        if not wav_paths:
            raise RuntimeError("未找到可用的 WAV 分段。")
        return wav_paths

    def _persist_realtime_session(self) -> None:
        request = self._request
        output_path = self._output_path
        if request is None or output_path is None or request.save_mode != SaveMode.REALTIME or not self._segments:
            return

        marker_path = self._realtime_session_path
        try:
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "output_path": str(output_path),
                "output_format": request.output_format.value,
                "save_mode": request.save_mode.value,
                "bitrate_kbps": request.bitrate_kbps,
                "segments": [segment.to_payload() for segment in self._segments],
                "active_index": self._active_segment.index if self._active_segment else None,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            marker_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        except OSError:
            LOGGER.warning("Failed to persist realtime recording marker: %s", marker_path)

    def _clear_realtime_session_marker(self) -> None:
        try:
            self._realtime_session_path.unlink(missing_ok=True)
        except OSError:
            LOGGER.warning("Failed to clear realtime recording marker: %s", self._realtime_session_path)

    def _recover_interrupted_realtime_recording(self) -> None:
        marker_path = self._realtime_session_path
        if not marker_path.exists():
            return

        try:
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._clear_realtime_session_marker()
            return

        output_raw = payload.get("output_path")
        output_format_raw = payload.get("output_format", OutputFormat.WAV.value)
        bitrate_raw = payload.get("bitrate_kbps", 64)
        segments_payload = payload.get("segments", [])

        if not isinstance(output_raw, str) or not output_raw:
            self._clear_realtime_session_marker()
            return
        if not isinstance(segments_payload, list) or not segments_payload:
            self._clear_realtime_session_marker()
            return

        output_path = Path(output_raw)
        output_format = OutputFormat.MP3 if output_format_raw == OutputFormat.MP3.value else OutputFormat.WAV
        try:
            bitrate_kbps = int(bitrate_raw)
        except (TypeError, ValueError):
            bitrate_kbps = 64

        segments = [
            segment
            for raw in segments_payload
            if isinstance(raw, dict)
            for segment in [RecordingSegment.from_payload(raw)]
            if segment is not None
        ]
        if not segments:
            self._clear_realtime_session_marker()
            return

        success = False
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            segments.sort(key=lambda item: item.index)

            if output_format == OutputFormat.MP3:
                mp3_paths: list[Path] = []
                for segment in segments:
                    if segment.mp3_path is not None and segment.mp3_path.exists():
                        mp3_paths.append(segment.mp3_path)
                        continue

                    if not segment.wav_path.exists():
                        continue

                    self._repair_wav_header_if_needed(segment.wav_path)
                    mp3_path = segment.mp3_path or segment.wav_path.with_suffix(".mp3")
                    self._transcoder.transcode(segment.wav_path, mp3_path, bitrate_kbps)
                    mp3_paths.append(mp3_path)

                if mp3_paths:
                    self._transcoder.concat_mp3_segments(mp3_paths, output_path)
                    success = True
            else:
                wav_paths = [segment.wav_path for segment in segments if segment.wav_path.exists()]
                for wav_path in wav_paths:
                    self._repair_wav_header_if_needed(wav_path)
                if wav_paths:
                    self._transcoder.concat_wavs_to_wav(wav_paths, output_path)
                    self._repair_wav_header_if_needed(output_path)
                    success = True

            if success:
                LOGGER.info("Recovered interrupted realtime recording: %s", output_path)
                self._cleanup_segment_files(segments, keep={output_path})
        except Exception as exc:  # pragma: no cover - best effort recovery
            LOGGER.warning("Failed to recover interrupted realtime recording: %s", exc)
            return
        finally:
            if success:
                self._clear_realtime_session_marker()

    def _cleanup_segment_files(self, segments: list[RecordingSegment], keep: set[Path] | None = None) -> None:
        keep_paths = keep or set()
        for segment in segments:
            for path in (segment.wav_path, segment.mp3_path):
                if path is None or path in keep_paths:
                    continue
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    LOGGER.warning("Failed to clean temporary segment file: %s", path)

    def _transcode_segment_file(self, wav_path: Path, mp3_path: Path, bitrate_kbps: int) -> Path:
        self._transcoder.transcode(wav_path, mp3_path, bitrate_kbps)
        wav_path.unlink(missing_ok=True)
        return mp3_path

    @staticmethod
    def _db_to_level(db_value: float) -> float:
        clamped = max(-60.0, min(0.0, db_value))
        return (clamped + 60.0) / 60.0

    def _resolve_runtime_dir(self) -> Path:
        return self._temp_recordings_dir or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PidRecorder" / "tmp"

    def _find_segment(self, index: int) -> RecordingSegment | None:
        for segment in self._segments:
            if segment.index == index:
                return segment
        return None

    @staticmethod
    def _repair_wav_header_if_needed(wav_path: Path) -> bool:
        try:
            return repair_wav_header(wav_path)
        except OSError:
            return False

    @staticmethod
    def _map_transcode_error(exc: TranscodeError) -> str:
        if exc.code == "FFMPEG_MISSING":
            return "未找到 ffmpeg，无法导出音频文件。"
        if exc.code == "TRANSCODE_FAILED":
            return f"音频导出失败：{exc.message}"
        return f"音频导出失败：{exc.message}"
