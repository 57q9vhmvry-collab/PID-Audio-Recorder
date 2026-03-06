from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO


UINT32_MAX = 0xFFFFFFFF


def repair_wav_header(wav_path: Path) -> bool:
    if not wav_path.exists() or not wav_path.is_file():
        return False

    file_size = wav_path.stat().st_size
    if file_size < 44:
        return False

    with wav_path.open("r+b") as handle:
        header = handle.read(12)
        if len(header) < 12:
            return False
        if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            return False

        data_size_offset, data_payload_offset = _locate_data_chunk(handle, file_size)
        if data_size_offset is None or data_payload_offset is None:
            return False

        riff_size = min(max(file_size - 8, 0), UINT32_MAX)
        data_size = min(max(file_size - data_payload_offset, 0), UINT32_MAX)

        changed = False
        changed |= _write_uint32_if_needed(handle, 4, riff_size)
        changed |= _write_uint32_if_needed(handle, data_size_offset, data_size)
        if changed:
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        return changed


def _locate_data_chunk(handle: BinaryIO, file_size: int) -> tuple[int | None, int | None]:
    cursor = 12
    while cursor + 8 <= file_size:
        handle.seek(cursor)
        chunk_header = handle.read(8)
        if len(chunk_header) < 8:
            return None, None

        chunk_id = chunk_header[:4]
        chunk_size = int.from_bytes(chunk_header[4:8], byteorder="little", signed=False)
        chunk_payload_offset = cursor + 8
        if chunk_id == b"data":
            return cursor + 4, chunk_payload_offset

        next_cursor = chunk_payload_offset + chunk_size + (chunk_size & 1)
        if next_cursor <= cursor or next_cursor > file_size:
            return None, None
        cursor = next_cursor
    return None, None


def _write_uint32_if_needed(handle: BinaryIO, offset: int, value: int) -> bool:
    handle.seek(offset)
    current_raw = handle.read(4)
    if len(current_raw) != 4:
        return False
    current = int.from_bytes(current_raw, byteorder="little", signed=False)
    if current == value:
        return False
    handle.seek(offset)
    handle.write(value.to_bytes(4, byteorder="little", signed=False))
    return True
