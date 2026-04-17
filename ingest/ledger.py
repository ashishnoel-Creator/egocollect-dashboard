from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import app_paths


def load_ledger() -> dict:
    path = app_paths().ledger_path
    if not path.exists():
        return {"version": 1, "ssds": {}}
    with path.open("r") as fh:
        return json.load(fh)


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
    ledger["ssds"][ssd_uuid] = {
        "logical_name": manifest.get("logical_name"),
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
        "last_mount_point": str(mount_point),
        "created_at": manifest.get("created_at"),
        "sessions": manifest.get("sessions", []),
    }
    save_ledger(ledger)
