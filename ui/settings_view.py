from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from ingest.ledger import load_ledger, save_ledger
from ingest.manifest import load_manifest, save_manifest


class SettingsView(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)

        rename_box = QGroupBox("Rename an SSD")
        rform = QFormLayout(rename_box)

        path_row = QHBoxLayout()
        self.ssd_path_edit = QLineEdit()
        self.ssd_path_edit.setReadOnly(True)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._pick_ssd)
        path_row.addWidget(self.ssd_path_edit, 1)
        path_row.addWidget(browse)
        path_row_widget = QWidget()
        path_row_widget.setLayout(path_row)

        self.new_name_edit = QLineEdit()
        save_btn = QPushButton("Save new name")
        save_btn.clicked.connect(self._save_name)

        rform.addRow("SSD folder:", path_row_widget)
        rform.addRow("New logical name:", self.new_name_edit)
        rform.addRow("", save_btn)
        root.addWidget(rename_box)

        known_box = QGroupBox("Known SSDs (from laptop ledger)")
        klayout = QVBoxLayout(known_box)
        self.known_text = QTextEdit()
        self.known_text.setReadOnly(True)
        klayout.addWidget(self.known_text)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        klayout.addWidget(refresh)
        root.addWidget(known_box, 1)

        drive_box = QGroupBox("Google Drive sync")
        dlayout = QVBoxLayout(drive_box)
        dlayout.addWidget(QLabel(
            "Drive sync is stubbed in this build. To enable later, an OAuth "
            "credentials.json will be dropped into the app support directory."
        ))
        root.addWidget(drive_box)

    def _pick_ssd(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select SSD folder")
        if path:
            self.ssd_path_edit.setText(path)
            manifest = load_manifest(Path(path))
            self.new_name_edit.setText(manifest.get("logical_name", ""))

    def _save_name(self) -> None:
        path = self.ssd_path_edit.text().strip()
        new_name = self.new_name_edit.text().strip()
        if not path or not new_name:
            QMessageBox.warning(
                self, "Missing field",
                "Pick an SSD folder and enter a new name.",
            )
            return
        p = Path(path)
        manifest = load_manifest(p)
        if not manifest:
            QMessageBox.warning(
                self, "Not tracked",
                "That folder has no SSD manifest yet — ingest a session "
                "into it first, then rename it here.",
            )
            return
        manifest["logical_name"] = new_name
        save_manifest(p, manifest)

        ledger = load_ledger()
        ssd_uuid = manifest.get("ssd_uuid")
        if ssd_uuid and ssd_uuid in ledger.get("ssds", {}):
            ledger["ssds"][ssd_uuid]["logical_name"] = new_name
            save_ledger(ledger)
        self.refresh()
        QMessageBox.information(self, "Saved", f"SSD renamed to {new_name!r}.")

    def refresh(self) -> None:
        ledger = load_ledger()
        lines: list[str] = []
        for ssd_uuid, ssd in sorted(
            ledger.get("ssds", {}).items(),
            key=lambda kv: (kv[1].get("logical_name") or "").lower(),
        ):
            lines.append(
                f"{ssd.get('logical_name') or ssd_uuid}\n"
                f"  UUID:         {ssd_uuid}\n"
                f"  Last mount:   {ssd.get('last_mount_point', '?')}\n"
                f"  Last seen:    {ssd.get('last_seen_at', '?')}\n"
                f"  Sessions:     {len(ssd.get('sessions', []))}"
            )
        self.known_text.setPlainText(
            "\n\n".join(lines) if lines else "No SSDs tracked yet."
        )
