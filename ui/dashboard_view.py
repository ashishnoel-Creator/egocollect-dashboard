from __future__ import annotations

from datetime import datetime, timezone

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ingest.ledger import load_ledger
from ingest.media_info import format_duration, format_duration_hms
from ingest.state import AppState


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


VIEW_LOCAL = "local"
VIEW_TEAM = "team"


class _DrivePullWorker(QThread):
    finished_ok = pyqtSignal(dict)
    errored = pyqtSignal(str)

    def __init__(self, drive_sync):
        super().__init__()
        self.drive_sync = drive_sync

    def run(self):
        try:
            data = self.drive_sync.pull_all()
            self.finished_ok.emit(data)
        except Exception as exc:
            self.errored.emit(str(exc))


_HEADERS = [
    "SSD", "Date", "Mode", "Employee", "Task",
    "Session", "Position", "Files", "Duration", "Size", "Machine",
]


class DashboardView(QWidget):
    def __init__(self, app_state: AppState | None = None):
        super().__init__()
        self.app_state = app_state
        self._team_data: dict | None = None
        self._pull_worker: _DrivePullWorker | None = None
        self._build()
        if app_state is not None:
            app_state.instance_changed.connect(lambda _: self._maybe_refresh())
            app_state.instance_added.connect(lambda _: self._maybe_refresh())
            app_state.instance_removed.connect(lambda _: self._maybe_refresh())
            app_state.ssd_changed.connect(self._maybe_refresh)
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(5000)
        self._auto_timer.timeout.connect(self._maybe_refresh)
        self._auto_timer.start()
        self.refresh()

    def _maybe_refresh(self) -> None:
        if not self.isVisible():
            return
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("All ingested sessions")
        title.setObjectName("TitleLabel")
        header.addWidget(title)
        header.addStretch()

        self.view_combo = QComboBox()
        self.view_combo.addItem("Team (synced)", VIEW_TEAM)
        self.view_combo.addItem("This laptop only", VIEW_LOCAL)
        self.view_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self.view_combo)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)
        root.addLayout(header)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("MutedLabel")
        root.addWidget(self.summary_label)

        self.table = QTableWidget(0, len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table, 1)

    def _current_view(self) -> str:
        return self.view_combo.currentData() or VIEW_TEAM

    def refresh(self) -> None:
        if self._current_view() == VIEW_TEAM and self._can_use_drive():
            self._refresh_from_drive()
        else:
            self._refresh_from_local()

    def _can_use_drive(self) -> bool:
        return (
            self.app_state is not None
            and self.app_state.drive_sync is not None
            and self.app_state.drive_sync.status.available
        )

    def _refresh_from_drive(self) -> None:
        ds = self.app_state.drive_sync
        self.summary_label.setText("Pulling from Google Sheet…")
        self.refresh_btn.setEnabled(False)
        self._pull_worker = _DrivePullWorker(ds)
        self._pull_worker.finished_ok.connect(self._on_pull_ok)
        self._pull_worker.errored.connect(self._on_pull_error)
        self._pull_worker.start()

    def _on_pull_ok(self, data: dict) -> None:
        self.refresh_btn.setEnabled(True)
        self._team_data = data
        sessions = data.get("sessions", []) or []
        rows: list[list[str]] = []
        ssd_names: set[str] = set()
        machines: set[str] = set()
        total_files = 0
        total_bytes = 0
        total_duration = 0.0
        for s in sessions:
            ssd_names.add(str(s.get("ssd_name", "")))
            machines.add(str(s.get("machine", "")))
            total_files += int(s.get("file_count") or 0)
            total_bytes += int(s.get("total_bytes") or 0)
            d = s.get("duration_seconds") or 0
            try:
                total_duration += float(d) if d != "" else 0
            except (TypeError, ValueError):
                pass
            duration_cell = s.get("duration_hms") or ""
            if not duration_cell and d:
                try:
                    duration_cell = format_duration_hms(float(d))
                except (TypeError, ValueError):
                    duration_cell = ""
            rows.append([
                str(s.get("ssd_name", "")),
                str(s.get("collection_date", "")),
                str(s.get("mode", "")),
                str(s.get("employee_id", "")),
                str(s.get("task_type", "")),
                f"{int(s.get('session_number') or 0):03d}",
                str(s.get("position") or ""),
                str(int(s.get("file_count") or 0)),
                duration_cell or "—",
                _human(int(s.get("total_bytes") or 0)),
                str(s.get("machine", "")),
            ])
        rows.sort(key=lambda r: (r[1], r[0], r[5], r[6]))
        self._fill_table(rows)
        self.summary_label.setText(
            f"Team view  ·  {len(ssd_names)} SSDs  ·  {len(rows)} sessions  ·  "
            f"{total_files} files  ·  {format_duration(total_duration)} of video  ·  "
            f"{_human(total_bytes)}  ·  {len(machines)} machine(s)"
        )

    def _on_pull_error(self, msg: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.summary_label.setText(f"Drive pull failed: {msg} — falling back to local.")
        self._refresh_from_local()

    def _refresh_from_local(self) -> None:
        ledger = load_ledger()
        rows: list[list[str]] = []
        total_files = 0
        total_bytes = 0
        total_duration = 0.0
        ssd_count = 0
        for ssd_uuid, ssd in ledger.get("ssds", {}).items():
            ssd_count += 1
            ssd_name = ssd.get("assigned_name") or ssd.get("logical_name") or ssd_uuid
            for s in ssd.get("sessions", []):
                total_files += s.get("file_count", 0)
                total_bytes += s.get("total_bytes", 0)
                dur = s.get("total_duration_seconds") or 0
                try:
                    total_duration += float(dur)
                except (TypeError, ValueError):
                    pass
                rows.append([
                    ssd_name,
                    s.get("collection_date", ""),
                    s.get("mode", ""),
                    s.get("employee_id", ""),
                    s.get("task_type", ""),
                    f"{s.get('session_number', 0):03d}",
                    s.get("position") or "",
                    str(s.get("file_count", 0)),
                    format_duration_hms(dur) if dur else "—",
                    _human(s.get("total_bytes", 0)),
                    "—",
                ])
        rows.sort(key=lambda r: (r[1], r[0], r[5], r[6]))
        self._fill_table(rows)
        self.summary_label.setText(
            f"Local view  ·  {ssd_count} SSDs  ·  {len(rows)} sessions  ·  "
            f"{total_files} files  ·  {format_duration(total_duration)} of video  ·  "
            f"{_human(total_bytes)}"
        )

    def _fill_table(self, rows: list[list[str]]) -> None:
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
