from __future__ import annotations

import shutil
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .config import SSD_FULL_THRESHOLD_PERCENT
from .copier import run_copy_batch, write_checksums_file
from .device_info import DriveInfo, get_drive_info
from .devices import VolumeInfo
from .drive_sync import DriveSync
from .folder_info import update_folder_info
from .ledger import find_by_identity, record_ssd_snapshot
from .manifest import (
    append_event, append_session, load_manifest, migrate_manifest,
    new_manifest, save_manifest,
)
from .models import CameraPosition, CollectionMode, SessionRecord
from .naming import generate_assigned_name
from .paths import (
    MODE_FOLDERS, copy_ordinal_for, emp_folder, ensure_mode_folders,
)
from .reports import write_date_csv, write_summary_csv
from .scanner import scan_sd_for_mp4


STATUS_PREPARING = "preparing"
STATUS_RUNNING = "running"
STATUS_FINALIZING = "finalizing"
STATUS_DONE_PENDING_CLEAR = "done_pending_clear"
STATUS_CLEARED = "cleared"
STATUS_DONE_NO_CLEAR = "done_no_clear"
STATUS_FAILED = "failed"


class RegistrationAction(str, Enum):
    NEW = "new"
    POST_REFORMAT = "post_reformat"
    RECONNECT = "reconnect"


@dataclass
class SSDInspection:
    volume: VolumeInfo
    drive_info: DriveInfo
    existing_manifest: dict | None
    prior_ledger_entry: dict | None
    proposed_name: str

    @property
    def action(self) -> RegistrationAction:
        if self.existing_manifest and self.existing_manifest.get("assigned_name"):
            return RegistrationAction.RECONNECT
        if self.prior_ledger_entry and self.prior_ledger_entry.get("assigned_name"):
            return RegistrationAction.POST_REFORMAT
        return RegistrationAction.NEW

    @property
    def existing_name(self) -> str | None:
        if self.existing_manifest:
            return self.existing_manifest.get("assigned_name")
        if self.prior_ledger_entry:
            return self.prior_ledger_entry.get("assigned_name")
        return None


def inspect_ssd(volume: VolumeInfo) -> SSDInspection:
    drive_info = get_drive_info(volume.path)
    manifest = load_manifest(volume.path)
    prior = None
    if not manifest:
        ident = drive_info.identity_key()
        if ident:
            prior = find_by_identity(ident)
    return SSDInspection(
        volume=volume,
        drive_info=drive_info,
        existing_manifest=manifest or None,
        prior_ledger_entry=prior,
        proposed_name=generate_assigned_name(drive_info.total_bytes or volume.total_bytes),
    )


@dataclass
class CopyInstance:
    id: str
    mode: CollectionMode
    collection_date: str
    employee_id: str
    task_type: str
    sd_sources: list[tuple[Path, CameraPosition | None]]
    ssd_root: Path
    emp_folder: Path
    copy_ordinal: int
    total_files: int
    total_bytes: int
    done_files: int = 0
    done_bytes: int = 0
    status: str = STATUS_PREPARING
    log_lines: list[str] = field(default_factory=list)
    results: list = field(default_factory=list)
    error: str | None = None

    def title(self) -> str:
        mode_label = "single-cam" if self.mode == CollectionMode.SINGLE else "3-cam"
        return (
            f"{mode_label}  ·  {self.collection_date}  ·  "
            f"{self.task_type}  ·  {self.employee_id}  ·  "
            f"copy #{self.copy_ordinal}"
        )

    def is_active(self) -> bool:
        return self.status in (STATUS_PREPARING, STATUS_RUNNING, STATUS_FINALIZING)

    def target_dir(self, position: CameraPosition | None) -> Path:
        return self.emp_folder if position is None else self.emp_folder / position.value


