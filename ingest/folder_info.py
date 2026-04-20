from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from .media_info import format_duration, format_duration_hms, mp4_duration_seconds


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

    Also probes each MP4 for its duration and aggregates per-folder and
    per-position totals.
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

        # Load previous duration cache so we don't re-probe existing files
        prev_durations: dict[str, float] = {}
        for f in info.get("files", []):
            if isinstance(f, dict) and f.get("path") and f.get("duration_seconds"):
                prev_durations[f["path"]] = float(f["duration_seconds"])

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
        total_duration = 0.0
        by_position: dict[str, dict] = {}
        for f in sorted(emp_folder.rglob("*")):
            if not f.is_file():
                continue
            if f.name == INFO_FILENAME or f.name == "checksums.sha256":
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            rel = f.relative_to(emp_folder).as_posix()
            file_entry = {"path": rel, "bytes": size}
            is_mp4 = f.suffix.upper() == ".MP4"
            if is_mp4:
                total_bytes += size
                duration = prev_durations.get(rel)
                if duration is None:
                    duration = mp4_duration_seconds(f)
                if duration and duration > 0:
                    file_entry["duration_seconds"] = round(duration, 3)
                    file_entry["duration"] = format_duration(duration)
                    total_duration += duration
                if is_three_cam:
                    parts = f.relative_to(emp_folder).parts
                    if len(parts) > 1:
                        pos = parts[0]
                        bp = by_position.setdefault(
                            pos, {"files": 0, "bytes": 0, "duration_seconds": 0.0},
                        )
                        bp["files"] += 1
                        bp["bytes"] += size
                        if duration and duration > 0:
                            bp["duration_seconds"] += duration
            files.append(file_entry)

        info["file_count"] = sum(1 for f in files if f["path"].lower().endswith(".mp4"))
        info["total_bytes"] = total_bytes
        info["total_gb"] = round(total_bytes / (1000 ** 3), 3)
        info["total_duration_seconds"] = round(total_duration, 3)
        info["total_duration"] = format_duration(total_duration)
        info["total_duration_hms"] = format_duration_hms(total_duration)
        info["files"] = files
        if is_three_cam:
            for pos, bp in by_position.items():
                bp["duration_seconds"] = round(bp["duration_seconds"], 3)
                bp["duration"] = format_duration(bp["duration_seconds"])
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
