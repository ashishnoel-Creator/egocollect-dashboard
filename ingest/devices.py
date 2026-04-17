from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import psutil


@dataclass
class VolumeInfo:
    path: Path
    label: str
    device: str
    total_bytes: int
    free_bytes: int
    fstype: str


def list_external_volumes() -> list[VolumeInfo]:
    volumes: list[VolumeInfo] = []
    seen: set[str] = set()
    for part in psutil.disk_partitions(all=False):
        if part.mountpoint in seen:
            continue
        seen.add(part.mountpoint)
        if not _is_external(part.mountpoint):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        mp = Path(part.mountpoint)
        volumes.append(VolumeInfo(
            path=mp,
            label=mp.name or str(mp),
            device=part.device,
            total_bytes=usage.total,
            free_bytes=usage.free,
            fstype=part.fstype,
        ))
    volumes.sort(key=lambda v: v.label.lower())
    return volumes


def _is_external(mountpoint: str) -> bool:
    if sys.platform == "darwin":
        if not mountpoint.startswith("/Volumes/"):
            return False
        try:
            return os.stat(mountpoint).st_dev != os.stat("/").st_dev
        except OSError:
            return False
    if sys.platform == "win32":
        system_root = os.environ.get("SystemDrive", "C:").rstrip(":\\").upper()
        letter = mountpoint.rstrip(":\\").upper()
        return letter != system_root
    for prefix in ("/media/", "/mnt/", "/run/media/"):
        if mountpoint.startswith(prefix):
            return True
    return False


def has_dcim(mountpoint: Path) -> bool:
    return (mountpoint / "DCIM").is_dir()
