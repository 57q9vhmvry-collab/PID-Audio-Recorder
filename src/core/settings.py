from __future__ import annotations

import shutil
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class AppSettings:
    output_dir: str
    output_format: str = "mp3"
    save_mode: str = "deferred"
    window_width: int = 1080
    window_height: int = 700


class SettingsManager:
    def __init__(self, config_dir: Path, legacy_settings_path: Path | None = None) -> None:
        self.config_dir = config_dir
        self.path = self.config_dir / "settings.json"
        self.legacy_settings_path = legacy_settings_path

    def load(self) -> AppSettings:
        default = self.default()
        self._migrate_legacy_settings()
        if not self.path.exists():
            self.save(default)
            return default

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            output_dir = str(payload.get("output_dir", default.output_dir))
            output_format = str(payload.get("output_format", default.output_format)).lower()
            if output_format not in {"mp3", "wav"}:
                output_format = default.output_format
            save_mode = str(payload.get("save_mode", default.save_mode)).lower()
            if save_mode not in {"deferred", "realtime"}:
                save_mode = default.save_mode
            width = int(payload.get("window_width", default.window_width))
            height = int(payload.get("window_height", default.window_height))
            settings = AppSettings(
                output_dir=output_dir,
                output_format=output_format,
                save_mode=save_mode,
                window_width=width,
                window_height=height,
            )
        except (ValueError, OSError, json.JSONDecodeError):
            settings = default

        Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
        return settings

    def save(self, settings: AppSettings) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")

    def _migrate_legacy_settings(self) -> None:
        legacy_path = self.legacy_settings_path
        if self.path.exists() or legacy_path is None or not legacy_path.exists():
            return

        self.config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_path, self.path)

    @staticmethod
    def default() -> AppSettings:
        default_output = Path.home() / "Music" / "PidRecorder"
        default_output.mkdir(parents=True, exist_ok=True)
        return AppSettings(output_dir=str(default_output))
