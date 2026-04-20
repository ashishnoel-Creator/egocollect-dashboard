from __future__ import annotations

import json
import socket
import sys
import threading
import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

from .config import app_paths
from .sync_outbox import SyncOutbox


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
    """Outbox-backed mirror of local manifest events to a shared Google Sheet.

    Every push writes an entry to a persistent JSONL outbox first, then wakes
    a background worker that drains the outbox to Google Drive. Offline pushes
    are preserved across app restarts and replayed when connectivity returns.
    """

    RETRY_INTERVAL_SECONDS = 30.0

    def __init__(self):
        self._client = None
        self._spreadsheet = None
        self._remote_lock = threading.Lock()
        self._outbox = SyncOutbox(app_paths().support_dir / "sync_outbox.jsonl")
        self._wake = threading.Event()
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self.status = SyncStatus()
        self.status.pending_jobs = self._outbox.count()

    def initialize(self) -> bool:
        if not GSPREAD_AVAILABLE:
            self.status = SyncStatus(
                available=False,
                last_error="gspread not installed",
                pending_jobs=self._outbox.count(),
            )
            return False

        connected = self._connect()
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()
        self._wake.set()
        return connected

    def shutdown(self) -> None:
        self._stop.set()
        self._wake.set()

    def _connect(self) -> bool:
        creds_path = credentials_path()
        if not creds_path.exists():
            self.status.available = False
            self.status.last_error = f"credentials not found at {creds_path}"
            return False
        try:
            creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
            self._client = gspread.authorize(creds)
            self._spreadsheet = self._client.open(SHEET_NAME)
            self._ensure_tabs()
            self.status.available = True
            self.status.spreadsheet_id = self._spreadsheet.id
            self.status.last_error = None
            return True
        except Exception as exc:
            self.status.available = False
            self.status.last_error = f"{type(exc).__name__}: {exc}"
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

    def push_ssd(self, manifest: dict) -> None:
        self._outbox.append("upsert_ssd", {"manifest": manifest})
        self.status.pending_jobs = self._outbox.count()
        self._wake.set()

    def push_session(self, session_record: dict, ssd_uuid: str, ssd_name: str) -> None:
        self._outbox.append("append_session", {
            "record": session_record,
            "ssd_uuid": ssd_uuid,
            "ssd_name": ssd_name,
        })
        self.status.pending_jobs = self._outbox.count()
        self._wake.set()

    def push_event(self, event_type: str, ssd_uuid: str, ssd_name: str, payload: dict) -> None:
        self._outbox.append("append_event", {
            "event_type": event_type,
            "ssd_uuid": ssd_uuid,
            "ssd_name": ssd_name,
            "payload": payload,
        })
        self.status.pending_jobs = self._outbox.count()
        self._wake.set()

    def sync_now(self) -> None:
        """Force an immediate drain attempt (also retries the connection)."""
        self._wake.set()

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
        return result

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=self.RETRY_INTERVAL_SECONDS)
            self._wake.clear()
            if self._stop.is_set():
                return
            self._drain_outbox()
            self.status.pending_jobs = self._outbox.count()

    def _drain_outbox(self) -> None:
        pending = self._outbox.read_all()
        if not pending:
            return
        if not self.status.available:
            if not self._connect():
                return
        done: set[str] = set()
        for entry in pending:
            try:
                self._dispatch(entry.get("op", ""), entry.get("args") or {})
                done.add(entry["id"])
            except Exception as exc:
                self.status.available = False
                self.status.last_error = (
                    f"{entry.get('op')}: {type(exc).__name__}: {exc}"
                )
                break
        if done:
            self._outbox.remove_ids(done)
            self.status.last_sync_at = _now()
            if not self.status.last_error or self.status.available:
                self.status.last_error = None

    def _dispatch(self, op: str, args: dict) -> None:
        if op == "upsert_ssd":
            self._upsert_ssd(args.get("manifest") or {})
        elif op == "append_session":
            self._append_session(
                args.get("record") or {},
                args.get("ssd_uuid", ""),
                args.get("ssd_name", ""),
            )
        elif op == "append_event":
            self._append_event(
                args.get("event_type", ""),
                args.get("ssd_uuid", ""),
                args.get("ssd_name", ""),
                args.get("payload") or {},
            )
        else:
            raise ValueError(f"unknown op: {op!r}")

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
        with self._remote_lock:
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
        with self._remote_lock:
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
        with self._remote_lock:
            ws.append_row(row, value_input_option="RAW")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
