from __future__ import annotations

import os
from pathlib import Path

from core.models import AudioProcess, OutputFormat, RecorderRequest, RecorderState, SaveMode
from core.recorder_controller import RecorderController


class FakeBackend:
    def __init__(self) -> None:
        self._capturing = False
        self.wav_path: Path | None = None

    def is_supported(self) -> bool:
        return True

    def enumerate_audio_processes(self) -> list[AudioProcess]:
        return [AudioProcess(pid=os.getpid(), name="python")]

    def start(self, pid: int, wav_path: Path) -> None:
        self.wav_path = wav_path
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


class FakeTranscoder:
    def transcode(self, wav_path: Path, mp3_path: Path, bitrate_kbps: int) -> None:
        mp3_path.write_bytes(b"MP3")


def test_controller_start_pause_resume_stop(qtbot, tmp_path) -> None:
    backend = FakeBackend()
    controller = RecorderController(backend=backend, transcoder=FakeTranscoder())
    states: list[RecorderState] = []
    controller.state_changed.connect(lambda state, message: states.append(state))

    request = RecorderRequest(
        pid=os.getpid(),
        process_name="pytest",
        output_dir=tmp_path,
    )
    controller.start_recording(request)
    assert controller.state == RecorderState.RECORDING

    controller.pause_recording()
    assert controller.state == RecorderState.PAUSED

    controller.resume_recording()
    assert controller.state == RecorderState.RECORDING

    controller.stop_recording("test")
    assert controller.state == RecorderState.COMPLETED
    assert any(tmp_path.glob("*.mp3"))
    assert RecorderState.PAUSED in states


def test_controller_auto_stop_on_pid_exit(monkeypatch, qtbot, tmp_path) -> None:
    backend = FakeBackend()
    controller = RecorderController(backend=backend, transcoder=FakeTranscoder())
    pid = os.getpid()
    request = RecorderRequest(pid=pid, process_name="pytest", output_dir=tmp_path)
    controller.start_recording(request)
    assert controller.state == RecorderState.RECORDING

    monkeypatch.setattr(
        "core.recorder_controller.psutil.pid_exists",
        lambda value: False if value == pid else True,
    )
    controller._on_process_tick()
    assert controller.state == RecorderState.COMPLETED


def test_controller_stop_with_deferred_wav_output(qtbot, tmp_path) -> None:
    backend = FakeBackend()
    controller = RecorderController(backend=backend, transcoder=FakeTranscoder())
    request = RecorderRequest(
        pid=os.getpid(),
        process_name="pytest",
        output_dir=tmp_path,
        output_format=OutputFormat.WAV,
        save_mode=SaveMode.DEFERRED,
    )
    controller.start_recording(request)
    controller.stop_recording("test")

    wav_files = list(tmp_path.glob("*.wav"))
    assert controller.state == RecorderState.COMPLETED
    assert len(wav_files) == 1


def test_controller_stop_with_realtime_wav_output(qtbot, tmp_path) -> None:
    backend = FakeBackend()
    controller = RecorderController(backend=backend, transcoder=FakeTranscoder())
    request = RecorderRequest(
        pid=os.getpid(),
        process_name="pytest",
        output_dir=tmp_path,
        output_format=OutputFormat.WAV,
        save_mode=SaveMode.REALTIME,
    )
    controller.start_recording(request)
    assert backend.wav_path is not None
    assert backend.wav_path.parent == tmp_path

    controller.stop_recording("test")
    assert controller.state == RecorderState.COMPLETED
    assert any(tmp_path.glob("*.wav"))


def test_controller_rejects_realtime_mp3_mode(qtbot, tmp_path) -> None:
    backend = FakeBackend()
    controller = RecorderController(backend=backend, transcoder=FakeTranscoder())
    request = RecorderRequest(
        pid=os.getpid(),
        process_name="pytest",
        output_dir=tmp_path,
        output_format=OutputFormat.MP3,
        save_mode=SaveMode.REALTIME,
    )
    controller.start_recording(request)
    assert controller.state == RecorderState.ERROR


def test_controller_uses_configured_temp_recording_dir(qtbot, tmp_path) -> None:
    backend = FakeBackend()
    temp_dir = tmp_path / "temp-recordings"
    controller = RecorderController(backend=backend, transcoder=FakeTranscoder(), temp_recordings_dir=temp_dir)
    request = RecorderRequest(pid=os.getpid(), process_name="pytest", output_dir=tmp_path)

    controller.start_recording(request)

    assert backend.wav_path is not None
    assert backend.wav_path.parent == temp_dir
