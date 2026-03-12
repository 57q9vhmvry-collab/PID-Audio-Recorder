from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe


class TranscodeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class Mp3Transcoder:
    def build_command(self, wav_path: Path, mp3_path: Path, bitrate_kbps: int) -> list[str]:
        return [
            self._get_ffmpeg_exe(),
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
            raise TranscodeError("TRANSCODE_FAILED", f"WAV file does not exist: {wav_path}")

        self._run(self.build_command(wav_path, mp3_path, bitrate_kbps))

    def concat_wavs_to_mp3(self, wav_paths: list[Path], mp3_path: Path, bitrate_kbps: int) -> None:
        self._ensure_input_paths(wav_paths)
        if len(wav_paths) == 1:
            self.transcode(wav_paths[0], mp3_path, bitrate_kbps)
            return

        with _ConcatFile(wav_paths) as concat_path:
            self._run(
                [
                    self._get_ffmpeg_exe(),
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_path),
                    "-vn",
                    "-acodec",
                    "libmp3lame",
                    "-b:a",
                    f"{bitrate_kbps}k",
                    str(mp3_path),
                ]
            )

    def concat_wavs_to_wav(self, wav_paths: list[Path], output_path: Path) -> None:
        self._ensure_input_paths(wav_paths)
        if len(wav_paths) == 1:
            wav_paths[0].replace(output_path)
            return

        with _ConcatFile(wav_paths) as concat_path:
            self._run(
                [
                    self._get_ffmpeg_exe(),
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_path),
                    "-vn",
                    "-c:a",
                    "pcm_f32le",
                    "-rf64",
                    "auto",
                    str(output_path),
                ]
            )

    def concat_mp3_segments(self, mp3_paths: list[Path], output_path: Path) -> None:
        self._ensure_input_paths(mp3_paths)
        if len(mp3_paths) == 1:
            mp3_paths[0].replace(output_path)
            return

        with _ConcatFile(mp3_paths) as concat_path:
            self._run(
                [
                    self._get_ffmpeg_exe(),
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_path),
                    "-c",
                    "copy",
                    str(output_path),
                ]
            )

    @staticmethod
    def _ensure_input_paths(paths: list[Path]) -> None:
        if not paths:
            raise TranscodeError("TRANSCODE_FAILED", "No audio segments were provided")

        missing = [str(path) for path in paths if not path.exists()]
        if missing:
            raise TranscodeError("TRANSCODE_FAILED", f"Missing audio segments: {', '.join(missing)}")

    @staticmethod
    def _get_ffmpeg_exe() -> str:
        try:
            return get_ffmpeg_exe()
        except Exception as exc:  # pragma: no cover - external lookup failure
            raise TranscodeError("FFMPEG_MISSING", f"Unable to locate ffmpeg: {exc}") from exc

    @staticmethod
    def _run(command: list[str]) -> None:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "").strip()
            raise TranscodeError("TRANSCODE_FAILED", error_text or "ffmpeg failed")


class _ConcatFile:
    def __init__(self, paths: list[Path]) -> None:
        self._paths = paths
        self._path: Path | None = None

    def __enter__(self) -> Path:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
            for path in self._paths:
                escaped = str(path).replace("\\", "/").replace("'", r"'\''")
                handle.write(f"file '{escaped}'\n")
            self._path = Path(handle.name)
        return self._path

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._path is not None:
            self._path.unlink(missing_ok=True)
