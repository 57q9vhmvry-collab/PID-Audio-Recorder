from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .version import APP_NAME

USER_CONFIG_DIR_NAME = "PIDAudioRecorder"
USER_DATA_DIR_NAME = "PIDAudioRecorderData"


@dataclass(slots=True)
class AppPaths:
    install_root: Path
    resource_root: Path
    user_config_dir: Path
    user_data_dir: Path
    log_dir: Path
    updates_dir: Path
    temp_recordings_dir: Path
    legacy_settings_path: Path
    legacy_log_path: Path


def resolve_app_paths() -> AppPaths:
    install_root, resource_root = _resolve_runtime_roots()
    app_data = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    local_app_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))

    user_config_dir = app_data / USER_CONFIG_DIR_NAME
    user_data_dir = local_app_data / USER_DATA_DIR_NAME
    log_dir = user_data_dir / "logs"
    updates_dir = user_data_dir / "updates"
    temp_recordings_dir = user_data_dir / "recordings" / "tmp"

    return AppPaths(
        install_root=install_root,
        resource_root=resource_root,
        user_config_dir=user_config_dir,
        user_data_dir=user_data_dir,
        log_dir=log_dir,
        updates_dir=updates_dir,
        temp_recordings_dir=temp_recordings_dir,
        legacy_settings_path=install_root / "config" / "settings.json",
        legacy_log_path=install_root / "logs" / "app.log",
    )


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def build_app_display_name(version: str) -> str:
    return f"{APP_NAME} v{version}"


def _resolve_runtime_roots() -> tuple[Path, Path]:
    if is_frozen_runtime():
        install_root = Path(sys.executable).resolve().parent
        resource_root = Path(getattr(sys, "_MEIPASS", install_root))
        return install_root, resource_root

    project_root = Path(__file__).resolve().parents[2]
    return project_root, project_root
