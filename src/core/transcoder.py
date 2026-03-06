from __future__ import annotations

import subprocess
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe


class TranscodeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class Mp3Transcoder:
    def build_command(self, wav_path: Path, mp3_path: Path, bitrate_kbps: int) -> list[str]:
        try:
            ffmpeg_exe = get_ffmpeg_exe()
        except Exception as exc:  # pragma: no cover - external lookup failure
            raise TranscodeError("FFMPEG_MISSING", f"无法找到 ffmpeg: {exc}") from exc

        return [
            ffmpeg_exe,
            "-y",
            "-i",
            str(wav_path),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-b:a",
            f"{bitrate_kbps}k",
            str(mp3_path),
        ]

    def transcode(self, wav_path: Path, mp3_path: Path, bitrate_kbps: int) -> None:
        if not wav_path.exists():
            raise TranscodeError("TRANSCODE_FAILED", f"WAV 文件不存在: {wav_path}")

        command = self.build_command(wav_path, mp3_path, bitrate_kbps)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "").strip()
            raise TranscodeError("TRANSCODE_FAILED", error_text or "ffmpeg 转码失败")

