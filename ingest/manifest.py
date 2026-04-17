from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import SessionRecord


MANIFEST_FILENAME = ".egocentric-manifest.json"


def manifest_path(ssd_root: Path) -> Path:
    return ssd_root / MANIFEST_FILENAME


def load_manifest(ssd_root: Path) -> dict:
    path = manifest_path(ssd_root)
    if not path.exists():
        return {}
    with path.open("r") as fh:
        return json.load(fh)


def ensure_manifest(ssd_root: Path, logical_name: str | None = None) -> dict:
    data = load_manifest(ssd_root)
    if not data:
        data = {
            "ssd_uuid": str(uuid.uuid4()),
            "logical_name": logical_name or ssd_root.name,
            "created_at": _now(),
            "last_updated": _now(),
            "sessions": [],
        }
        save_manifest(ssd_root, data)
    elif logical_name and not data.get("logical_name"):
        data["logical_name"] = logical_name
        save_manifest(ssd_root, data)
    return data


def save_manifest(ssd_root: Path, data: dict) -> None:
    data["last_updated"] = _now()
    path = manifest_path(ssd_root)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w") as fh:
        json.dump(data, fh, indent=2)
    tmp.replace(path)


def append_session(ssd_root: Path, record: SessionRecord) -> dict:
    data = ensure_manifest(ssd_root)
    data["sessions"].append(asdict(record))
    save_manifest(ssd_root, data)
    return data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
