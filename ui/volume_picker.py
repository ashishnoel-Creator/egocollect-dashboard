from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout,
)

from ingest.devices import VolumeInfo, has_dcim, list_external_volumes


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class VolumePickerDialog(QDialog):
    def __init__(
        self,
        title: str,
        prompt: str = "Choose a connected external drive:",
        parent=None,
        exclude_paths: set[str] | None = None,
        require_dcim: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(600, 400)
        self._exclude = exclude_paths or set()
        self._require_dcim = require_dcim
        self._selected: VolumeInfo | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(prompt))

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._accept_current)
        layout.addWidget(self.list_widget, 1)

        self.empty_label = QLabel()
        self.empty_label.setStyleSheet("color: #888; font-style: italic;")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

        bottom = QHBoxLayout()
        refresh_btn = QPushButton("Refresh drive list")
        refresh_btn.clicked.connect(self.refresh)
        bottom.addWidget(refresh_btn)
        bottom.addStretch()
        layout.addLayout(bottom)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setObjectName("PrimaryButton")
            ok_btn.setText("Use this drive")
        btns.accepted.connect(self._accept_current)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        shown = 0
        for vol in list_external_volumes():
            if str(vol.path) in self._exclude:
                continue
            if self._require_dcim and not has_dcim(vol.path):
                continue
            item = QListWidgetItem(
                f"{vol.label}   ({_human(vol.free_bytes)} free of "
                f"{_human(vol.total_bytes)})\n"
                f"{vol.path}   [{vol.fstype}]"
            )
            item.setData(Qt.ItemDataRole.UserRole, vol)
            self.list_widget.addItem(item)
            shown += 1

        if shown == 0:
            if self._require_dcim:
                self.empty_label.setText(
                    "No available SD cards with a DCIM folder. "
                    "Connect a GoPro SD card and click Refresh. "
                    "(SDs already used by another running copy are hidden.)"
                )
            else:
                self.empty_label.setText(
                    "No external drives detected. "
                    "Connect a drive and click Refresh."
                )
        else:
            self.empty_label.setText(
                f"{shown} drive{'s' if shown != 1 else ''} available."
            )

    def _accept_current(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        self._selected = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    @classmethod
    def pick(
        cls,
        title: str,
        prompt: str = "Choose a connected external drive:",
        parent=None,
        exclude_paths: set[str] | None = None,
        require_dcim: bool = False,
    ) -> VolumeInfo | None:
        dlg = cls(title, prompt, parent, exclude_paths, require_dcim)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg._selected
        return None
