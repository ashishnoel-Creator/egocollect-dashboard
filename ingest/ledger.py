from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import app_paths


def load_ledger() -> dict:
    path = app_paths().ledger_path
    if not path.exists():
        return {"version": 2, "ssds": {}, "serial_index": {}}
    try:
        with path.open("r") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"version": 2, "ssds": {}, "serial_index": {}}
    data.setdefault("ssds", {})
    data.setdefault("serial_index", {})
    return data


def save_ledger(data: dict) -> None:
    path = app_paths().ledger_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w") as fh:
        json.dump(data, fh, indent=2)
    tmp.replace(path)


def record_ssd_snapshot(manifest: dict, mount_point: Path) -> None:
    ledger = load_ledger()
    ssd_uuid = manifest["ssd_uuid"]
    serial = manifest.get("serial_number")

    ledger["ssds"][ssd_uuid] = {
        "ssd_uuid": ssd_uuid,
        "assigned_name": manifest.get("assigned_name"),
        "serial_number": serial,
        "volume_uuid": manifest.get("volume_uuid"),
        "media_name": manifest.get("media_name"),
        "total_bytes": manifest.get("total_bytes"),
        "registered_at": manifest.get("registered_at"),
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
        "last_mount_point": str(mount_point),
        "sessions": manifest.get("sessions", []),
        "events": manifest.get("events", []),
    }
    if serial:
        ledger["serial_index"][f"serial:{serial}"] = ssd_uuid
    save_ledger(ledger)


def find_by_identity(identity_key: str) -> dict | None:
    """Look up a prior SSD entry by its identity key (serial or uuid)."""
    if not identity_key:
        return None
    ledger = load_ledger()
    ssd_uuid = ledger.get("serial_index", {}).get(identity_key)
    if ssd_uuid and ssd_uuid in ledger.get("ssds", {}):
        return ledger["ssds"][ssd_uuid]
    for entry in ledger.get("ssds", {}).values():
        if entry.get("serial_number") and f"serial:{entry['serial_number']}" == identity_key:
            return entry
        if entry.get("volume_uuid") and f"uuid:{entry['volume_uuid']}" == identity_key:
            return entry
    return None
