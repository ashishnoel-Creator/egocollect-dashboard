from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ingest.ledger import load_ledger
from ingest.state import AppState


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class DashboardView(QWidget):
    def __init__(self, app_state: AppState | None = None):
        super().__init__()
        self.app_state = app_state
        self._build()
        if app_state is not None:
            app_state.instance_changed.connect(lambda _: self.refresh())
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>All ingested sessions across known SSDs</b>"))
        header.addStretch()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        root.addLayout(header)

        self.summary_label = QLabel()
        root.addWidget(self.summary_label)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "SSD", "Date", "Mode", "Employee", "Task",
            "Session", "Position", "Files", "Size",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

    def refresh(self) -> None:
        ledger = load_ledger()
        rows: list[list[str]] = []
        total_files = 0
        total_bytes = 0
        ssd_count = 0
        for ssd_uuid, ssd in ledger.get("ssds", {}).items():
            ssd_count += 1
            ssd_name = ssd.get("assigned_name") or ssd.get("logical_name") or ssd_uuid
            for s in ssd.get("sessions", []):
                total_files += s.get("file_count", 0)
                total_bytes += s.get("total_bytes", 0)
                rows.append([
                    ssd_name,
                    s.get("collection_date", ""),
                    s.get("mode", ""),
                    s.get("employee_id", ""),
                    s.get("task_type", ""),
                    f"{s.get('session_number', 0):03d}",
                    s.get("position") or "",
                    str(s.get("file_count", 0)),
                    _human(s.get("total_bytes", 0)),
                ])

        rows.sort(key=lambda r: (r[1], r[0], r[5], r[6]))
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()

        self.summary_label.setText(
            f"{ssd_count} SSDs tracked · {len(rows)} session entries · "
            f"{total_files} files · {_human(total_bytes)}"
        )
