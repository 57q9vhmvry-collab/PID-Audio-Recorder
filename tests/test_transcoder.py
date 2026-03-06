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

