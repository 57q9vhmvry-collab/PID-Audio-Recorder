from __future__ import annotations

import logging
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from core.app_paths import build_app_display_name, resolve_app_paths
from core.capture_backend import ProcessAudioCaptureBackend
from core.process_service import ProcessService
from core.recorder_controller import RecorderController
from core.settings import SettingsManager
from core.transcoder import Mp3Transcoder
from core.updater import GitHubReleaseUpdater
from core.version import APP_NAME, APP_VERSION
from gui.mac_theme import build_stylesheet, create_palette
from gui.main_window import MainWindow

LOGGER = logging.getLogger(__name__)
ASSETS_DIR_NAME = "assets"
FONT_FILE_NAME = "DouyinSansBold.otf"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"


def configure_logging(log_dir: Path, legacy_log_path: Path | None = None) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"
    if legacy_log_path and legacy_log_path.exists() and not log_file.exists():
        try:
            shutil.copy2(legacy_log_path, log_file)
        except OSError:
            pass

    formatter = logging.Formatter(LOG_FORMAT)
    handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


def load_app_font(project_root: Path) -> str | None:
    font_path = project_root / ASSETS_DIR_NAME / FONT_FILE_NAME
    if not font_path.exists():
        LOGGER.warning("Custom font file not found: %s", font_path)
        return None

    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id < 0:
        LOGGER.warning("Failed to load custom font: %s", font_path)
        return None

    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        LOGGER.warning("No font family found in: %s", font_path)
        return None

    family = families[0]
    LOGGER.info("Loaded custom font family: %s", family)
    return family


def main() -> int:
    paths = resolve_app_paths()
    configure_logging(paths.log_dir, paths.legacy_log_path)

    app = QApplication(sys.argv)
    app.setApplicationName(build_app_display_name(APP_VERSION))
    font_family = load_app_font(paths.resource_root)
    if font_family:
        app.setFont(QFont(font_family))
    app.setPalette(create_palette())
    app.setStyleSheet(build_stylesheet(font_family=font_family))

    settings_manager = SettingsManager(paths.user_config_dir, legacy_settings_path=paths.legacy_settings_path)
    settings = settings_manager.load()

    backend = ProcessAudioCaptureBackend()
    process_service = ProcessService(backend)
    recorder_controller = RecorderController(
        backend=backend,
        transcoder=Mp3Transcoder(),
        temp_recordings_dir=paths.temp_recordings_dir,
    )
    updater = GitHubReleaseUpdater(paths.updates_dir)

    window = MainWindow(
        process_service=process_service,
        controller=recorder_controller,
        settings_manager=settings_manager,
        settings=settings,
        updater=updater,
        app_version=APP_VERSION,
    )
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
