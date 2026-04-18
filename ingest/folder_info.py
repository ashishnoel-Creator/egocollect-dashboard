from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


INFO_FILENAME = "info.json"

_locks_master = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _lock_for(folder: Path) -> threading.Lock:
    key = str(folder.resolve())
    with _locks_master:
        return _locks.setdefault(key, threading.Lock())


def info_path(emp_folder: Path) -> Path:
    return emp_folder / INFO_FILENAME


def update_folder_info(
    emp_folder: Path,
    mode: str,
    collection_date: str,
    task_type: str,
    employee_id: str,
    ssd_assigned_name: str,
    ssd_serial_number: str | None,
    machine: str,
    is_three_cam: bool,
) -> dict:
    """Create or update info.json by walking the emp folder for actual files.

    Always re-walks the folder so the info reflects on-disk reality after the
    copy, not a snapshot of the latest copy alone.
    """
    lock = _lock_for(emp_folder)
    with lock:
        path = info_path(emp_folder)
        if path.exists():
            try:
                with path.open("r") as fh:
                    info = json.load(fh)
            except (OSError, json.JSONDecodeError):
                info = {}
        else:
            info = {}

        now = _now()
        if not info:
            info = {
                "mode": mode,
                "collection_date": collection_date,
                "task_type": task_type,
                "employee_id": employee_id,
                "first_copy_at": now,
                "copy_count": 0,
            }
        info["mode"] = mode
        info["collection_date"] = collection_date
        info["task_type"] = task_type
        info["employee_id"] = employee_id
        info["ssd_assigned_name"] = ssd_assigned_name
        info["ssd_serial_number"] = ssd_serial_number
        info["last_updated"] = now
        info["last_machine"] = machine
        info["copy_count"] = int(info.get("copy_count", 0)) + 1

        files: list[dict] = []
        total_bytes = 0
        by_position: dict[str, dict] = {}
        for f in sorted(emp_folder.rglob("*")):
            if not f.is_file():
                continue
            if f.name == INFO_FILENAME:
                continue
            if f.name == "checksums.sha256":
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            rel = f.relative_to(emp_folder).as_posix()
            files.append({"path": rel, "bytes": size})
            if f.suffix.upper() == ".MP4":
                total_bytes += size
                if is_three_cam:
                    parts = f.relative_to(emp_folder).parts
                    if len(parts) > 1:
                        pos = parts[0]
                        bp = by_position.setdefault(pos, {"files": 0, "bytes": 0})
                        bp["files"] += 1
                        bp["bytes"] += size

        info["file_count"] = sum(1 for f in files if f["path"].lower().endswith(".mp4"))
        info["total_bytes"] = total_bytes
        info["total_gb"] = round(total_bytes / (1000 ** 3), 3)
        info["files"] = files
        if is_three_cam:
            info["by_position"] = by_position
        else:
            info.pop("by_position", None)

        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w") as fh:
            json.dump(info, fh, indent=2)
        tmp.replace(path)
        return info


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
