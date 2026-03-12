from __future__ import annotations

import os
from pathlib import Path

from core.models import AudioProcess, RecorderState
from core.recorder_controller import RecorderController
from core.settings import AppSettings, SettingsManager
from gui.main_window import MainWindow


class _FakeBackend:
    def __init__(self) -> None:
        self._capturing = False

    def is_supported(self) -> bool:
        return True

    def enumerate_audio_processes(self) -> list[AudioProcess]:
        return [AudioProcess(pid=os.getpid(), name="python")]

    def start(self, pid: int, wav_path: Path) -> None:
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(b"RIFF0000")
        self._capturing = True

    def pause(self) -> None:
        self._capturing = True

    def resume(self) -> None:
        self._capturing = True

    def stop(self) -> None:
        self._capturing = False

    def is_capturing(self) -> bool:
        return self._capturing

    def get_level_db(self) -> float:
        return -12.0


class _FakeTranscoder:
    def transcode(self, wav_path: Path, mp3_path: Path, bitrate_kbps: int) -> None:
        mp3_path.write_bytes(b"MP3")

    def concat_wavs_to_mp3(self, wav_paths: list[Path], mp3_path: Path, bitrate_kbps: int) -> None:
        mp3_path.write_bytes(b"MP3")

    def concat_wavs_to_wav(self, wav_paths: list[Path], output_path: Path) -> None:
        output_path.write_bytes(b"WAV")

    def concat_mp3_segments(self, mp3_paths: list[Path], output_path: Path) -> None:
        output_path.write_bytes(b"MP3")


class _FakeProcessService:
    def list_audio_processes(self, keyword: str = "") -> list[AudioProcess]:
        return []


class _FakeUpdater:
    @staticmethod
    def is_supported() -> bool:
        return False


def test_recording_state_locks_format_and_save_mode(qtbot, tmp_path) -> None:
    controller = RecorderController(backend=_FakeBackend(), transcoder=_FakeTranscoder())
    settings_manager = SettingsManager(tmp_path / "config")
    settings = AppSettings(
        output_dir=str(tmp_path),
        output_format="mp3",
        save_mode="realtime",
    )
    window = MainWindow(
        process_service=_FakeProcessService(),
        controller=controller,
        settings_manager=settings_manager,
        settings=settings,
        updater=_FakeUpdater(),
        app_version="1.0.0",
    )
    qtbot.addWidget(window)

    window._apply_state(RecorderState.IDLE)
    assert window.format_combo.isEnabled()
    assert window.save_mode_combo.isEnabled()

    window._apply_state(RecorderState.RECORDING)
    assert not window.format_combo.isEnabled()
    assert not window.save_mode_combo.isEnabled()

    window._apply_state(RecorderState.COMPLETED)
    assert window.format_combo.isEnabled()
    assert window.save_mode_combo.isEnabled()
