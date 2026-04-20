from __future__ import annotations

import json
import os
import plistlib
import re
import shlex
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


def apply_mac_update(dmg_path: Path) -> bool:
    """Silent self-update on Mac.

    Returns True if the update was staged and a background helper is now
    waiting for the app to quit (caller should call QApplication.quit()).
    Returns False if we can't do a silent install — in that case the DMG
    is opened in Finder and the caller should show the legacy "drag to
    Applications" dialog.
    """
    current_app = _current_app_bundle()
    if current_app is None or not os.access(current_app.parent, os.W_OK):
        subprocess.Popen(["open", str(dmg_path)])
        return False

    try:
        mount_point, staged_app, staging_dir = _stage_app_from_dmg(dmg_path)
    except Exception:
        subprocess.Popen(["open", str(dmg_path)])
        return False

    parent_pid = os.getpid()
    log_file = staging_dir / "apply_update.log"
    helper = staging_dir / "apply_update.sh"

    helper.write_text(_build_mac_helper_script(
        log_file=log_file,
        parent_pid=parent_pid,
        current_app=current_app,
        staged_app=staged_app,
        staging_dir=staging_dir,
    ))
    helper.chmod(0o755)

    subprocess.Popen(
        ["/bin/bash", str(helper)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True


def _current_app_bundle() -> Path | None:
    """If we're running from inside an `.app` bundle, return its path."""
    exe = Path(sys.executable).resolve()
    for ancestor in exe.parents:
        if ancestor.suffix == ".app":
            return ancestor
    return None


def _stage_app_from_dmg(dmg_path: Path) -> tuple[Path, Path, Path]:
    """Mount the DMG, copy the first `.app` inside to a temp dir, detach."""
    result = subprocess.run(
        ["hdiutil", "attach", "-nobrowse", "-plist", str(dmg_path)],
        capture_output=True, check=True, timeout=60,
    )
    data = plistlib.loads(result.stdout)
    mount_point: Path | None = None
    for entity in data.get("system-entities", []):
        mp = entity.get("mount-point")
        if mp:
            mount_point = Path(mp)
            break
    if mount_point is None:
        raise RuntimeError("failed to find DMG mount point")

    staging_dir = Path(tempfile.mkdtemp(prefix="egocollect-update-"))
    try:
        apps = list(mount_point.glob("*.app"))
        if not apps:
            raise RuntimeError("no .app inside DMG")
        source_app = apps[0]
        staged_app = staging_dir / source_app.name
        subprocess.run(
            ["cp", "-R", str(source_app), str(staged_app)],
            check=True, timeout=180,
        )
    finally:
        subprocess.run(
            ["hdiutil", "detach", str(mount_point), "-force"],
            capture_output=True,
        )
    return mount_point, staged_app, staging_dir


def _build_mac_helper_script(
    log_file: Path,
    parent_pid: int,
    current_app: Path,
    staged_app: Path,
    staging_dir: Path,
) -> str:
    log_q = shlex.quote(str(log_file))
    current_q = shlex.quote(str(current_app))
    staged_q = shlex.quote(str(staged_app))
    staging_q = shlex.quote(str(staging_dir))
    app_name = current_app.name
    fallback_q = shlex.quote(str(Path.home() / "Desktop" / app_name))
    return f"""#!/bin/bash
LOG={log_q}
exec >> "$LOG" 2>&1
PID_TO_WAIT={parent_pid}
CURRENT={current_q}
STAGED={staged_q}
STAGING_DIR={staging_q}
FALLBACK={fallback_q}

echo "[$(date)] helper started; waiting for PID $PID_TO_WAIT"
for i in $(seq 1 60); do
  if ! kill -0 "$PID_TO_WAIT" 2>/dev/null; then
    break
  fi
  sleep 0.5
done
sleep 1

echo "[$(date)] parent has exited, replacing app"
if [ -d "$CURRENT" ]; then
  rm -rf "$CURRENT"
  if [ -e "$CURRENT" ]; then
    echo "[$(date)] rm failed; falling back to Desktop install"
    ditto "$STAGED" "$FALLBACK"
    xattr -cr "$FALLBACK" 2>/dev/null || true
    open "$FALLBACK"
    exit 1
  fi
fi
mv "$STAGED" "$CURRENT"
if [ ! -d "$CURRENT" ]; then
  echo "[$(date)] mv failed; falling back to Desktop install"
  ditto "$STAGED" "$FALLBACK" 2>/dev/null || true
  xattr -cr "$FALLBACK" 2>/dev/null || true
  open "$FALLBACK"
  exit 2
fi

xattr -cr "$CURRENT" 2>/dev/null || true
echo "[$(date)] launching new version"
open "$CURRENT"

sleep 3
rm -rf "$STAGING_DIR"
echo "[$(date)] done"
"""


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
