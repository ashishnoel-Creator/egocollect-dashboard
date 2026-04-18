from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QVBoxLayout, QWidget,
)

from ingest.device_info import size_bucket
from ingest.state import RegistrationAction, SSDInspection


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class SSDRegistrationDialog(QDialog):
    """Confirm assigning an identity to a newly-connected or reformatted SSD."""

    def __init__(self, inspection: SSDInspection, parent=None):
        super().__init__(parent)
        self.inspection = inspection
        self._confirmed_name: str | None = None
        self.setWindowTitle("Register SSD")
        self.setModal(True)
        self.resize(520, 380)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)

        action = self.inspection.action
        drive = self.inspection.drive_info
        vol = self.inspection.volume

        if action == RegistrationAction.NEW:
            title_text = "Register a new SSD"
            subtitle_text = (
                "This SSD hasn't been registered yet. Assign it a permanent "
                "identity so we can always recognise it, even after reformatting."
            )
            self._confirmed_name = self.inspection.proposed_name
        elif action == RegistrationAction.POST_REFORMAT:
            title_text = "SSD recognised — restore its name?"
            subtitle_text = (
                "This drive's serial number matches an SSD that was previously "
                "registered. Its manifest is missing, likely because it was "
                "reformatted. Restore the original name?"
            )
            self._confirmed_name = self.inspection.existing_name or self.inspection.proposed_name
        else:
            title_text = "Reconnect SSD"
            subtitle_text = "This SSD is already registered."
            self._confirmed_name = self.inspection.existing_name

        title = QLabel(title_text)
        title.setObjectName("TitleLabel")
        root.addWidget(title)

        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        name_card = QFrame()
        name_card.setStyleSheet(
            "QFrame { background: #eff6ff; border: 1px solid #bfdbfe; "
            "border-radius: 10px; padding: 12px; }"
        )
        name_layout = QVBoxLayout(name_card)
        name_layout.setSpacing(4)
        name_small = QLabel("ASSIGNED NAME")
        name_small.setStyleSheet(
            "color: #1e40af; font-size: 10px; font-weight: 700; "
            "letter-spacing: 0.5px; background: transparent; border: none;"
        )
        name_big = QLabel(self._confirmed_name or "?")
        name_big.setStyleSheet(
            "color: #1e3a8a; font-size: 18px; font-weight: 700; "
            "font-family: 'SF Mono', 'Menlo', 'Consolas', monospace; "
            "background: transparent; border: none;"
        )
        name_big.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        name_layout.addWidget(name_small)
        name_layout.addWidget(name_big)
        root.addWidget(name_card)

        details = QFormLayout()
        details.setHorizontalSpacing(14)
        details.setVerticalSpacing(6)
        details.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        details.addRow(self._muted("Mount point:"), self._value(str(vol.path)))
        details.addRow(self._muted("Volume label:"), self._value(vol.label or "—"))
        size_label = size_bucket(drive.total_bytes or vol.total_bytes)
        total = drive.total_bytes or vol.total_bytes
        details.addRow(
            self._muted("Capacity:"),
            self._value(f"{size_label}  ({_human(total)} reported)"),
        )
        details.addRow(
            self._muted("Serial number:"),
            self._value(drive.serial_number or "not detected — using volume UUID fallback"),
        )
        details.addRow(
            self._muted("Volume UUID:"),
            self._value(drive.volume_uuid or "—"),
        )
        if drive.media_name:
            details.addRow(self._muted("Media name:"), self._value(drive.media_name))
        root.addLayout(details)

        if not drive.serial_number:
            warn = QLabel(
                "Heads up: serial number not detected (some USB-SATA adapters "
                "hide it). We'll track this SSD by its volume UUID instead, "
                "which changes if the drive is reformatted."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(
                "color: #92400e; background: #fef3c7; border: 1px solid #fde68a; "
                "border-radius: 8px; padding: 8px 10px; font-size: 11px;"
            )
            root.addWidget(warn)

        root.addStretch(1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setObjectName("PrimaryButton")
            if action == RegistrationAction.NEW:
                ok_btn.setText("Register and lock")
            elif action == RegistrationAction.POST_REFORMAT:
                ok_btn.setText("Restore name and lock")
            else:
                ok_btn.setText("Lock")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    @staticmethod
    def _muted(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("color: #6b7280; font-size: 12px;")
        return label

    @staticmethod
    def _value(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("color: #111827; font-size: 12px;")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setWordWrap(True)
        return label

    def confirmed_name(self) -> str | None:
        return self._confirmed_name
