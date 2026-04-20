from __future__ import annotations

import csv
from pathlib import Path

from .manifest import load_manifest
from .media_info import format_duration_hms


def _ensure_reports_dir(ssd_root: Path) -> Path:
    d = ssd_root / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


_SUMMARY_HEADERS = [
    "date", "mode", "employee_id", "task_type",
    "session_number", "position", "file_count",
    "total_bytes", "total_gb",
    "duration_hms", "duration_seconds",
    "created_at",
]


def _row_from_session(s: dict) -> list:
    total_bytes = int(s.get("total_bytes") or 0)
    duration = s.get("total_duration_seconds")
    return [
        s.get("collection_date", ""),
        s.get("mode", ""),
        s.get("employee_id", ""),
        s.get("task_type", ""),
        s.get("session_number", ""),
        s.get("position") or "",
        s.get("file_count", 0),
        total_bytes,
        round(total_bytes / (1000 ** 3), 3) if total_bytes else 0,
        format_duration_hms(duration),
        round(float(duration), 3) if duration else "",
        s.get("created_at", ""),
    ]


def write_summary_csv(ssd_root: Path) -> Path:
    manifest = load_manifest(ssd_root)
    out = _ensure_reports_dir(ssd_root) / "summary.csv"
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(_SUMMARY_HEADERS)
        for s in manifest.get("sessions", []):
            writer.writerow(_row_from_session(s))
    return out


def write_date_csv(ssd_root: Path, collection_date: str) -> Path:
    manifest = load_manifest(ssd_root)
    out = _ensure_reports_dir(ssd_root) / f"{collection_date}.csv"
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([h for h in _SUMMARY_HEADERS if h != "date"])
        for s in manifest.get("sessions", []):
            if s.get("collection_date") != collection_date:
                continue
            row = _row_from_session(s)
            writer.writerow(row[1:])
    return out
