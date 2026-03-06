from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.version import APP_VERSION, INSTALLER_NAME_PREFIX


def main() -> None:
    output_base_filename = f"{INSTALLER_NAME_PREFIX}{APP_VERSION}"
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "PIDAudioRecorder.spec"])
    run(
        [
            locate_iscc(),
            f"/DAppVersion={APP_VERSION}",
            f"/DOutputBaseFilename={output_base_filename}",
            "installer.iss",
        ]
    )


def locate_iscc() -> str:
    candidates = [
        shutil.which("ISCC.exe"),
        str(Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("未找到 ISCC.exe，请先安装 Inno Setup 6。")


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
