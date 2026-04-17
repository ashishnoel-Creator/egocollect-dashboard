from __future__ import annotations

import csv
from pathlib import Path

from .manifest import load_manifest


def _ensure_reports_dir(ssd_root: Path) -> Path:
    d = ssd_root / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_summary_csv(ssd_root: Path) -> Path:
    manifest = load_manifest(ssd_root)
    out = _ensure_reports_dir(ssd_root) / "summary.csv"
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "date", "mode", "employee_id", "task_type",
            "session_number", "position", "file_count",
            "total_bytes", "created_at",
        ])
        for s in manifest.get("sessions", []):
            writer.writerow([
                s["collection_date"], s["mode"], s["employee_id"],
                s["task_type"], s["session_number"], s.get("position") or "",
                s["file_count"], s["total_bytes"], s["created_at"],
            ])
    return out


def write_date_csv(ssd_root: Path, collection_date: str) -> Path:
    manifest = load_manifest(ssd_root)
    out = _ensure_reports_dir(ssd_root) / f"{collection_date}.csv"
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "mode", "employee_id", "task_type", "session_number",
            "position", "file_count", "total_bytes", "created_at",
        ])
        for s in manifest.get("sessions", []):
            if s["collection_date"] != collection_date:
                continue
            writer.writerow([
                s["mode"], s["employee_id"], s["task_type"],
                s["session_number"], s.get("position") or "",
                s["file_count"], s["total_bytes"], s["created_at"],
            ])
    return out
