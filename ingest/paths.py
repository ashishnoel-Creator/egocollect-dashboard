from __future__ import annotations

from pathlib import Path

from .models import CollectionMode


MODE_FOLDERS = ("single-camera", "3-camera-array")


def emp_folder(
    ssd_root: Path,
    mode: CollectionMode,
    collection_date: str,
    task_type: str,
    employee_id: str,
) -> Path:
    """Final destination folder. Files land directly inside (or under
    a Position subfolder for 3-camera-array)."""
    return (
        ssd_root
        / mode.value
        / collection_date
        / slugify(task_type)
        / slugify(employee_id)
    )


def ensure_mode_folders(ssd_root: Path) -> None:
    """Create the two top-level mode folders if they don't exist."""
    for name in MODE_FOLDERS:
        try:
            (ssd_root / name).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def copy_ordinal_for(
    sessions: list[dict],
    mode: CollectionMode,
    collection_date: str,
    task_type: str,
    employee_id: str,
) -> int:
    """Number of prior copies into this same emp folder + 1."""
    n = 1
    for s in sessions:
        if (
            s.get("mode") == mode.value
            and s.get("collection_date") == collection_date
            and s.get("task_type") == task_type
            and s.get("employee_id") == employee_id
        ):
            n += 1
    return n


def slugify(value: str) -> str:
    cleaned = "".join(
        c if c.isalnum() or c in "-_." else "_"
        for c in value.strip()
    )
    return cleaned or "unknown"
