from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


class OutputFormat(Enum):
    MP3 = "mp3"
    WAV = "wav"


class SaveMode(Enum):
    DEFERRED = "deferred"
    REALTIME = "realtime"


@dataclass(slots=True)
class RecorderRequest:
    pid: int
    process_name: str
    output_dir: Path
    output_format: OutputFormat = OutputFormat.MP3
    save_mode: SaveMode = SaveMode.DEFERRED
    sample_rate: int = 48000
    channels: int = 2
    bitrate_kbps: int = 64


class RecorderState(Enum):
    IDLE = "idle"
    STARTING = "starting"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPING = "stopping"
    TRANSCODING = "transcoding"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass(slots=True)
class AudioProcess:
    pid: int
    name: str
    window_title: str = ""


class CaptureBackendError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class CaptureBackend(Protocol):
    def is_supported(self) -> bool:
        raise NotImplementedError

    def enumerate_audio_processes(self) -> list[AudioProcess]:
        raise NotImplementedError

    def start(self, pid: int, wav_path: Path) -> None:
        raise NotImplementedError

    def pause(self) -> None:
        raise NotImplementedError

    def resume(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def is_capturing(self) -> bool:
        raise NotImplementedError

    def get_level_db(self) -> float:
        raise NotImplementedError