class _CopyWorker(QThread):
    progress_signal = pyqtSignal(str, str, int, int)
    bytes_signal = pyqtSignal(str, int, int)
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

            def _on_bytes(done, total):
                self.bytes_signal.emit(self.inst_id, done, total)

            results = run_copy_batch(
                self.pairs, progress=_on_progress, bytes_progress=_on_bytes,
            )
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
        self.ssd_drive_info: DriveInfo | None = None
        self.ssd_assigned_name: str | None = None
        self.instances: dict[str, CopyInstance] = {}
        self._sds_in_use: set[str] = set()
        self._workers: dict[str, _CopyWorker] = {}
        self.drive_sync: DriveSync | None = None

    def attach_drive_sync(self, ds: DriveSync) -> None:
        self.drive_sync = ds

    @property
    def sds_in_use(self) -> set[str]:
        return set(self._sds_in_use)

    def register_or_reconnect_ssd(
        self, inspection: SSDInspection, confirmed_name: str,
    ) -> None:
        vol = inspection.volume
        drive_info = inspection.drive_info
        manifest = inspection.existing_manifest

        if inspection.action == RegistrationAction.RECONNECT and manifest:
            manifest = migrate_manifest(manifest, drive_info)
            save_manifest(vol.path, manifest)
            append_event(vol.path, "reconnected", {
                "mount_point": str(vol.path),
                "assigned_name": manifest.get("assigned_name"),
            })
        else:
            manifest = new_manifest(drive_info, confirmed_name)
            if inspection.action == RegistrationAction.POST_REFORMAT:
                if inspection.prior_ledger_entry:
                    manifest["ssd_uuid"] = inspection.prior_ledger_entry.get(
                        "ssd_uuid", manifest["ssd_uuid"],
                    )
                    manifest["registered_at"] = inspection.prior_ledger_entry.get(
                        "registered_at", manifest["registered_at"],
                    )
            save_manifest(vol.path, manifest)
            event_type = (
                "restored_after_reformat"
                if inspection.action == RegistrationAction.POST_REFORMAT
                else "registered"
            )
            append_event(vol.path, event_type, {
                "assigned_name": confirmed_name,
                "serial_number": drive_info.serial_number,
                "volume_uuid": drive_info.volume_uuid,
                "total_bytes": drive_info.total_bytes,
                "mount_point": str(vol.path),
            })

        ensure_mode_folders(vol.path)

        manifest = load_manifest(vol.path)
        record_ssd_snapshot(manifest, vol.path)

        if self.drive_sync:
            self.drive_sync.push_ssd(manifest)
            last = (manifest.get("events") or [{}])[-1]
            self.drive_sync.push_event(
                last.get("type", "connected"),
                manifest.get("ssd_uuid", ""),
                manifest.get("assigned_name", ""),
                last.get("data", {}),
            )

        self.ssd_info = vol
        self.ssd_drive_info = drive_info
        self.ssd_assigned_name = manifest.get("assigned_name")
        self.ssd_changed.emit()

    def unlock_ssd(self) -> None:
        if self.has_active_instances():
            raise RuntimeError("Cannot unlock SSD while copies are running.")
        self.ssd_info = None
        self.ssd_drive_info = None
        self.ssd_assigned_name = None
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

        manifest = load_manifest(ssd_root)
        ordinal = copy_ordinal_for(
            manifest.get("sessions", []),
            mode, collection_date, task_type, employee_id,
        )
        target_emp = emp_folder(
            ssd_root, mode, collection_date, task_type, employee_id,
        )
        target_emp.mkdir(parents=True, exist_ok=True)

        pairs: list[tuple[Path, Path]] = []
        total_files = 0
        total_bytes = 0
        for sd, pos in sd_sources:
            scan = scan_sd_for_mp4(sd)
            if scan.count == 0:
                raise ValueError(f"No .MP4 files found under {sd}/DCIM.")
            target_dir = target_emp if pos is None else target_emp / pos.value
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
            emp_folder=target_emp,
            copy_ordinal=ordinal,
            total_files=total_files,
            total_bytes=total_bytes,
            status=STATUS_RUNNING,
        )
        inst.log_lines.append(
            f"Starting copy of {total_files} files ({_human(total_bytes)}) "
            f"into {target_emp}"
        )
        self.instances[inst_id] = inst
        self._register_sds([sd for sd, _ in sd_sources])
        self.instance_added.emit(inst_id)

        worker = _CopyWorker(inst_id, pairs)
        worker.progress_signal.connect(self._on_worker_progress)
        worker.bytes_signal.connect(self._on_worker_bytes)
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

    def clear_ssd_data(self) -> dict:
        """Wipe everything inside the two mode folders. Preserve mode folders,
        manifest, reports, and SSD identity. Logs an `ssd_cleared` event.
        """
        if not self.ssd_info:
            raise RuntimeError("No SSD is locked.")
        if self.has_active_instances():
            raise RuntimeError("Finish active copies before clearing the SSD.")

        ssd_root = self.ssd_info.path
        manifest_before = load_manifest(ssd_root)

        bytes_deleted = 0
        files_deleted = 0
        sessions_deleted = len(manifest_before.get("sessions", []))
        dates_seen: set[str] = set()
        modes_seen: set[str] = set()
        emp_seen: set[str] = set()

        for mode_name in MODE_FOLDERS:
            mode_dir = ssd_root / mode_name
            if not mode_dir.is_dir():
                continue
            for child in list(mode_dir.iterdir()):
                if child.is_dir() and _looks_like_date(child.name):
                    dates_seen.add(child.name)
                if child.is_dir():
                    for sub in child.iterdir():
                        if sub.is_dir():
                            for emp in sub.iterdir():
                                if emp.is_dir():
                                    emp_seen.add(emp.name)
                for path in child.rglob("*"):
                    if path.is_file():
                        try:
                            bytes_deleted += path.stat().st_size
                            files_deleted += 1
                        except OSError:
                            pass
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    try:
                        child.unlink()
                    except OSError:
                        pass
            modes_seen.add(mode_name)

        manifest_before["sessions"] = []
        save_manifest(ssd_root, manifest_before)
        summary = {
            "files_deleted": files_deleted,
            "bytes_deleted": bytes_deleted,
            "gb_deleted": round(bytes_deleted / (1000 ** 3), 3),
            "sessions_deleted": sessions_deleted,
            "dates_deleted": sorted(dates_seen),
            "modes_deleted": sorted(modes_seen),
            "employees_deleted": sorted(emp_seen),
            "cleared_at": datetime.now(timezone.utc).isoformat(),
            "machine": _machine(),
        }
        append_event(ssd_root, "ssd_cleared", summary)
        manifest_after = load_manifest(ssd_root)
        record_ssd_snapshot(manifest_after, ssd_root)

        if self.drive_sync:
            self.drive_sync.push_ssd(manifest_after)
            self.drive_sync.push_event(
                "ssd_cleared",
                manifest_after.get("ssd_uuid", ""),
                manifest_after.get("assigned_name", ""),
                summary,
            )
        return summary

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

    def _on_worker_bytes(self, inst_id: str, done: int, total: int) -> None:
        inst = self.instances.get(inst_id)
        if not inst:
            return
        inst.done_bytes = done
        if total and total != inst.total_bytes:
            inst.total_bytes = total
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

        is_three_cam = inst.mode == CollectionMode.THREE_CAM
        info = update_folder_info(
            emp_folder=inst.emp_folder,
            mode=inst.mode.value,
            collection_date=inst.collection_date,
            task_type=inst.task_type,
            employee_id=inst.employee_id,
            ssd_assigned_name=self.ssd_assigned_name or "",
            ssd_serial_number=(
                self.ssd_drive_info.serial_number if self.ssd_drive_info else None
            ),
            machine=_machine(),
            is_three_cam=is_three_cam,
        )
        from .media_info import format_duration as _fmt_dur
        instance_duration = sum(
            (r.duration_seconds or 0.0) for r in results if r.duration_seconds
        )
        inst.log_lines.append(
            f"Copied {len(results)} files  ·  {_fmt_dur(instance_duration)} of video "
            f"({_human(sum(r.size_bytes for r in results))})"
        )
        inst.log_lines.append(
            f"info.json updated  ·  total in folder: "
            f"{info.get('file_count', 0)} files  ·  "
            f"{info.get('total_gb', 0)} GB  ·  "
            f"{info.get('total_duration', '—')}"
        )

        manifest: dict = {}
        for sd, pos in inst.sd_sources:
            target_dir = inst.target_dir(pos)
            per = [r for r in results if r.destination.parent == target_dir]
            per_duration = sum(
                (r.duration_seconds or 0.0) for r in per if r.duration_seconds
            )
            rec = SessionRecord(
                collection_date=inst.collection_date,
                mode=inst.mode.value,
                employee_id=inst.employee_id,
                task_type=inst.task_type,
                session_number=inst.copy_ordinal,
                position=pos.value if pos else None,
                relative_path=str(target_dir.relative_to(inst.ssd_root)),
                file_count=len(per),
                total_bytes=sum(r.size_bytes for r in per),
                created_at=datetime.now(timezone.utc).isoformat(),
                total_duration_seconds=(
                    round(per_duration, 3) if per_duration > 0 else None
                ),
            )
            manifest = append_session(inst.ssd_root, rec)

        record_ssd_snapshot(manifest, inst.ssd_root)
        write_summary_csv(inst.ssd_root)
        write_date_csv(inst.ssd_root, inst.collection_date)

        if self.drive_sync:
            ssd_name = manifest.get("assigned_name", "")
            ssd_uuid = manifest.get("ssd_uuid", "")
            self.drive_sync.push_ssd(manifest)
            for s in manifest.get("sessions", [])[-len(inst.sd_sources):]:
                self.drive_sync.push_session(s, ssd_uuid, ssd_name)
            total_duration = sum(
                (r.duration_seconds or 0.0) for r in results if r.duration_seconds
            )
            from .media_info import format_duration
            self.drive_sync.push_event(
                "copy_session", ssd_uuid, ssd_name,
                {
                    "copy_ordinal": inst.copy_ordinal,
                    "collection_date": inst.collection_date,
                    "mode": inst.mode.value,
                    "employee_id": inst.employee_id,
                    "task_type": inst.task_type,
                    "file_count": len(results),
                    "total_bytes": sum(r.size_bytes for r in results),
                    "total_gb": round(
                        sum(r.size_bytes for r in results) / (1000 ** 3), 3,
                    ),
                    "total_duration_seconds": round(total_duration, 3),
                    "total_duration": format_duration(total_duration),
                },
            )

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


def _looks_like_date(name: str) -> bool:
    import re
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", name))


def _machine() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
