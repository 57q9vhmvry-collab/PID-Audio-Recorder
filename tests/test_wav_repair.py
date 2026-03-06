from __future__ import annotations

from pathlib import Path

from core.wav_repair import repair_wav_header


def _build_pcm_wav_with_sizes(payload: bytes, riff_size: int, data_size: int) -> bytes:
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
    data_chunk = b"data" + data_size.to_bytes(4, "little") + payload
    return b"RIFF" + riff_size.to_bytes(4, "little") + b"WAVE" + fmt_chunk + data_chunk


def test_repair_wav_header_updates_riff_and_data_sizes(tmp_path: Path) -> None:
    payload = b"\x00" * 4096
    wav_path = tmp_path / "broken.wav"
    wav_path.write_bytes(_build_pcm_wav_with_sizes(payload, riff_size=36, data_size=0))

    changed = repair_wav_header(wav_path)

    raw = wav_path.read_bytes()
    assert changed is True
    assert int.from_bytes(raw[4:8], "little") == len(raw) - 8
    assert int.from_bytes(raw[40:44], "little") == len(payload)


def test_repair_wav_header_ignores_non_wav_file(tmp_path: Path) -> None:
    not_wav = tmp_path / "invalid.bin"
    not_wav.write_bytes(b"not-a-wav")

    changed = repair_wav_header(not_wav)

    assert changed is False
