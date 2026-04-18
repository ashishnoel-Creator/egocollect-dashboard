from __future__ import annotations

from datetime import datetime, timezone

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ingest.ledger import load_ledger
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

        version_row = QHBoxLayout()
        version = QLabel(f"EgoCollect v{VERSION}")
        version.setObjectName("TitleLabel")
        version_row.addWidget(version)
        version_row.addStretch()
        layout.addLayout(version_row)

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

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Name", "Serial", "Capacity", "Sessions", "Data",
            "Last seen", "State",
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
        for i, (ssd_uuid, entry) in enumerate(
            sorted(ssds.items(), key=lambda kv: (kv[1].get("assigned_name") or "").lower())
        ):
            name = entry.get("assigned_name") or entry.get("logical_name") or ssd_uuid[:8]
            serial = entry.get("serial_number") or "—"
            total = entry.get("total_bytes") or 0
            sessions = entry.get("sessions", [])
            session_count = len(sessions)
            data_bytes = sum(s.get("total_bytes", 0) for s in sessions)
            last_seen = entry.get("last_seen_at")

            if ssd_uuid == locked_uuid:
                state = "CONNECTED"
                state_color = "#d1fae5;color:#065f46"
            else:
                state = "offline"
                state_color = "#f3f4f6;color:#6b7280"

            total_sessions += session_count
            total_bytes += data_bytes

            values = [
                name,
                serial,
                _human(total) if total else "—",
                str(session_count),
                _human(data_bytes),
                _relative_time(last_seen),
                state,
            ]
            for j, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if j == 0:
                    item.setData(Qt.ItemDataRole.UserRole, ssd_uuid)
                    font = item.font()
                    font.setFamilies(["SF Mono", "Menlo", "Consolas", "monospace"])
                    item.setFont(font)
                self.table.setItem(i, j, item)

        self.table.resizeColumnsToContents()
        self.summary_label.setText(
            f"{len(ssds)} SSDs tracked  ·  {total_sessions} sessions  ·  "
            f"{_human(total_bytes)} archived"
        )


class DriveSyncCard(QGroupBox):
    def __init__(self):
        super().__init__("Google Drive sync")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        status = QLabel(
            "Drive sync is not configured yet. When enabled, each SSD "
            "registration and clear event will be mirrored to a Google Sheet "
            "for cross-team visibility. (Planned for Phase 4.)"
        )
        status.setObjectName("SubtitleLabel")
        status.setWordWrap(True)
        layout.addWidget(status)


class AdminView(QWidget):
    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)
        root.addWidget(AppInfoCard())
        root.addWidget(SSDRegistryCard(app_state), 1)
        root.addWidget(DriveSyncCard())
