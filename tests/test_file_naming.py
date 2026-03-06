from __future__ import annotations

from datetime import datetime

from core.file_naming import build_mp3_name, build_output_name, sanitize_process_name


def test_sanitize_process_name_removes_windows_invalid_chars() -> None:
    assert sanitize_process_name('my<proc>:name*?') == "my_proc__name__"


def test_build_mp3_name_uses_expected_pattern() -> None:
    name = build_mp3_name("chrome", 1234, datetime(2026, 3, 5, 10, 30, 20))
    assert name == "chrome_1234_20260305_103020.mp3"


def test_build_output_name_supports_wav_extension() -> None:
    name = build_output_name("chrome", 1234, "wav", datetime(2026, 3, 5, 10, 30, 20))
    assert name == "chrome_1234_20260305_103020.wav"
