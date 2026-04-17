from __future__ import annotations

from pathlib import Path

from .models import CollectionMode


def session_folder(
    ssd_root: Path,
    mode: CollectionMode,
    collection_date: str,
    employee_id: str,
    task_type: str,
    session_number: int,
) -> Path:
    return (
        ssd_root
        / collection_date
        / mode.value
        / slugify(employee_id)
        / slugify(task_type)
        / f"session_{session_number:03d}"
    )


def next_session_number(
    ssd_root: Path,
    mode: CollectionMode,
    collection_date: str,
    employee_id: str,
    task_type: str,
) -> int:
    parent = (
        ssd_root
        / collection_date
        / mode.value
        / slugify(employee_id)
        / slugify(task_type)
    )
    if not parent.exists():
        return 1
    highest = 0
    for p in parent.iterdir():
        if p.is_dir() and p.name.startswith("session_"):
            try:
                n = int(p.name.split("_", 1)[1])
                highest = max(highest, n)
            except (IndexError, ValueError):
                pass
    return highest + 1


def slugify(value: str) -> str:
    cleaned = "".join(
        c if c.isalnum() or c in "-_." else "_"
        for c in value.strip()
    )
    return cleaned or "unknown"
