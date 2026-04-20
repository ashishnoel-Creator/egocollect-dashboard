from __future__ import annotations

from datetime import datetime, timezone

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ingest.drive_sync import sheet_url
from ingest.ledger import load_ledger
from ingest.media_info import format_duration
from ingest.state import AppState
from ingest.version import GITHUB_REPO, VERSION


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _relative_time(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    delta = datetime.now(timezone.utc) - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


class AppInfoCard(QGroupBox):
    def __init__(self):
        super().__init__("Application")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        version = QLabel(f"EgoCollect v{VERSION}")
        version.setObjectName("TitleLabel")
        layout.addWidget(version)

        repo_label = QLabel(
            f'Source & updates: <a href="https://github.com/{GITHUB_REPO}">'
            f"github.com/{GITHUB_REPO}</a>"
        )
        repo_label.setObjectName("SubtitleLabel")
        repo_label.setOpenExternalLinks(True)
        layout.addWidget(repo_label)

        support_row = QHBoxLayout()
        open_support_btn = QPushButton("Open app data folder")
        open_support_btn.clicked.connect(self._open_support_dir)
        support_row.addWidget(open_support_btn)
        support_row.addStretch()
        layout.addLayout(support_row)

    def _open_support_dir(self):
        from ingest.config import app_paths
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_paths().support_dir)))


class DriveSyncCard(QGroupBox):
    def __init__(self, app_state: AppState):
        super().__init__("Google Drive sync")
        self.app_state = app_state
        self._build()

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        status_row = QHBoxLayout()
        self.chip = QLabel("INITIALIZING")
        self.chip.setStyleSheet(
            "padding: 3px 10px; border-radius: 10px; "
            "font-size: 11px; font-weight: 600; "
            "background: #f3f4f6; color: #6b7280;"
        )
        status_row.addWidget(self.chip)
        status_row.addStretch()
        self.open_btn = QPushButton("Open Sheet")
        self.open_btn.clicked.connect(self._open_sheet)
        self.open_btn.setEnabled(False)
        status_row.addWidget(self.open_btn)
        layout.addLayout(status_row)

        self.detail_label = QLabel()
        self.detail_label.setWordWrap(True)
        self.detail_label.setObjectName("SubtitleLabel")
        layout.addWidget(self.detail_label)

    def _refresh(self):
        ds = self.app_state.drive_sync
        if ds is None:
            self.chip.setText("CONNECTING")
            self.chip.setStyleSheet(
                "padding: 3px 10px; border-radius: 10px; "
                "font-size: 11px; font-weight: 600; "
                "background: #fef3c7; color: #92400e;"
            )
            self.detail_label.setText("Authenticating with Google Drive…")
            self.open_btn.setEnabled(False)
            return

        if ds.status.available:
            self.chip.setText("CONNECTED")
            self.chip.setStyleSheet(
                "padding: 3px 10px; border-radius: 10px; "
                "font-size: 11px; font-weight: 600; "
                "background: #d1fae5; color: #065f46;"
            )
            pending = ds.status.pending_jobs
            last_sync = _relative_time(ds.status.last_sync_at)
            extra = f"  ·  {pending} job(s) pending" if pending else ""
            self.detail_label.setText(
                f"Mirroring SSD registrations, copies, and clear events to "
                f"<b>EgoCollect_Log</b>. Last sync: {last_sync}{extra}."
            )
            self.open_btn.setEnabled(True)
        else:
            self.chip.setText("UNAVAILABLE")
            self.chip.setStyleSheet(
                "padding: 3px 10px; border-radius: 10px; "
                "font-size: 11px; font-weight: 600; "
                "background: #fecaca; color: #991b1b;"
            )
            self.detail_label.setText(
                f"Drive sync is offline: {ds.status.last_error or 'unknown error'}."
            )
            self.open_btn.setEnabled(False)

    def _open_sheet(self):
        ds = self.app_state.drive_sync
        if ds and ds.status.spreadsheet_id:
            QDesktopServices.openUrl(QUrl(sheet_url(ds.status.spreadsheet_id)))


class SSDRegistryCard(QGroupBox):
    def __init__(self, app_state: AppState):
        super().__init__("Registered SSDs")
        self.app_state = app_state
        self._build()
        app_state.ssd_changed.connect(self.refresh)
        app_state.instance_changed.connect(lambda _: self.refresh())
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.summary_label = QLabel()
        self.summary_label.setObjectName("MutedLabel")
        header.addWidget(self.summary_label, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        layout.addLayout(header)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Name", "Serial", "Capacity", "Sessions", "Data",
            "Duration", "Last seen", "State",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

    def refresh(self):
        ledger = load_ledger()
        ssds = ledger.get("ssds", {})
        self.table.setRowCount(len(ssds))

        locked_uuid = None
        if self.app_state.ssd_info and self.app_state.ssd_assigned_name:
            from ingest.manifest import load_manifest
            m = load_manifest(self.app_state.ssd_info.path)
            locked_uuid = m.get("ssd_uuid")

        total_sessions = 0
        total_bytes = 0
        total_duration = 0.0
        for i, (ssd_uuid, entry) in enumerate(
            sorted(ssds.items(), key=lambda kv: (kv[1].get("assigned_name") or "").lower())
        ):
            name = entry.get("assigned_name") or entry.get("logical_name") or ssd_uuid[:8]
            serial = entry.get("serial_number") or "—"
            total = entry.get("total_bytes") or 0
            sessions = entry.get("sessions", [])
            session_count = len(sessions)
            data_bytes = sum(s.get("total_bytes", 0) for s in sessions)
            duration_s = 0.0
            for s in sessions:
                try:
                    duration_s += float(s.get("total_duration_seconds") or 0)
                except (TypeError, ValueError):
                    pass
            last_seen = entry.get("last_seen_at")

            if ssd_uuid == locked_uuid:
                state = "CONNECTED"
            else:
                state = "offline"

            total_sessions += session_count
            total_bytes += data_bytes
            total_duration += duration_s

            values = [
                name,
                serial,
                _human(total) if total else "—",
                str(session_count),
                _human(data_bytes),
                format_duration(duration_s),
                _relative_time(last_seen),
                state,
            ]
            for j, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if j == 0:
                    item.setData(Qt.ItemDataRole.UserRole, ssd_uuid)
                    font = item.font()
                    font.setFamilies(["Menlo", "Consolas", "monospace"])
                    item.setFont(font)
                self.table.setItem(i, j, item)

        self.table.resizeColumnsToContents()
        self.summary_label.setText(
            f"{len(ssds)} SSDs tracked locally  ·  {total_sessions} sessions  ·  "
            f"{_human(total_bytes)} archived  ·  "
            f"{format_duration(total_duration)} of video"
        )


class AdminView(QWidget):
    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)
        root.addWidget(AppInfoCard())
        root.addWidget(DriveSyncCard(app_state))
        root.addWidget(SSDRegistryCard(app_state), 1)
