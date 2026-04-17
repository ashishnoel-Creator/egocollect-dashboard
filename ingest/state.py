from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .config import SSD_FULL_THRESHOLD_PERCENT
from .copier import run_copy_batch, write_checksums_file
from .devices import VolumeInfo
from .ledger import record_ssd_snapshot
from .manifest import append_session, ensure_manifest
from .models import CameraPosition, CollectionMode, SessionRecord
from .paths import next_session_number, session_folder
from .reports import write_date_csv, write_summary_csv
from .scanner import scan_sd_for_mp4


STATUS_PREPARING = "preparing"
STATUS_RUNNING = "running"
STATUS_FINALIZING = "finalizing"
STATUS_DONE_PENDING_CLEAR = "done_pending_clear"
STATUS_CLEARED = "cleared"
STATUS_DONE_NO_CLEAR = "done_no_clear"
STATUS_FAILED = "failed"


@dataclass
class CopyInstance:
    id: str
    mode: CollectionMode
    collection_date: str
    employee_id: str
    task_type: str
    sd_sources: list[tuple[Path, CameraPosition | None]]
    ssd_root: Path
    session_dir: Path
    session_number: int
    total_files: int
    total_bytes: int
    done_files: int = 0
    status: str = STATUS_PREPARING
    log_lines: list[str] = field(default_factory=list)
    results: list = field(default_factory=list)
    error: str | None = None

    def title(self) -> str:
        mode_label = "single-cam" if self.mode == CollectionMode.SINGLE else "3-cam"
        return (
            f"Session {self.session_number:03d}  ·  "
            f"{self.employee_id}  ·  {self.task_type}  ·  "
            f"{self.collection_date}  ·  {mode_label}"
        )

    def is_active(self) -> bool:
        return self.status in (STATUS_PREPARING, STATUS_RUNNING, STATUS_FINALIZING)

    def target_dir(self, position: CameraPosition | None) -> Path:
        return self.session_dir if position is None else self.session_dir / position.value


class _CopyWorker(QThread):
    progress_signal = pyqtSignal(str, str, int, int)
    completed_signal = pyqtSignal(str, list)
    failed_signal = pyqtSignal(str, str)

    def __init__(self, inst_id: str, pairs: list[tuple[Path, Path]]):
        super().__init__()
        self.inst_id = inst_id
        self.pairs = pairs

    def run(self) -> None:
        try:
            def _on_progress(r, done, total):
                prefix = "OK  " if r.success else "FAIL"
                detail = f"  [{r.error}]" if r.error else ""
                self.progress_signal.emit(
                    self.inst_id,
                    f"{prefix}  {r.source.name}{detail}",
                    done, total,
                )

            results = run_copy_batch(self.pairs, progress=_on_progress)
            self.completed_signal.emit(self.inst_id, results)
        except Exception as exc:
            self.failed_signal.emit(self.inst_id, str(exc))


