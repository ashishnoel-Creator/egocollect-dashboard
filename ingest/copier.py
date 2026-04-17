from __future__ import annotations

import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable

from .config import MAX_COPY_WORKERS
from .models import FileCopyResult


_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_and_verify(source: Path, destination: Path) -> FileCopyResult:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        source_hash = sha256_file(source)
        shutil.copy2(source, destination)
        dest_hash = sha256_file(destination)
        if source_hash != dest_hash:
            return FileCopyResult(
                source=source,
                destination=destination,
                size_bytes=destination.stat().st_size,
                sha256=dest_hash,
                success=False,
                error=f"checksum mismatch: src={source_hash[:12]} dst={dest_hash[:12]}",
            )
        return FileCopyResult(
            source=source,
            destination=destination,
            size_bytes=destination.stat().st_size,
            sha256=dest_hash,
            success=True,
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


ProgressCallback = Callable[[FileCopyResult, int, int], None]


def run_copy_batch(
    pairs: list[tuple[Path, Path]],
    progress: ProgressCallback | None = None,
    max_workers: int = MAX_COPY_WORKERS,
) -> list[FileCopyResult]:
    results: list[FileCopyResult] = []
    total = len(pairs)
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(copy_and_verify, src, dst): (src, dst)
            for src, dst in pairs
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            done += 1
            if progress:
                progress(result, done, total)
    return results


def write_checksums_file(results: Iterable[FileCopyResult], out_path: Path) -> None:
    with out_path.open("w") as fh:
        for r in results:
            if r.success:
                fh.write(f"{r.sha256}  {r.destination.name}\n")
