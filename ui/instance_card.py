from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QTextEdit, QVBoxLayout,
)

from ingest.state import (
    STATUS_CLEARED, STATUS_DONE_NO_CLEAR, STATUS_DONE_PENDING_CLEAR,
    STATUS_FAILED, STATUS_FINALIZING, STATUS_PREPARING, STATUS_RUNNING,
    AppState, CopyInstance,
)
from ui.theme import status_chip_stylesheet


_STATUS_LABEL = {
    STATUS_PREPARING: "PREPARING",
    STATUS_RUNNING: "COPYING",
    STATUS_FINALIZING: "FINALIZING",
    STATUS_DONE_PENDING_CLEAR: "VERIFIED",
    STATUS_CLEARED: "CLEARED",
    STATUS_DONE_NO_CLEAR: "DONE",
    STATUS_FAILED: "FAILED",
}


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class InstanceCard(QFrame):
    def __init__(self, inst: CopyInstance, app_state: AppState, parent=None):
        super().__init__(parent)
        self.inst_id = inst.id
        self.app_state = app_state
        self.setObjectName("InstanceCard")
        self._build()
        app_state.instance_changed.connect(self._maybe_refresh)
        self._refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.title_label = QLabel()
        self.title_label.setObjectName("TitleLabel")
        self.status_label = QLabel()
        self.status_label.setObjectName("StatusChip")
        header.addWidget(self.title_label, 1)
        header.addWidget(self.status_label)
        layout.addLayout(header)

        self.sd_label = QLabel()
        self.sd_label.setObjectName("SubtitleLabel")
        layout.addWidget(self.sd_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 1000)
        layout.addWidget(self.progress_bar)

        self.progress_text = QLabel()
        self.progress_text.setObjectName("MutedLabel")
        layout.addWidget(self.progress_text)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.details_btn = QPushButton("Show log")
        self.details_btn.setCheckable(True)
        self.details_btn.setChecked(True)
        self.details_btn.toggled.connect(self._toggle_log)
        self.clear_yes_btn = QPushButton("Clear SD card(s) now")
        self.clear_yes_btn.setObjectName("PrimaryButton")
        self.clear_yes_btn.clicked.connect(self._on_clear_yes)
        self.clear_no_btn = QPushButton("Keep files on SD")
        self.clear_no_btn.clicked.connect(self._on_clear_no)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._on_remove)

        actions.addWidget(self.details_btn)
        actions.addStretch()
        actions.addWidget(self.clear_no_btn)
        actions.addWidget(self.clear_yes_btn)
        actions.addWidget(self.remove_btn)
        layout.addLayout(actions)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(220)
        layout.addWidget(self.log_view)
        self._toggle_log(True)

    def _maybe_refresh(self, inst_id: str) -> None:
        if inst_id == self.inst_id:
            self._refresh()

    def _refresh(self) -> None:
        inst = self.app_state.instances.get(self.inst_id)
        if inst is None:
            return

        self.title_label.setText(inst.title())

        source_parts = []
        for sd, pos in inst.sd_sources:
            label = pos.value if pos else "SD"
            source_parts.append(f"{label}: {sd.name}")
        self.sd_label.setText("   •   ".join(source_parts))

        if inst.total_bytes > 0:
            pct = min(100.0, 100.0 * inst.done_bytes / inst.total_bytes)
            self.progress_bar.setValue(int(pct * 10))
        else:
            self.progress_bar.setValue(0)

        self.progress_text.setText(
            f"{_human(inst.done_bytes)} / {_human(inst.total_bytes)}   ·   "
            f"files: {inst.done_files} / {inst.total_files}"
        )

        self.status_label.setText(_STATUS_LABEL.get(inst.status, inst.status.upper()))
        self.status_label.setStyleSheet(status_chip_stylesheet(inst.status))

        if inst.status == STATUS_DONE_PENDING_CLEAR:
            self.message_label.setText(
                f"{inst.total_files} files copied and SHA-256 verified. "
                "Ready to clear the source SD card(s)."
            )
        elif inst.status == STATUS_CLEARED:
            self.message_label.setText(
                f"{inst.total_files} files copied. SD card(s) cleared."
            )
        elif inst.status == STATUS_DONE_NO_CLEAR:
            self.message_label.setText(
                f"{inst.total_files} files copied. SD card(s) kept untouched."
            )
        elif inst.status == STATUS_FAILED:
            self.message_label.setText(
                f"Failed: {inst.error or 'unknown error'}. "
                "SD card(s) not cleared; data on SSD kept."
            )
        else:
            self.message_label.setText("")

        pending = inst.status == STATUS_DONE_PENDING_CLEAR
        self.clear_yes_btn.setVisible(pending)
        self.clear_no_btn.setVisible(pending)
        self.remove_btn.setVisible(not inst.is_active() and not pending)

        if self.log_view.isVisible():
            text = "\n".join(inst.log_lines[-400:])
            if self.log_view.toPlainText() != text:
                self.log_view.setPlainText(text)
                cursor = self.log_view.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)
                self.log_view.setTextCursor(cursor)

    def _toggle_log(self, on: bool) -> None:
        self.log_view.setVisible(on)
        self.details_btn.setText("Hide log" if on else "Show log")
        if on:
            inst = self.app_state.instances.get(self.inst_id)
            if inst:
                self.log_view.setPlainText("\n".join(inst.log_lines[-400:]))

    def _on_clear_yes(self) -> None:
        confirm = QMessageBox.question(
            self, "Clear SD cards?",
            "All files under DCIM/ on the source SD card(s) will be "
            "permanently deleted. Copies on the SSD are verified.\n\n"
            "Continue?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.app_state.resolve_clear(self.inst_id, clear_sds=True)

    def _on_clear_no(self) -> None:
        self.app_state.resolve_clear(self.inst_id, clear_sds=False)

    def _on_remove(self) -> None:
        self.app_state.remove_instance(self.inst_id)