class AppState(QObject):
    ssd_changed = pyqtSignal()
    sds_changed = pyqtSignal()
    instance_added = pyqtSignal(str)
    instance_changed = pyqtSignal(str)
    instance_removed = pyqtSignal(str)
    ssd_full_warning = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.ssd_info: VolumeInfo | None = None
        self.instances: dict[str, CopyInstance] = {}
        self._sds_in_use: set[str] = set()
        self._workers: dict[str, _CopyWorker] = {}

    @property
    def sds_in_use(self) -> set[str]:
        return set(self._sds_in_use)

    def lock_ssd(self, info: VolumeInfo) -> None:
        self.ssd_info = info
        ensure_manifest(info.path, logical_name=info.label)
        self.ssd_changed.emit()

    def unlock_ssd(self) -> None:
        if self.has_active_instances():
            raise RuntimeError("Cannot unlock SSD while copies are running.")
        self.ssd_info = None
        self.ssd_changed.emit()

    def has_active_instances(self) -> bool:
        return any(i.is_active() for i in self.instances.values())

    def start_instance(
        self,
        mode: CollectionMode,
        collection_date: str,
        employee_id: str,
        task_type: str,
        sd_sources: list[tuple[Path, CameraPosition | None]],
    ) -> CopyInstance:
        if not self.ssd_info:
            raise RuntimeError("No destination SSD is locked.")
        ssd_root = self.ssd_info.path

        sess_n = next_session_number(ssd_root, mode, collection_date, employee_id, task_type)
        sess_dir = session_folder(ssd_root, mode, collection_date, employee_id, task_type, sess_n)

        pairs: list[tuple[Path, Path]] = []
        total_files = 0
        total_bytes = 0
        for sd, pos in sd_sources:
            scan = scan_sd_for_mp4(sd)
            if scan.count == 0:
                raise ValueError(f"No .MP4 files found under {sd}/DCIM.")
            target_dir = sess_dir if pos is None else sess_dir / pos.value
            target_dir.mkdir(parents=True, exist_ok=True)
            total_files += scan.count
            total_bytes += scan.total_bytes
            for src in scan.files:
                pairs.append((src, target_dir / src.name))

        free = shutil.disk_usage(ssd_root).free
        if free < total_bytes:
            raise RuntimeError(
                f"Not enough space on SSD ({_human(free)} free, "
                f"need {_human(total_bytes)})."
            )

        inst_id = uuid.uuid4().hex[:8]
        inst = CopyInstance(
            id=inst_id,
            mode=mode,
            collection_date=collection_date,
            employee_id=employee_id,
            task_type=task_type,
            sd_sources=sd_sources,
            ssd_root=ssd_root,
            session_dir=sess_dir,
            session_number=sess_n,
            total_files=total_files,
            total_bytes=total_bytes,
            status=STATUS_RUNNING,
        )
        self.instances[inst_id] = inst
        self._register_sds([sd for sd, _ in sd_sources])
        self.instance_added.emit(inst_id)

        worker = _CopyWorker(inst_id, pairs)
        worker.progress_signal.connect(self._on_worker_progress)
        worker.completed_signal.connect(self._on_worker_completed)
        worker.failed_signal.connect(self._on_worker_failed)
        self._workers[inst_id] = worker
        worker.start()
        return inst

    def resolve_clear(self, inst_id: str, clear_sds: bool) -> None:
        inst = self.instances.get(inst_id)
        if not inst or inst.status != STATUS_DONE_PENDING_CLEAR:
            return
        if clear_sds:
            cleared = 0
            for sd, _ in inst.sd_sources:
                cleared += _clear_dcim_contents(sd)
            inst.log_lines.append(f"Cleared {cleared} files from source SD(s).")
            inst.status = STATUS_CLEARED
        else:
            inst.status = STATUS_DONE_NO_CLEAR
        self._release_sds([sd for sd, _ in inst.sd_sources])
        self.instance_changed.emit(inst_id)

    def remove_instance(self, inst_id: str) -> None:
        inst = self.instances.get(inst_id)
        if not inst or inst.is_active():
            return
        self.instances.pop(inst_id, None)
        self._workers.pop(inst_id, None)
        self.instance_removed.emit(inst_id)

    def _register_sds(self, paths: Iterable[Path]) -> None:
        for p in paths:
            self._sds_in_use.add(str(p))
        self.sds_changed.emit()

    def _release_sds(self, paths: Iterable[Path]) -> None:
        for p in paths:
            self._sds_in_use.discard(str(p))
        self.sds_changed.emit()

    def _on_worker_progress(self, inst_id: str, line: str, done: int, total: int) -> None:
        inst = self.instances.get(inst_id)
        if not inst:
            return
        inst.done_files = done
        inst.log_lines.append(line)
        self.instance_changed.emit(inst_id)

    def _on_worker_completed(self, inst_id: str, results: list) -> None:
        inst = self.instances.get(inst_id)
        if not inst:
            return
        inst.results = results
        inst.status = STATUS_FINALIZING
        self.instance_changed.emit(inst_id)

        failures = [r for r in results if not r.success]
        if failures:
            inst.error = f"{len(failures)} file(s) failed checksum verification."
            inst.status = STATUS_FAILED
            self._release_sds([sd for sd, _ in inst.sd_sources])
            self.instance_changed.emit(inst_id)
            return

        for _, pos in inst.sd_sources:
            target_dir = inst.target_dir(pos)
            per = [r for r in results if r.destination.parent == target_dir]
            write_checksums_file(per, target_dir / "checksums.sha256")

        metadata = {
            "mode": inst.mode.value,
            "collection_date": inst.collection_date,
            "employee_id": inst.employee_id,
            "task_type": inst.task_type,
            "session_number": inst.session_number,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "sources": [
                {"path": str(sd), "position": pos.value if pos else None}
                for sd, pos in inst.sd_sources
            ],
            "file_count": len(results),
            "total_bytes": sum(r.size_bytes for r in results),
        }
        (inst.session_dir / "session.json").write_text(json.dumps(metadata, indent=2))

        manifest: dict = {}
        for sd, pos in inst.sd_sources:
            target_dir = inst.target_dir(pos)
            per = [r for r in results if r.destination.parent == target_dir]
            rec = SessionRecord(
                collection_date=inst.collection_date,
                mode=inst.mode.value,
                employee_id=inst.employee_id,
                task_type=inst.task_type,
                session_number=inst.session_number,
                position=pos.value if pos else None,
                relative_path=str(target_dir.relative_to(inst.ssd_root)),
                file_count=len(per),
                total_bytes=sum(r.size_bytes for r in per),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            manifest = append_session(inst.ssd_root, rec)

        record_ssd_snapshot(manifest, inst.ssd_root)
        write_summary_csv(inst.ssd_root)
        write_date_csv(inst.ssd_root, inst.collection_date)

        inst.status = STATUS_DONE_PENDING_CLEAR
        self.instance_changed.emit(inst_id)

        usage = shutil.disk_usage(inst.ssd_root)
        pct_free = 100.0 * usage.free / usage.total if usage.total else 100.0
        if pct_free < SSD_FULL_THRESHOLD_PERCENT:
            self.ssd_full_warning.emit(pct_free)

    def _on_worker_failed(self, inst_id: str, msg: str) -> None:
        inst = self.instances.get(inst_id)
        if not inst:
            return
        inst.error = msg
        inst.status = STATUS_FAILED
        self._release_sds([sd for sd, _ in inst.sd_sources])
        self.instance_changed.emit(inst_id)


def _clear_dcim_contents(sd_root: Path) -> int:
    dcim = sd_root / "DCIM"
    if not dcim.exists():
        return 0
    removed = 0
    for path in dcim.rglob("*"):
        if path.is_file():
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
