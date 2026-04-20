from __future__ import annotations

import json
import queue
import socket
import sys
import threading
import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False


SHEET_NAME = "EgoCollect_Log"
DRIVE_FOLDER_ID = "10kMVkqe40hzGDV8c87BIgdXcrfZDTHE6"
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

SSD_HEADERS = [
    "ssd_uuid", "assigned_name", "serial_number", "volume_uuid",
    "media_name", "capacity_label", "total_bytes", "registered_at",
    "last_seen_at", "last_seen_machine", "session_count",
    "bytes_archived", "duration_hms_archived", "duration_seconds_archived",
    "last_event_type",
]

SESSION_HEADERS = [
    "created_at", "ssd_uuid", "ssd_name", "collection_date", "mode",
    "employee_id", "task_type", "session_number", "position",
    "file_count", "total_bytes",
    "duration_hms", "duration_seconds",
    "machine",
]

EVENT_HEADERS = [
    "timestamp", "event_id", "ssd_uuid", "ssd_name", "type",
    "machine", "payload",
]


def credentials_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "secrets" / "sheet_service_account.json"


def machine_name() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown-host"


def sheet_url(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"


@dataclass
class SyncStatus:
    available: bool = False
    spreadsheet_id: str | None = None
    last_sync_at: str | None = None
    last_error: str | None = None
    pending_jobs: int = 0


class DriveSync:
    """Background-threaded mirror of local manifest events to a Google Sheet."""

    def __init__(self):
        self._client = None
        self._spreadsheet = None
        self._lock = threading.Lock()
        self._queue: "queue.Queue" = queue.Queue()
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self.status = SyncStatus()

    def initialize(self) -> bool:
        if not GSPREAD_AVAILABLE:
            self.status = SyncStatus(available=False, last_error="gspread not installed")
            return False
        creds_path = credentials_path()
        if not creds_path.exists():
            self.status = SyncStatus(
                available=False,
                last_error=f"credentials not found at {creds_path}",
            )
            return False
        try:
            creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
            self._client = gspread.authorize(creds)
            self._spreadsheet = self._client.open(SHEET_NAME)
            self._ensure_tabs()
            self.status = SyncStatus(
                available=True,
                spreadsheet_id=self._spreadsheet.id,
                last_sync_at=_now(),
            )
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()
            return True
        except Exception as exc:
            self.status = SyncStatus(available=False, last_error=f"{type(exc).__name__}: {exc}")
            return False

    def _ensure_tabs(self) -> None:
        configs = [
            ("SSDs", SSD_HEADERS),
            ("Sessions", SESSION_HEADERS),
            ("Events", EVENT_HEADERS),
        ]
        existing = {ws.title for ws in self._spreadsheet.worksheets()}
        for name, headers in configs:
            if name not in existing:
                ws = self._spreadsheet.add_worksheet(
                    title=name, rows=1000, cols=max(len(headers), 5),
                )
                ws.update("A1", [headers])
            else:
                ws = self._spreadsheet.worksheet(name)
                first_row = ws.row_values(1)
                if first_row != headers:
                    ws.update("A1", [headers])

        if "Sheet1" in existing and {"SSDs", "Sessions", "Events"}.issubset(existing | {"SSDs", "Sessions", "Events"}):
            try:
                self._spreadsheet.del_worksheet(self._spreadsheet.worksheet("Sheet1"))
            except Exception:
                pass

    def shutdown(self) -> None:
        self._stop.set()
        self._queue.put(None)

    def push_ssd(self, manifest: dict) -> None:
        self._enqueue(("upsert_ssd", manifest))

    def push_session(self, session_record: dict, ssd_uuid: str, ssd_name: str) -> None:
        self._enqueue(("append_session", session_record, ssd_uuid, ssd_name))

    def push_event(self, event_type: str, ssd_uuid: str, ssd_name: str, payload: dict) -> None:
        self._enqueue(("append_event", event_type, ssd_uuid, ssd_name, payload))

    def pull_all(self) -> dict:
        if not self.status.available or not self._spreadsheet:
            return {"ssds": [], "sessions": [], "events": []}
        result = {}
        for tab in ("SSDs", "Sessions", "Events"):
            try:
                ws = self._spreadsheet.worksheet(tab)
                result[tab.lower()] = ws.get_all_records()
            except Exception as exc:
                self.status.last_error = f"pull {tab}: {exc}"
                result[tab.lower()] = []
        self.status.last_sync_at = _now()
        return result

    def _enqueue(self, job: tuple) -> None:
        if not self.status.available:
            return
        self._queue.put(job)
        self.status.pending_jobs = self._queue.qsize()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if job is None:
                return
            try:
                self._dispatch(job)
                self.status.last_sync_at = _now()
                self.status.last_error = None
            except Exception as exc:
                self.status.last_error = f"{job[0]}: {type(exc).__name__}: {exc}"
            finally:
                self.status.pending_jobs = self._queue.qsize()

    def _dispatch(self, job: tuple) -> None:
        op = job[0]
        if op == "upsert_ssd":
            self._upsert_ssd(job[1])
        elif op == "append_session":
            self._append_session(job[1], job[2], job[3])
        elif op == "append_event":
            self._append_event(job[1], job[2], job[3], job[4])

    def _upsert_ssd(self, manifest: dict) -> None:
        from .device_info import size_bucket
        from .media_info import format_duration_hms
        ws = self._spreadsheet.worksheet("SSDs")
        ssd_uuid = manifest.get("ssd_uuid", "")
        sessions = manifest.get("sessions", []) or []
        events = manifest.get("events", []) or []
        last_event_type = events[-1].get("type") if events else ""
        total_duration = sum(
            float(s.get("total_duration_seconds") or 0) for s in sessions
        )
        row = [
            ssd_uuid,
            manifest.get("assigned_name") or "",
            manifest.get("serial_number") or "",
            manifest.get("volume_uuid") or "",
            manifest.get("media_name") or "",
            size_bucket(manifest.get("total_bytes") or 0),
            int(manifest.get("total_bytes") or 0),
            manifest.get("registered_at") or "",
            _now(),
            machine_name(),
            len(sessions),
            sum(int(s.get("total_bytes") or 0) for s in sessions),
            format_duration_hms(total_duration),
            round(total_duration, 3) if total_duration else 0,
            last_event_type,
        ]
        with self._lock:
            try:
                cell = ws.find(ssd_uuid, in_column=1)
            except gspread.exceptions.CellNotFound:
                cell = None
            except Exception:
                cell = None
            if cell:
                ws.update(f"A{cell.row}", [row], value_input_option="RAW")
            else:
                ws.append_row(row, value_input_option="RAW")

    def _append_session(self, record: dict, ssd_uuid: str, ssd_name: str) -> None:
        from .media_info import format_duration_hms
        ws = self._spreadsheet.worksheet("Sessions")
        duration = record.get("total_duration_seconds")
        row = [
            record.get("created_at") or _now(),
            ssd_uuid,
            ssd_name,
            record.get("collection_date") or "",
            record.get("mode") or "",
            record.get("employee_id") or "",
            record.get("task_type") or "",
            int(record.get("session_number") or 0),
            record.get("position") or "",
            int(record.get("file_count") or 0),
            int(record.get("total_bytes") or 0),
            format_duration_hms(duration),
            round(float(duration), 3) if duration else "",
            machine_name(),
        ]
        with self._lock:
            ws.append_row(row, value_input_option="RAW")

    def _append_event(self, event_type: str, ssd_uuid: str, ssd_name: str, payload: dict) -> None:
        ws = self._spreadsheet.worksheet("Events")
        row = [
            _now(),
            _uuid.uuid4().hex,
            ssd_uuid,
            ssd_name,
            event_type,
            machine_name(),
            json.dumps(payload, default=str),
        ]
        with self._lock:
            ws.append_row(row, value_input_option="RAW")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
