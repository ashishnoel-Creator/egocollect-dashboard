#!/usr/bin/env python3
"""Build installers for the EgoCollect dashboard.

Mac:  dist/EgoCollect.app  +  dist/EgoCollect.dmg
Win:  dist/EgoCollect/EgoCollect.exe  +  dist/EgoCollect-win.zip
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_NAME = "EgoCollect"


def run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}\n", flush=True)
    subprocess.check_call(cmd, cwd=ROOT)


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not found; installing…")
        run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"])


def clean() -> None:
    for p in (DIST, BUILD):
        if p.exists():
            shutil.rmtree(p)


def pyinstaller() -> None:
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "build.spec"])


def make_dmg() -> Path:
    app_bundle = DIST / f"{APP_NAME}.app"
    dmg = DIST / f"{APP_NAME}.dmg"
    if not app_bundle.exists():
        raise SystemExit(f"Expected {app_bundle} to exist after PyInstaller.")
    if dmg.exists():
        dmg.unlink()
    run([
        "hdiutil", "create",
        "-volname", APP_NAME,
        "-srcfolder", str(app_bundle),
        "-ov", "-format", "UDZO",
        str(dmg),
    ])
    return dmg


def make_win_zip() -> Path:
    dist_dir = DIST / APP_NAME
    zip_base = DIST / f"{APP_NAME}-win"
    if not dist_dir.exists():
        raise SystemExit(f"Expected {dist_dir} to exist after PyInstaller.")
    zip_path = Path(shutil.make_archive(str(zip_base), "zip", DIST, APP_NAME))
    return zip_path


def main() -> None:
    ensure_pyinstaller()
    clean()
    pyinstaller()

    system = platform.system()
    if system == "Darwin":
        out = make_dmg()
        print(f"\nBuilt DMG: {out}")
        print(f"       App: {DIST / (APP_NAME + '.app')}")
    elif system == "Windows":
        out = make_win_zip()
        print(f"\nBuilt ZIP: {out}")
        print(f"       App folder: {DIST / APP_NAME}")
        print("\nTo produce an .exe installer, open installer.iss in Inno Setup.")
    else:
        print(f"\nBuilt in {DIST}")


if __name__ == "__main__":
    main()
