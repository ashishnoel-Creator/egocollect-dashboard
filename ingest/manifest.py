from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .device_info import DriveInfo
from .models import SessionRecord


MANIFEST_FILENAME = ".egocentric-manifest.json"


def manifest_path(ssd_root: Path) -> Path:
    return ssd_root / MANIFEST_FILENAME


def load_manifest(ssd_root: Path) -> dict:
    path = manifest_path(ssd_root)
    if not path.exists():
        return {}
    try:
        with path.open("r") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def save_manifest(ssd_root: Path, data: dict) -> None:
    data["last_updated"] = _now()
    path = manifest_path(ssd_root)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w") as fh:
        json.dump(data, fh, indent=2)
    tmp.replace(path)


def new_manifest(drive_info: DriveInfo, assigned_name: str) -> dict:
    now = _now()
    return {
        "schema_version": 2,
        "ssd_uuid": str(uuid.uuid4()),
        "assigned_name": assigned_name,
        "serial_number": drive_info.serial_number,
        "volume_uuid": drive_info.volume_uuid,
        "media_name": drive_info.media_name,
        "total_bytes": drive_info.total_bytes,
        "registered_at": now,
        "last_updated": now,
        "sessions": [],
        "events": [],
    }


def migrate_manifest(data: dict, drive_info: DriveInfo) -> dict:
    """In-place upgrade of an older manifest to schema_version 2."""
    changed = False
    if data.get("schema_version") != 2:
        data["schema_version"] = 2
        changed = True
    if "assigned_name" not in data and data.get("logical_name"):
        data["assigned_name"] = data["logical_name"]
        changed = True
    if "serial_number" not in data and drive_info.serial_number:
        data["serial_number"] = drive_info.serial_number
        changed = True
    if "volume_uuid" not in data and drive_info.volume_uuid:
        data["volume_uuid"] = drive_info.volume_uuid
        changed = True
    if "media_name" not in data and drive_info.media_name:
        data["media_name"] = drive_info.media_name
        changed = True
    if "total_bytes" not in data and drive_info.total_bytes:
        data["total_bytes"] = drive_info.total_bytes
        changed = True
    if "registered_at" not in data:
        data["registered_at"] = data.get("created_at") or _now()
        changed = True
    if "events" not in data:
        data["events"] = []
        changed = True
    return data if changed else data


def append_session(ssd_root: Path, record: SessionRecord) -> dict:
    data = load_manifest(ssd_root)
    data.setdefault("sessions", []).append(asdict(record))
    data.setdefault("events", []).append({
        "type": "copy_session",
        "timestamp": _now(),
        "data": {
            "session_number": record.session_number,
            "collection_date": record.collection_date,
            "mode": record.mode,
            "employee_id": record.employee_id,
            "task_type": record.task_type,
            "position": record.position,
            "file_count": record.file_count,
            "total_bytes": record.total_bytes,
        },
    })
    save_manifest(ssd_root, data)
    return data


def append_event(ssd_root: Path, event_type: str, payload: dict) -> dict:
    data = load_manifest(ssd_root)
    data.setdefault("events", []).append({
        "type": event_type,
        "timestamp": _now(),
        "data": payload,
    })
    save_manifest(ssd_root, data)
    return data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
