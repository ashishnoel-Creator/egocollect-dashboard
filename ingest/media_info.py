from __future__ import annotations

import struct
from pathlib import Path


def mp4_duration_seconds(path: Path) -> float | None:
    """Read duration from an MP4's `mvhd` atom. Returns None on any error.

    Pure Python, no ffprobe dependency. Walks top-level atoms until it
    finds `moov`, then scans inside for `mvhd` and divides duration by
    timescale. Handles both 32-bit and 64-bit atom sizes and both
    `mvhd` versions 0 and 1. Handles `moov` placed at end-of-file.
    """
    try:
        with path.open("rb") as f:
            file_size = f.seek(0, 2)
            f.seek(0)
            return _find_mvhd_duration(f, file_size)
    except (OSError, struct.error, ValueError):
        return None


def _find_mvhd_duration(f, file_size: int) -> float | None:
    pos = 0
    while pos < file_size:
        f.seek(pos)
        header = f.read(8)
        if len(header) < 8:
            return None
        size, atom_type = struct.unpack(">I4s", header)
        header_len = 8
        if size == 1:
            ext = f.read(8)
            if len(ext) < 8:
                return None
            size = struct.unpack(">Q", ext)[0]
            header_len = 16
        elif size == 0:
            size = file_size - pos
        if size < header_len:
            return None
        body_start = pos + header_len
        body_end = pos + size

        if atom_type == b"moov":
            return _scan_moov_for_mvhd(f, body_start, body_end)

        pos = body_end
    return None


def _scan_moov_for_mvhd(f, start: int, end: int) -> float | None:
    pos = start
    while pos < end:
        f.seek(pos)
        header = f.read(8)
        if len(header) < 8:
            return None
        size, atom_type = struct.unpack(">I4s", header)
        header_len = 8
        if size == 1:
            ext = f.read(8)
            if len(ext) < 8:
                return None
            size = struct.unpack(">Q", ext)[0]
            header_len = 16
        elif size == 0:
            size = end - pos
        if size < header_len:
            return None

        if atom_type == b"mvhd":
            return _read_mvhd(f, pos + header_len)

        pos += size
    return None


def _read_mvhd(f, body_start: int) -> float | None:
    f.seek(body_start)
    version_flags = f.read(4)
    if len(version_flags) < 4:
        return None
    version = version_flags[0]
    if version == 0:
        f.read(8)  # creation + modification (32-bit each)
        timescale_raw = f.read(4)
        duration_raw = f.read(4)
        if len(timescale_raw) < 4 or len(duration_raw) < 4:
            return None
        timescale = struct.unpack(">I", timescale_raw)[0]
        duration = struct.unpack(">I", duration_raw)[0]
    elif version == 1:
        f.read(16)  # creation + modification (64-bit each)
        timescale_raw = f.read(4)
        duration_raw = f.read(8)
        if len(timescale_raw) < 4 or len(duration_raw) < 8:
            return None
        timescale = struct.unpack(">I", timescale_raw)[0]
        duration = struct.unpack(">Q", duration_raw)[0]
    else:
        return None
    if timescale <= 0:
        return None
    return duration / timescale


def format_duration(seconds: float | None) -> str:
    """Human-readable duration like '1h 23m 45s' or '45s'. '—' if unknown."""
    if not seconds or seconds <= 0:
        return "—"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def format_duration_hms(seconds: float | None) -> str:
    """HH:MM:SS (empty string if unknown). Suitable for CSV columns."""
    if not seconds or seconds <= 0:
        return ""
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
