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
        if self.serial_number:
            return f"serial:{self.serial_number}"
        if self.volume_uuid:
            return f"uuid:{self.volume_uuid}"
        return None


_SERIAL_KEYS = (
    "IOUSBSerialNumber",
    "USBSerialNumber",
    "IOSerialNumber",
    "MediaSerialNumber",
    "MediaSerial",
    "SerialNumber",
    "SerialNumberString",
)


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
    parent_disk: str | None = None

    parent_match = re.match(r"(disk\d+)", device_id)
    if parent_match:
        parent_disk = parent_match.group(1)
        parent_info = _diskutil_plist(parent_disk)
        if parent_info is not None:
            for key in _SERIAL_KEYS:
                val = parent_info.get(key)
                if val and str(val).strip():
                    serial = str(val).strip()
                    break
            media_name = (
                parent_info.get("MediaName")
                or parent_info.get("IORegistryEntryName")
            )

    if not serial:
        serial = _serial_from_ioreg(parent_disk) if parent_disk else None
    if not serial:
        serial = _serial_from_system_profiler(parent_disk) if parent_disk else None

    return DriveInfo(
        serial_number=serial or None,
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


def _serial_from_ioreg(parent_disk: str) -> str | None:
    """Look up the serial number via ioreg by climbing the IOMedia tree."""
    try:
        result = subprocess.run(
            ["ioreg", "-rd1", "-w", "0", "-c", "IOBlockStorageDevice"],
            capture_output=True, check=True, timeout=8, text=True,
        )
    except Exception:
        return None
    target = re.escape(parent_disk)
    block_pattern = re.compile(
        r"\{[^{}]*?\"BSD Name\"\s*=\s*\"" + target + r"\"[^{}]*\}",
        re.DOTALL,
    )
    serial_pattern = re.compile(
        r"\"(?:Serial Number|USB Serial Number|kUSBSerialNumberString)\"\s*=\s*\"([^\"]+)\""
    )
    for blob in re.finditer(r"\{.*?\}", result.stdout, re.DOTALL):
        text = blob.group(0)
        if f'"BSD Name" = "{parent_disk}"' in text:
            m = serial_pattern.search(text)
            if m:
                return m.group(1).strip()
    m = serial_pattern.search(result.stdout)
    return m.group(1).strip() if m else None


def _serial_from_system_profiler(parent_disk: str) -> str | None:
    """Walk SPStorageDataType / SPUSBDataType for a matching bsd_name."""
    for data_type in ("SPStorageDataType", "SPUSBDataType"):
        try:
            result = subprocess.run(
                ["system_profiler", "-xml", data_type],
                capture_output=True, check=True, timeout=15,
            )
            data = plistlib.loads(result.stdout)
        except Exception:
            continue
        serial = _walk_sp_for_serial(data, parent_disk)
        if serial:
            return serial
    return None


def _walk_sp_for_serial(data, parent_disk: str) -> str | None:
    if isinstance(data, list):
        for item in data:
            r = _walk_sp_for_serial(item, parent_disk)
            if r:
                return r
        return None
    if isinstance(data, dict):
        bsd = data.get("bsd_name") or data.get("_name")
        looks_match = False
        if bsd and parent_disk in str(bsd):
            looks_match = True
        for child_key in ("_items", "volumes", "Media"):
            child = data.get(child_key)
            if child:
                if looks_match:
                    candidate = data.get("device_serial") or data.get("serial_num")
                    if candidate:
                        return str(candidate).strip()
                r = _walk_sp_for_serial(child, parent_disk)
                if r:
                    return r
        if looks_match:
            for key in ("device_serial", "serial_num", "DeviceSerial"):
                if data.get(key):
                    return str(data[key]).strip()
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


def debug_dump(mountpoint: Path) -> dict:
    """Diagnostic: return everything we know about a mounted drive.
    Useful for troubleshooting serial-detection failures.
    """
    out: dict = {"mountpoint": str(mountpoint), "platform": sys.platform}
    if sys.platform == "darwin":
        v = _diskutil_plist(str(mountpoint)) or {}
        out["volume_diskutil_keys"] = sorted(v.keys())
        out["device_id"] = v.get("DeviceIdentifier")
        m = re.match(r"(disk\d+)", v.get("DeviceIdentifier", "") or "")
        if m:
            parent = m.group(1)
            p = _diskutil_plist(parent) or {}
            out["parent_disk"] = parent
            out["parent_diskutil_keys"] = sorted(p.keys())
            out["parent_serial_candidates"] = {
                k: p.get(k) for k in _SERIAL_KEYS if p.get(k)
            }
            out["parent_media_name"] = (
                p.get("MediaName") or p.get("IORegistryEntryName")
            )
            out["ioreg_serial"] = _serial_from_ioreg(parent)
            out["system_profiler_serial"] = _serial_from_system_profiler(parent)
    return out
