from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ScanResult:
    files: list[Path] = field(default_factory=list)
    total_bytes: int = 0

    @property
    def count(self) -> int:
        return len(self.files)


def scan_sd_for_mp4(sd_root: Path) -> ScanResult:
    dcim = sd_root / "DCIM"
    if not dcim.is_dir():
        return ScanResult()

    files: list[Path] = []
    total = 0
    for path in dcim.rglob("*"):
        if path.is_file() and path.suffix.upper() == ".MP4":
            files.append(path)
            try:
                total += path.stat().st_size
            except OSError:
                pass
    files.sort()
    return ScanResult(files=files, total_bytes=total)
