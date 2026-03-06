from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from core.updater import GitHubReleaseUpdater, ReleaseInfo, UpdateError, normalize_version


class _Response(io.BytesIO):
    def __init__(self, payload: bytes, headers: dict[str, str] | None = None) -> None:
        super().__init__(payload)
        self.headers = headers or {}

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_normalize_version_strips_v_prefix() -> None:
    assert normalize_version("v1.0.0") == "1.0.0"


def test_check_for_updates_detects_new_release(monkeypatch, tmp_path) -> None:
    payload = {
        "tag_name": "v1.0.1",
        "name": "v1.0.1",
        "body": "Bug fixes",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": "PIDAudioRecorder-Setup-1.0.1.exe",
                "browser_download_url": "https://example.com/PIDAudioRecorder-Setup-1.0.1.exe",
            }
        ],
    }
    monkeypatch.setattr(
        "core.updater.urlopen",
        lambda request, timeout=0: _Response(json.dumps(payload).encode("utf-8")),
    )

    updater = GitHubReleaseUpdater(tmp_path)
    result = updater.check_for_updates("1.0.0")
    assert result.update_available is True
    assert result.latest_version == "1.0.1"
    assert result.release is not None
    assert result.release.installer_name == "PIDAudioRecorder-Setup-1.0.1.exe"


def test_check_for_updates_raises_for_prerelease_payload(monkeypatch, tmp_path) -> None:
    payload = {
        "tag_name": "v1.1.0",
        "draft": False,
        "prerelease": True,
        "assets": [],
    }
    monkeypatch.setattr(
        "core.updater.urlopen",
        lambda request, timeout=0: _Response(json.dumps(payload).encode("utf-8")),
    )

    updater = GitHubReleaseUpdater(tmp_path)
    with pytest.raises(UpdateError):
        updater.check_for_updates("1.0.0")


def test_download_installer_writes_expected_file(monkeypatch, tmp_path) -> None:
    binary_data = b"installer-binary"
    monkeypatch.setattr(
        "core.updater.urlopen",
        lambda request, timeout=0: _Response(binary_data, headers={"Content-Length": str(len(binary_data))}),
    )

    updater = GitHubReleaseUpdater(tmp_path)
    release = ReleaseInfo(
        version="1.0.1",
        tag_name="v1.0.1",
        title="v1.0.1",
        notes="",
        installer_name="PIDAudioRecorder-Setup-1.0.1.exe",
        installer_url="https://example.com/PIDAudioRecorder-Setup-1.0.1.exe",
    )

    path = updater.download_installer(release)
    assert path == tmp_path / "PIDAudioRecorder-Setup-1.0.1.exe"
    assert path.read_bytes() == binary_data
