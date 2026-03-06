from __future__ import annotations

import re
from datetime import datetime

WINDOWS_INVALID_CHARS = r'[<>:"/\\|?*]'


def sanitize_process_name(name: str) -> str:
    cleaned = re.sub(WINDOWS_INVALID_CHARS, "_", name).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "process"


def build_mp3_name(process_name: str, pid: int, now: datetime | None = None) -> str:
    return build_output_name(process_name, pid, "mp3", now)


def build_output_name(process_name: str, pid: int, extension: str, now: datetime | None = None) -> str:
    safe_name = sanitize_process_name(process_name)
    ts = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    normalized_ext = extension.lstrip(".").lower() or "wav"
    return f"{safe_name}_{pid}_{ts}.{normalized_ext}"
