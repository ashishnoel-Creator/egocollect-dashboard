from __future__ import annotations

import hashlib
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable

from .config import MAX_COPY_WORKERS
from .media_info import mp4_duration_seconds
from .models import FileCopyResult


_CHUNK = 4 * 1024 * 1024


def sha256_file(path: Path, chunk_size: int = _CHUNK) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_and_verify(
    source: Path,
    destination: Path,
    chunk_size: int = _CHUNK,
    on_chunk: Callable[[int], None] | None = None,
) -> FileCopyResult:
    """Stream source -> destination while hashing, then verify by re-reading destination.

    `on_chunk(bytes_in_this_chunk)` fires on every chunk written for live progress.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        h_src = hashlib.sha256()
        with source.open("rb") as src, destination.open("wb") as dst:
            while True:
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                h_src.update(chunk)
                dst.write(chunk)
                if on_chunk:
                    on_chunk(len(chunk))
            dst.flush()
            try:
                os.fsync(dst.fileno())
            except OSError:
                pass

        src_hash = h_src.hexdigest()
        dst_hash = sha256_file(destination, chunk_size)

        if src_hash != dst_hash:
            return FileCopyResult(
                source=source,
                destination=destination,
                size_bytes=destination.stat().st_size,
                sha256=dst_hash,
                success=False,
                error=f"checksum mismatch: src={src_hash[:12]} dst={dst_hash[:12]}",
            )
        duration = None
        if destination.suffix.upper() == ".MP4":
            duration = mp4_duration_seconds(destination)
        return FileCopyResult(
            source=source,
            destination=destination,
            size_bytes=destination.stat().st_size,
            sha256=dst_hash,
            success=True,
            duration_seconds=duration,
        )
    except Exception as exc:
        return FileCopyResult(
            source=source,
            destination=destination,
            size_bytes=0,
            sha256="",
            success=False,
            error=str(exc),
        )


FileProgressCallback = Callable[[FileCopyResult, int, int], None]
BytesProgressCallback = Callable[[int, int], None]


def run_copy_batch(
    pairs: list[tuple[Path, Path]],
    progress: FileProgressCallback | None = None,
    bytes_progress: BytesProgressCallback | None = None,
    max_workers: int = MAX_COPY_WORKERS,
) -> list[FileCopyResult]:
    """Copy `(src, dst)` pairs in parallel.

    `progress(result, files_done, files_total)` fires once per file as it
    finishes. `bytes_progress(bytes_done, bytes_total)` fires often during
    each file's copy (throttled across the whole batch to ~10 Hz).
    """
    total_bytes = 0
    for src, _ in pairs:
        try:
            total_bytes += src.stat().st_size
        except OSError:
            pass

    bytes_done = [0]
    bytes_lock = threading.Lock()
    last_emit = [0.0]
    emit_lock = threading.Lock()

    def emit_bytes_throttled() -> None:
        if not bytes_progress:
            return
        now = time.monotonic()
        with emit_lock:
            if now - last_emit[0] < 0.1:
                return
            last_emit[0] = now
        bytes_progress(bytes_done[0], total_bytes)

    def make_chunk_cb():
        def cb(n: int) -> None:
            with bytes_lock:
                bytes_done[0] += n
            emit_bytes_throttled()
        return cb

    results: list[FileCopyResult | None] = [None] * len(pairs)
    files_done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {}
        for i, (src, dst) in enumerate(pairs):
            fut = executor.submit(copy_and_verify, src, dst, _CHUNK, make_chunk_cb())
            future_to_idx[fut] = i
        for fut in as_completed(future_to_idx):
            i = future_to_idx[fut]
            results[i] = fut.result()
            files_done += 1
            if progress:
                progress(results[i], files_done, len(pairs))

    if bytes_progress:
        bytes_progress(bytes_done[0], total_bytes)
    return [r for r in results if r is not None]


def write_checksums_file(results: Iterable[FileCopyResult], out_path: Path) -> None:
    with out_path.open("w") as fh:
        for r in results:
            if r.success:
                fh.write(f"{r.sha256}  {r.destination.name}\n")
