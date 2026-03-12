from __future__ import annotations

from pathlib import Path

import pytest

from core.transcoder import Mp3Transcoder, TranscodeError


def test_build_command_contains_mp3_params(monkeypatch) -> None:
    monkeypatch.setattr("core.transcoder.get_ffmpeg_exe", lambda: "ffmpeg.exe")
    transcoder = Mp3Transcoder()
    cmd = transcoder.build_command(Path("a.wav"), Path("b.mp3"), 192)

    assert cmd[0] == "ffmpeg.exe"
    assert "libmp3lame" in cmd
    assert "192k" in cmd
    assert str(Path("b.mp3")) == cmd[-1]


def test_transcode_raises_when_wav_missing() -> None:
    transcoder = Mp3Transcoder()
    with pytest.raises(TranscodeError) as exc:
        transcoder.transcode(Path("missing.wav"), Path("out.mp3"), 192)
    assert exc.value.code == "TRANSCODE_FAILED"


def test_concat_wavs_to_mp3_uses_concat_demuxer(monkeypatch, tmp_path) -> None:
    commands: list[list[str]] = []

    class _Result:
        returncode = 0
        stderr = ""
        stdout = ""

    monkeypatch.setattr("core.transcoder.get_ffmpeg_exe", lambda: "ffmpeg.exe")
    monkeypatch.setattr(
        "core.transcoder.subprocess.run",
        lambda command, capture_output, text, check: commands.append(command) or _Result(),
    )

    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    a.write_bytes(b"A")
    b.write_bytes(b"B")

    transcoder = Mp3Transcoder()
    transcoder.concat_wavs_to_mp3([a, b], tmp_path / "out.mp3", 64)

    assert commands
    assert commands[0][0] == "ffmpeg.exe"
    assert "-f" in commands[0]
    assert "concat" in commands[0]
    assert "64k" in commands[0]


def test_concat_mp3_segments_moves_single_segment(tmp_path) -> None:
    transcoder = Mp3Transcoder()
    part = tmp_path / "part.mp3"
    out = tmp_path / "out.mp3"
    part.write_bytes(b"MP3")

    transcoder.concat_mp3_segments([part], out)

    assert out.read_bytes() == b"MP3"
    assert not part.exists()
