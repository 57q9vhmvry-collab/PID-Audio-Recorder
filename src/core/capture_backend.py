from __future__ import annotations

from pathlib import Path
from typing import Optional

from process_audio_capture import (
    PacErrorCode,
    ProcessAudioCapture,
    ProcessAudioCaptureError,
)

from .models import AudioProcess, CaptureBackend, CaptureBackendError


ERROR_CODE_MAP = {
    PacErrorCode.NOT_SUPPORTED: "NOT_SUPPORTED",
    PacErrorCode.PROCESS_NOT_FOUND: "PROCESS_NOT_FOUND",
    PacErrorCode.AUDIO_INIT_FAILED: "AUDIO_INIT_FAILED",
    PacErrorCode.FILE_CREATE_FAILED: "FILE_CREATE_FAILED",
    PacErrorCode.ALREADY_RECORDING: "ALREADY_RECORDING",
    PacErrorCode.NOT_RECORDING: "NOT_RECORDING",
    PacErrorCode.INVALID_PARAM: "INVALID_PARAM",
}


class ProcessAudioCaptureBackend(CaptureBackend):
    def __init__(self) -> None:
        self._capture: Optional[ProcessAudioCapture] = None

    def is_supported(self) -> bool:
        return ProcessAudioCapture.is_supported()

    def enumerate_audio_processes(self) -> list[AudioProcess]:
        try:
            items = ProcessAudioCapture.enumerate_audio_processes()
        except ProcessAudioCaptureError as exc:
            raise self._map_exception(exc) from exc

        result: list[AudioProcess] = []
        for item in items:
            result.append(AudioProcess(pid=item.pid, name=item.name, window_title=item.window_title))
        return result

    def start(self, pid: int, wav_path: Path) -> None:
        if self._capture is not None:
            raise CaptureBackendError("ALREADY_RECORDING", "当前已有录音任务正在运行")

        wav_path.parent.mkdir(parents=True, exist_ok=True)
        self._capture = ProcessAudioCapture(pid=pid, output_path=str(wav_path))
        try:
            self._capture.start()
        except ProcessAudioCaptureError as exc:
            self._capture = None
            raise self._map_exception(exc) from exc

    def pause(self) -> None:
        capture = self._ensure_capture()
        try:
            capture.pause()
        except ProcessAudioCaptureError as exc:
            raise self._map_exception(exc) from exc

    def resume(self) -> None:
        capture = self._ensure_capture()
        try:
            capture.resume()
        except ProcessAudioCaptureError as exc:
            raise self._map_exception(exc) from exc

    def stop(self) -> None:
        capture = self._capture
        if capture is None:
            return

        self._capture = None
        try:
            capture.stop()
        except ProcessAudioCaptureError as exc:
            raise self._map_exception(exc) from exc

    def is_capturing(self) -> bool:
        capture = self._capture
        return bool(capture and capture.is_capturing)

    def get_level_db(self) -> float:
        capture = self._capture
        if capture is None:
            return -60.0
        return float(capture.level_db)

    def _ensure_capture(self) -> ProcessAudioCapture:
        if self._capture is None:
            raise CaptureBackendError("NOT_RECORDING", "当前没有正在录制的任务")
        return self._capture

    @staticmethod
    def _map_exception(exc: ProcessAudioCaptureError) -> CaptureBackendError:
        code = ERROR_CODE_MAP.get(exc.code, "UNKNOWN")
        return CaptureBackendError(code, exc.message)

