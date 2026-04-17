from __future__ import annotations

import json
import re
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


RELEASES_API_URL = "https://api.github.com/repos/{repo}/releases/latest"


@dataclass
class UpdateInfo:
    latest_version: str
    release_name: str
    release_notes: str
    html_url: str
    mac_asset_url: str | None
    win_asset_url: str | None


def _parse_version(v: str) -> tuple[int, ...]:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v)
    if not m:
        return (0, 0, 0)
    return tuple(int(g) for g in m.groups())


def check_for_update(
    current_version: str, repo: str, timeout: float = 5.0,
) -> UpdateInfo | None:
    url = RELEASES_API_URL.format(repo=repo)
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, ValueError):
        return None

    tag = data.get("tag_name", "")
    if not tag:
        return None
    if _parse_version(tag) <= _parse_version(current_version):
        return None

    mac_asset_url = None
    win_asset_url = None
    for asset in data.get("assets", []):
        name = (asset.get("name") or "").lower()
        url = asset.get("browser_download_url")
        if name.endswith(".dmg"):
            mac_asset_url = url
        elif name.endswith(".zip"):
            win_asset_url = url

    return UpdateInfo(
        latest_version=tag,
        release_name=data.get("name") or tag,
        release_notes=data.get("body") or "",
        html_url=data.get("html_url") or "",
        mac_asset_url=mac_asset_url,
        win_asset_url=win_asset_url,
    )


def check_for_update_async(
    current_version: str, repo: str,
    callback: Callable[["UpdateInfo | None"], None],
    timeout: float = 5.0,
) -> None:
    def _run():
        try:
            info = check_for_update(current_version, repo, timeout)
        except Exception:
            info = None
        callback(info)

    threading.Thread(target=_run, daemon=True).start()


def download_update(
    url: str,
    progress_cb: Callable[[int, int], None] | None = None,
) -> Path | None:
    suffix = ".dmg" if url.lower().endswith(".dmg") else ".zip"
    fd, tmp_str = tempfile.mkstemp(prefix="egocollect-update-", suffix=suffix)
    tmp = Path(tmp_str)
    import os
    os.close(fd)
    try:
        with urllib.request.urlopen(url) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            with tmp.open("wb") as fh:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
        return tmp
    except Exception:
        if tmp.exists():
            tmp.unlink()
        return None


def apply_mac_update(dmg_path: Path) -> None:
    subprocess.Popen(["open", str(dmg_path)])


def apply_windows_update(zip_path: Path) -> None:
    """Extract the new build and spawn a helper batch that replaces + restarts."""
    current_exe = Path(sys.executable).resolve()
    install_dir = current_exe.parent

    staging = Path(tempfile.mkdtemp(prefix="egocollect-staging-"))
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(staging)

    candidates = [p for p in staging.iterdir() if p.is_dir()]
    new_install = candidates[0] if candidates else staging
    new_exe = new_install / current_exe.name
    if not new_exe.exists():
        raise RuntimeError(f"Update archive missing {current_exe.name}")

    bat = staging / "apply_update.bat"
    bat.write_text(
        "@echo off\r\n"
        "timeout /t 2 /nobreak >nul\r\n"
        f'rmdir /s /q "{install_dir}"\r\n'
        f'move "{new_install}" "{install_dir}"\r\n'
        f'start "" "{install_dir / current_exe.name}"\r\n',
        encoding="utf-8",
    )
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)
