from __future__ import annotations

import plistlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DriveInfo:
    serial_number: str | None
    volume_uuid: str | None
    media_name: str | None
    total_bytes: int

    def identity_key(self) -> str | None:
        """Stable identifier across reformats. Prefers hardware serial."""
        if self.serial_number:
            return f"serial:{self.serial_number}"
        if self.volume_uuid:
            return f"uuid:{self.volume_uuid}"
        return None


def get_drive_info(mountpoint: Path) -> DriveInfo:
    if sys.platform == "darwin":
        return _get_drive_info_mac(mountpoint)
    if sys.platform == "win32":
        return _get_drive_info_win(mountpoint)
    return DriveInfo(None, None, None, 0)


def _get_drive_info_mac(mountpoint: Path) -> DriveInfo:
    info = _diskutil_plist(str(mountpoint))
    if info is None:
        return DriveInfo(None, None, None, 0)

    volume_uuid = info.get("VolumeUUID")
    total_bytes = int(info.get("Size") or 0)
    device_id = info.get("DeviceIdentifier", "")

    serial = None
    media_name = None

    parent_match = re.match(r"(disk\d+)", device_id)
    if parent_match:
        parent_info = _diskutil_plist(parent_match.group(1))
        if parent_info is not None:
            serial = (
                parent_info.get("IOUSBSerialNumber")
                or parent_info.get("SerialNumber")
                or parent_info.get("DiskUUID")
            )
            media_name = (
                parent_info.get("MediaName")
                or parent_info.get("IORegistryEntryName")
            )

    return DriveInfo(
        serial_number=str(serial) if serial else None,
        volume_uuid=str(volume_uuid) if volume_uuid else None,
        media_name=str(media_name) if media_name else None,
        total_bytes=total_bytes,
    )


def _diskutil_plist(target: str) -> dict | None:
    try:
        result = subprocess.run(
            ["diskutil", "info", "-plist", target],
            capture_output=True, check=True, timeout=10,
        )
        return plistlib.loads(result.stdout)
    except Exception:
        return None


def _get_drive_info_win(mountpoint: Path) -> DriveInfo:
    mp = str(mountpoint)
    ps_script = (
        f"$v = Get-Volume -FilePath '{mp}' -ErrorAction SilentlyContinue; "
        "if ($v) { "
        "$part = Get-Partition -Volume $v -ErrorAction SilentlyContinue; "
        "$disk = $part | Get-Disk -ErrorAction SilentlyContinue; "
        "Write-Output ('serial=' + $disk.SerialNumber); "
        "Write-Output ('model=' + $disk.FriendlyName); "
        "Write-Output ('size=' + $disk.Size); "
        "Write-Output ('uuid=' + $v.UniqueId); "
        "Write-Output ('volsize=' + $v.Size); "
        "}"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, check=True, timeout=10, text=True,
        )
    except Exception:
        return DriveInfo(None, None, None, 0)

    fields: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            fields[k.strip()] = v.strip()

    return DriveInfo(
        serial_number=fields.get("serial") or None,
        volume_uuid=fields.get("uuid") or None,
        media_name=fields.get("model") or None,
        total_bytes=int(fields.get("size") or fields.get("volsize") or 0),
    )


def size_bucket(total_bytes: int) -> str:
    """Round to a standard SSD size label. Marketing GB (10^9), not GiB."""
    if total_bytes <= 0:
        return "?"
    gb = total_bytes / (1000 ** 3)
    candidates = [
        (500, "500GB"),
        (1000, "1TB"),
        (2000, "2TB"),
        (4000, "4TB"),
        (8000, "8TB"),
        (16000, "16TB"),
    ]
    for threshold, label in candidates:
        if gb <= threshold * 1.1:
            return label
    return f"{round(gb / 1000)}TB"
