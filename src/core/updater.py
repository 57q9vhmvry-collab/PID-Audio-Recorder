from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .app_paths import is_frozen_runtime
from .version import GITHUB_REPOSITORY, INSTALLER_NAME_PREFIX

SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
GITHUB_API_TIMEOUT_SECONDS = 15
CHUNK_SIZE = 64 * 1024


class UpdateError(RuntimeError):
    pass


@dataclass(slots=True)
class ReleaseInfo:
    version: str
    tag_name: str
    title: str
    notes: str
    installer_name: str
    installer_url: str


@dataclass(slots=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    release: ReleaseInfo | None
    update_available: bool


def parse_semver(value: str) -> tuple[int, int, int]:
    match = SEMVER_RE.fullmatch(value.strip())
    if not match:
        raise UpdateError(f"无效版本号: {value}")
    return tuple(int(part) for part in match.groups())


def normalize_version(value: str) -> str:
    major, minor, patch = parse_semver(value)
    return f"{major}.{minor}.{patch}"


class GitHubReleaseUpdater:
    def __init__(self, updates_dir: Path, repository: str = GITHUB_REPOSITORY) -> None:
        self.repository = repository
        self.updates_dir = updates_dir

    @staticmethod
    def is_supported() -> bool:
        return is_frozen_runtime()

    def check_for_updates(self, current_version: str) -> UpdateCheckResult:
        current_version = normalize_version(current_version)
        current_tuple = parse_semver(current_version)
        release = self._fetch_latest_release()
        latest_tuple = parse_semver(release.version)
        return UpdateCheckResult(
            current_version=current_version,
            latest_version=release.version,
            release=release,
            update_available=latest_tuple > current_tuple,
        )

    def download_installer(
        self,
        release: ReleaseInfo,
        progress_callback: Callable[[int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        self.updates_dir.mkdir(parents=True, exist_ok=True)
        final_path = self.updates_dir / release.installer_name
        partial_path = final_path.with_suffix(final_path.suffix + ".part")

        request = Request(
            release.installer_url,
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": "PIDAudioRecorder-Updater",
            },
        )

        downloaded = 0
        total = 0
        try:
            with urlopen(request, timeout=GITHUB_API_TIMEOUT_SECONDS) as response:
                total = int(response.headers.get("Content-Length", "0") or "0")
                with partial_path.open("wb") as file_handle:
                    while True:
                        if cancelled and cancelled():
                            raise UpdateError("已取消下载。")
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        file_handle.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total)
        except (HTTPError, URLError) as exc:
            partial_path.unlink(missing_ok=True)
            raise UpdateError(f"下载更新失败: {exc}") from exc
        except OSError as exc:
            partial_path.unlink(missing_ok=True)
            raise UpdateError(f"保存安装包失败: {exc}") from exc
        except Exception:
            partial_path.unlink(missing_ok=True)
            raise

        if downloaded <= 0:
            partial_path.unlink(missing_ok=True)
            raise UpdateError("下载结果为空，未生成有效安装包。")

        partial_path.replace(final_path)
        return final_path

    def _fetch_latest_release(self) -> ReleaseInfo:
        api_url = f"https://api.github.com/repos/{self.repository}/releases/latest"
        request = Request(
            api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "PIDAudioRecorder-Updater",
            },
        )

        try:
            with urlopen(request, timeout=GITHUB_API_TIMEOUT_SECONDS) as response:
                payload = json.load(response)
        except HTTPError as exc:
            raise UpdateError(f"读取最新版本失败: HTTP {exc.code}") from exc
        except URLError as exc:
            raise UpdateError(f"读取最新版本失败: {exc.reason}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise UpdateError(f"读取最新版本失败: {exc}") from exc

        if payload.get("draft") or payload.get("prerelease"):
            raise UpdateError("最新 Release 不是正式版。")

        tag_name = str(payload.get("tag_name", "")).strip()
        version = normalize_version(tag_name)
        title = str(payload.get("name") or tag_name).strip() or tag_name
        notes = str(payload.get("body") or "").strip()

        asset = self._select_installer_asset(payload.get("assets", []), version)
        return ReleaseInfo(
            version=version,
            tag_name=tag_name,
            title=title,
            notes=notes,
            installer_name=asset["name"],
            installer_url=asset["browser_download_url"],
        )

    @staticmethod
    def _select_installer_asset(assets: list[object], version: str) -> dict[str, str]:
        expected_name = f"{INSTALLER_NAME_PREFIX}{version}.exe"
        for raw_asset in assets:
            if not isinstance(raw_asset, dict):
                continue
            name = str(raw_asset.get("name", "")).strip()
            download_url = str(raw_asset.get("browser_download_url", "")).strip()
            if name == expected_name and download_url:
                return {"name": name, "browser_download_url": download_url}

        raise UpdateError(f"Release 中未找到安装包资源: {expected_name}")
