from __future__ import annotations

import json
from pathlib import Path

from core.settings import SettingsManager


def test_settings_manager_migrates_legacy_settings(tmp_path) -> None:
    config_dir = tmp_path / "config"
    legacy_path = tmp_path / "legacy" / "settings.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        json.dumps(
            {
                "output_dir": str(tmp_path / "recordings"),
                "output_format": "wav",
                "save_mode": "realtime",
                "window_width": 1200,
                "window_height": 800,
            }
        ),
        encoding="utf-8",
    )

    manager = SettingsManager(config_dir, legacy_settings_path=legacy_path)
    settings = manager.load()

    assert settings.output_format == "wav"
    assert settings.save_mode == "realtime"
    assert manager.path.exists()


def test_settings_manager_prefers_current_settings_file(tmp_path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    current_path = config_dir / "settings.json"
    current_path.write_text(
        json.dumps({"output_dir": str(tmp_path / "music"), "window_width": 1111, "window_height": 666}),
        encoding="utf-8",
    )

    legacy_path = tmp_path / "legacy" / "settings.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(json.dumps({"output_dir": "ignored"}), encoding="utf-8")

    manager = SettingsManager(config_dir, legacy_settings_path=legacy_path)
    settings = manager.load()

    assert settings.output_dir == str(tmp_path / "music")
    assert settings.window_width == 1111
