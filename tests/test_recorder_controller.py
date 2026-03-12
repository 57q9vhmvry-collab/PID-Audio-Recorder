from __future__ import annotations

import json
import os
from pathlib import Path

from core.models import AudioProcess, OutputFormat, RecorderRequest, RecorderState, SaveMode
from core.recorder_controller import RecorderController


class FakeBackend:
    def __init__(self) -> None:
        self._capturing = False
        self.wav_path: Path | None = None
        self.started_paths: list[Path] = []

    def is_supported(self) -> bool:
        return True

    def enumerate_audio_processes(self) -> list[AudioProcess]:
        return [AudioProcess(pid=os.getpid(), name="python")]

    def start(self, pid: int, wav_path: Path) -> None:
        self.wav_path = wav_path
        self.started_paths.append(wav_path)
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
        mp3_path.parent.mkdir(parents=True, exist_ok=True)
        mp3_path.write_bytes(b"MP3" + wav_path.read_bytes())

    def concat_wavs_to_mp3(self, wav_paths: list[Path], mp3_path: Path, bitrate_kbps: int) -> None:
        mp3_path.parent.mkdir(parents=True, exist_ok=True)
        mp3_path.write_bytes(b"".join(path.read_bytes() for path in wav_paths) or b"MP3")

    def concat_wavs_to_wav(self, wav_paths: list[Path], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if len(wav_paths) == 1:
            wav_paths[0].replace(output_path)
            return
        output_path.write_bytes(b"".join(path.read_bytes() for path in wav_paths))

    def concat_mp3_segments(self, mp3_paths: list[Path], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if len(mp3_paths) == 1:
            mp3_paths[0].replace(output_path)
            return
        output_path.write_bytes(b"".join(path.read_bytes() for path in mp3_paths))


def _build_broken_pcm_wav(payload: bytes) -> bytes:
    channels = 2
    sample_rate = 48000
    bits_per_sample = 16
    block_align = channels * bits_per_sample // 8
    byte_rate = sample_rate * block_align
    fmt_chunk = (
        b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + channels.to_bytes(2, "little")
        + sample_rate.to_bytes(4, "little")
        + byte_rate.to_bytes(4, "little")
        + block_align.to_bytes(2, "little")
        + bits_per_sample.to_bytes(2, "little")
    )
    data_chunk = b"data" + (0).to_bytes(4, "little") + payload
    return b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + fmt_chunk + data_chunk


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
    assert backend.wav_path.name.endswith(".part0000.wav")

    controller.stop_recording("test")
    assert controller.state == RecorderState.COMPLETED
    assert any(tmp_path.glob("*.wav"))


def test_controller_supports_realtime_mp3_mode(qtbot, tmp_path) -> None:
    backend = FakeBackend()
    controller = RecorderController(backend=backend, transcoder=FakeTranscoder(), segment_rotate_bytes=12)
    request = RecorderRequest(
        pid=os.getpid(),
        process_name="pytest",
        output_dir=tmp_path,
        output_format=OutputFormat.MP3,
        save_mode=SaveMode.REALTIME,
    )
    controller.start_recording(request)
    assert controller.state == RecorderState.RECORDING

    assert backend.wav_path is not None
    backend.wav_path.write_bytes(b"0123456789abcdef")
    controller._on_segment_tick()

    assert len(controller._segments) == 2
    controller.stop_recording("test")
    assert controller.state == RecorderState.COMPLETED
    assert any(tmp_path.glob("*.mp3"))


def test_controller_uses_configured_temp_recording_dir(qtbot, tmp_path) -> None:
    backend = FakeBackend()
    temp_dir = tmp_path / "temp-recordings"
    controller = RecorderController(backend=backend, transcoder=FakeTranscoder(), temp_recordings_dir=temp_dir)
    request = RecorderRequest(pid=os.getpid(), process_name="pytest", output_dir=tmp_path)

    controller.start_recording(request)

    assert backend.wav_path is not None
    assert backend.wav_path.parent == temp_dir


def test_controller_rotates_segments_before_single_wav_grows_too_large(qtbot, tmp_path) -> None:
    backend = FakeBackend()
    controller = RecorderController(
        backend=backend,
        transcoder=FakeTranscoder(),
        segment_rotate_bytes=12,
    )
    request = RecorderRequest(
        pid=os.getpid(),
        process_name="pytest",
        output_dir=tmp_path,
        output_format=OutputFormat.WAV,
        save_mode=SaveMode.DEFERRED,
    )
    controller.start_recording(request)

    first_segment = backend.wav_path
    assert first_segment is not None
    first_segment.write_bytes(b"0123456789abcdef")
    controller._on_segment_tick()

    assert len(controller._segments) == 2
    assert controller._capture_wav_path is not None
    assert controller._capture_wav_path != first_segment


def test_controller_recovers_realtime_wav_after_unclean_shutdown(qtbot, tmp_path) -> None:
    temp_dir = tmp_path / "temp-recordings"
    temp_dir.mkdir(parents=True, exist_ok=True)

    payload = b"\x01" * 3200
    wav_path = tmp_path / "crashed.part0000.wav"
    wav_path.write_bytes(_build_broken_pcm_wav(payload))

    marker_path = temp_dir / "active_realtime_recording.json"
    marker_path.write_text(
        json.dumps(
            {
                "output_path": str(tmp_path / "crashed.wav"),
                "output_format": "wav",
                "save_mode": "realtime",
                "bitrate_kbps": 64,
                "segments": [
                    {
                        "index": 0,
                        "wav_path": str(wav_path),
                        "mp3_path": None,
                    }
                ],
                "active_index": 0,
            }
        ),
        encoding="utf-8",
    )

    RecorderController(backend=FakeBackend(), transcoder=FakeTranscoder(), temp_recordings_dir=temp_dir)

    recovered_wav = tmp_path / "crashed.wav"
    raw = recovered_wav.read_bytes()
    assert not marker_path.exists()
    assert recovered_wav.exists()
    assert int.from_bytes(raw[4:8], "little") == len(raw) - 8
    assert int.from_bytes(raw[40:44], "little") == len(payload)


def test_controller_recovers_realtime_mp3_after_unclean_shutdown(qtbot, tmp_path) -> None:
    temp_dir = tmp_path / "temp-recordings"
    temp_dir.mkdir(parents=True, exist_ok=True)

    segment_wav = tmp_path / "crashed.part0001.wav"
    segment_wav.write_bytes(_build_broken_pcm_wav(b"\x02" * 2048))
    segment_mp3 = tmp_path / "crashed.part0000.mp3"
    segment_mp3.write_bytes(b"MP3-READY")

    marker_path = temp_dir / "active_realtime_recording.json"
    marker_path.write_text(
        json.dumps(
            {
                "output_path": str(tmp_path / "crashed.mp3"),
                "output_format": "mp3",
                "save_mode": "realtime",
                "bitrate_kbps": 64,
                "segments": [
                    {
                        "index": 0,
                        "wav_path": str(tmp_path / "crashed.part0000.wav"),
                        "mp3_path": str(segment_mp3),
                    },
                    {
                        "index": 1,
                        "wav_path": str(segment_wav),
                        "mp3_path": None,
                    },
                ],
                "active_index": 1,
            }
        ),
        encoding="utf-8",
    )

    RecorderController(backend=FakeBackend(), transcoder=FakeTranscoder(), temp_recordings_dir=temp_dir)

    recovered_mp3 = tmp_path / "crashed.mp3"
    assert not marker_path.exists()
    assert recovered_mp3.exists()
    assert recovered_mp3.read_bytes().startswith(b"MP3")
