from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CollectionMode(str, Enum):
    SINGLE = "single-camera"
    THREE_CAM = "3-camera-array"


class CameraPosition(str, Enum):
    LEFT = "Left"
    RIGHT = "Right"
    HEAD = "Head"


@dataclass
class CopyTarget:
    source_sd: Path
    destination_dir: Path
    position: CameraPosition | None = None


@dataclass
class FileCopyResult:
    source: Path
    destination: Path
    size_bytes: int
    sha256: str
    success: bool
    error: str | None = None


@dataclass
class SessionRecord:
    collection_date: str
    mode: str
    employee_id: str
    task_type: str
    session_number: int
    position: str | None
    relative_path: str
    file_count: int
    total_bytes: int
    created_at: str
    source_sd_label: str | None = None
