from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from ingest.devices import has_dcim
from ingest.models import CameraPosition, CollectionMode
from ingest.state import AppState, RegistrationAction, inspect_ssd
from ui.instance_card import InstanceCard
from ui.ssd_registration_dialog import SSDRegistrationDialog
from ui.volume_picker import VolumePickerDialog


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


_STALE_DAYS_THRESHOLD = 1
_STALE_FULL_PCT_THRESHOLD = 90.0


class SDField(QWidget):
    def __init__(self, label: str, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        self.other_fields: list["SDField"] = []
        self._vol = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.display = QLineEdit()
        self.display.setReadOnly(True)
        self.display.setPlaceholderText(label)
        self.browse_btn = QPushButton("Choose SD…")
        self.browse_btn.clicked.connect(self._pick)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.reset)
        layout.addWidget(self.display, 1)
        layout.addWidget(self.browse_btn)
        layout.addWidget(self.clear_btn)

    def _pick(self) -> None:
        exclude = set(self.app_state.sds_in_use)
        if self.app_state.ssd_info:
            exclude.add(str(self.app_state.ssd_info.path))
        for f in self.other_fields:
            v = f.value()
            if v is not None:
                exclude.add(str(v))
        vol = VolumePickerDialog.pick(
            title="Choose SD card",
            prompt="Connected SD cards (must have a DCIM folder):",
            parent=self,
            exclude_paths=exclude,
            require_dcim=True,
        )
        if vol:
            self._vol = vol
            self.display.setText(str(vol.path))

    def reset(self) -> None:
        self._vol = None
        self.display.setText("")

    def value(self) -> Path | None:
        return self._vol.path if self._vol else None


class SSDPanel(QGroupBox):
    def __init__(self, app_state: AppState):
        super().__init__("Destination SSD")
        self.app_state = app_state
        self._build()
        app_state.ssd_changed.connect(self._refresh)
        app_state.instance_added.connect(lambda _: self._refresh())
        app_state.instance_changed.connect(lambda _: self._refresh())
        app_state.instance_removed.connect(lambda _: self._refresh())
        app_state.ssd_full_warning.connect(self._warn_full)
        self._refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        self.stack = QStackedWidget()

        empty = QWidget()
        el = QVBoxLayout(empty)
        el.setContentsMargins(4, 4, 4, 4)
        el.setSpacing(10)
        heading = QLabel("No destination SSD yet")
        heading.setObjectName("TitleLabel")
        sub = QLabel(
            "Plug in an external SSD and lock it as the destination. "
            "It stays the destination for every copy until it fills up."
        )
        sub.setObjectName("SubtitleLabel")
        sub.setWordWrap(True)
        el.addWidget(heading)
        el.addWidget(sub)
        row = QHBoxLayout()
        self.connect_btn = QPushButton("Connect & lock SSD")
        self.connect_btn.setObjectName("PrimaryButton")
        self.connect_btn.clicked.connect(self._lock)
        row.addWidget(self.connect_btn)
        row.addStretch()
        el.addLayout(row)
        self.stack.addWidget(empty)

        locked = QWidget()
        ll = QVBoxLayout(locked)
        ll.setContentsMargins(4, 4, 4, 4)
        ll.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        self.name_label = QLabel()
        self.name_label.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #111827; "
            "font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;"
        )
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label = QLabel()
        self.path_label.setObjectName("SubtitleLabel")
        self.serial_label = QLabel()
        self.serial_label.setObjectName("MutedLabel")
        name_col.addWidget(self.name_label)
        name_col.addWidget(self.path_label)
        name_col.addWidget(self.serial_label)
        top_row.addLayout(name_col, 1)
        self.lock_chip = QLabel("LOCKED")
        self.lock_chip.setStyleSheet(
            "padding: 3px 10px; border-radius: 10px; "
            "font-size: 11px; font-weight: 600; "
            "background: #d1fae5; color: #065f46;"
        )
        top_row.addWidget(self.lock_chip)
        ll.addLayout(top_row)

        self.free_bar = QProgressBar()
        self.free_bar.setObjectName("WithText")
        self.free_bar.setFormat("%p% used")
        ll.addWidget(self.free_bar)

        self.free_text = QLabel()
        self.free_text.setObjectName("MutedLabel")
        ll.addWidget(self.free_text)

        hrow = QHBoxLayout()
        self.clear_ssd_btn = QPushButton("Clear SSD…")
        self.clear_ssd_btn.clicked.connect(self._clear_ssd)
        self.clear_ssd_btn.hide()
        hrow.addWidget(self.clear_ssd_btn)
        hrow.addStretch()
        self.change_btn = QPushButton("Unlock SSD…")
        self.change_btn.clicked.connect(self._unlock)
        hrow.addWidget(self.change_btn)
        ll.addLayout(hrow)

        self.stack.addWidget(locked)
        outer.addWidget(self.stack)

    def _lock(self) -> None:
        vol = VolumePickerDialog.pick(
            title="Connect destination SSD",
            prompt="Choose the external SSD to use as destination:",
            parent=self,
        )
        if vol is None:
            return
        if has_dcim(vol.path):
            confirm = QMessageBox.question(
                self, "Drive has a DCIM folder",
                "This drive has a DCIM/ folder, which usually means it's a "
                "camera SD card, not an SSD. Use it as the destination anyway?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        inspection = inspect_ssd(vol)
        if inspection.action == RegistrationAction.RECONNECT:
            self.app_state.register_or_reconnect_ssd(
                inspection, inspection.existing_name or inspection.proposed_name,
            )
            return

        dlg = SSDRegistrationDialog(inspection, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = dlg.confirmed_name() or inspection.proposed_name
        self.app_state.register_or_reconnect_ssd(inspection, name)

    def _unlock(self) -> None:
        if self.app_state.has_active_instances():
            QMessageBox.warning(
                self, "Copies in progress",
                "Finish or remove active copy instances before unlocking the SSD.",
            )
            return
        confirm = QMessageBox.question(
            self, "Unlock SSD?",
            "Unlock the current destination SSD? You'll need to pick "
            "another SSD before you can start more copies.",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.app_state.unlock_ssd()

    def _clear_ssd(self) -> None:
        if not self.app_state.ssd_info:
            return
        name = self.app_state.ssd_assigned_name or self.app_state.ssd_info.label
        confirm = QMessageBox.warning(
            self, "Clear all data on this SSD?",
            f"This will delete every session folder on {name} but preserve its "
            "registered identity (name, serial number, event log).\n\n"
            "Data deleted: every dated folder and its session files, plus the "
            "reports directory. The manifest file is kept.\n\n"
            "This cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            summary = self.app_state.clear_ssd_data()
        except RuntimeError as exc:
            QMessageBox.critical(self, "Cannot clear", str(exc))
            return

        QMessageBox.information(
            self, "SSD cleared",
            f"{summary['files_deleted']} files ({_human(summary['bytes_deleted'])}) "
            f"across {summary['sessions_deleted']} session(s) deleted.\n\n"
            f"Dates: {', '.join(summary['dates_deleted']) or '—'}\n"
            f"Modes: {', '.join(summary['modes_deleted']) or '—'}\n\n"
            f"Identity preserved: {name}",
        )
        self._refresh()

    def _refresh(self) -> None:
        info = self.app_state.ssd_info
        if info is None:
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(1)
        try:
            usage = shutil.disk_usage(info.path)
        except OSError:
            usage = None

        name = self.app_state.ssd_assigned_name or info.label
        self.name_label.setText(name)
        self.path_label.setText(str(info.path))
        drive = self.app_state.ssd_drive_info
        if drive and drive.serial_number:
            self.serial_label.setText(f"Serial: {drive.serial_number}")
        else:
            self.serial_label.setText("Serial: not detected")

        if usage and usage.total:
            pct_used = int(100.0 * (usage.total - usage.free) / usage.total)
            self.free_bar.setValue(pct_used)
            self.free_text.setText(
                f"{_human(usage.free)} free of {_human(usage.total)}"
            )
            show_clear = (
                pct_used >= _STALE_FULL_PCT_THRESHOLD
                and self._is_ssd_stale()
                and not self.app_state.has_active_instances()
            )
            self.clear_ssd_btn.setVisible(show_clear)
        self.change_btn.setEnabled(not self.app_state.has_active_instances())

    def _is_ssd_stale(self) -> bool:
        from ingest.manifest import load_manifest
        if not self.app_state.ssd_info:
            return False
        manifest = load_manifest(self.app_state.ssd_info.path)
        last = manifest.get("last_updated")
        if not last:
            return True
        try:
            dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        except ValueError:
            return True
        age = datetime.now(timezone.utc) - dt
        return age.days >= _STALE_DAYS_THRESHOLD

    def _warn_full(self, pct_free: float) -> None:
        QMessageBox.warning(
            self, "SSD nearly full",
            f"Only {pct_free:.1f}% free on this SSD. "
            "When current copies finish, unlock and connect a new SSD "
            "(or clear this one for reuse from the destination panel).",
        )


class NewInstanceForm(QGroupBox):
    def __init__(self, app_state: AppState):
        super().__init__("Start a new copy")
        self.app_state = app_state
        self._build()
        app_state.ssd_changed.connect(self._refresh)
        self._refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(10)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Single Camera", CollectionMode.SINGLE)
        self.mode_combo.addItem("3-Camera Array", CollectionMode.THREE_CAM)
        self.mode_combo.currentIndexChanged.connect(self._on_mode)
        form.addRow("Mode", self.mode_combo)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Collection date", self.date_edit)

        self.employee_edit = QLineEdit()
        self.employee_edit.setPlaceholderText("e.g. EMP001")
        form.addRow("Employee ID", self.employee_edit)

        self.task_edit = QLineEdit()
        self.task_edit.setPlaceholderText("e.g. fold-laundry")
        form.addRow("Task type", self.task_edit)

        root.addLayout(form)

        self.sd_stack = QStackedWidget()
        self.sd_stack.addWidget(self._build_single_form())
        self.sd_stack.addWidget(self._build_three_cam_form())
        root.addWidget(self.sd_stack)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.hint_label = QLabel()
        self.hint_label.setObjectName("HintLabel")
        actions.addWidget(self.hint_label, 1)
        self.start_btn = QPushButton("Start copy")
        self.start_btn.setObjectName("PrimaryButton")
        self.start_btn.clicked.connect(self._start)
        actions.addWidget(self.start_btn)
        root.addLayout(actions)

    def _build_single_form(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.single_sd = SDField("Source SD (DCIM required)", self.app_state)
        form.addRow("Source SD", self.single_sd)
        return w

    def _build_three_cam_form(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.left_sd = SDField("Left hand SD (DCIM)", self.app_state)
        self.right_sd = SDField("Right hand SD (DCIM)", self.app_state)
        self.head_sd = SDField("Head SD (DCIM)", self.app_state)
        self.left_sd.other_fields = [self.right_sd, self.head_sd]
        self.right_sd.other_fields = [self.left_sd, self.head_sd]
        self.head_sd.other_fields = [self.left_sd, self.right_sd]
        form.addRow("Left hand SD", self.left_sd)
        form.addRow("Right hand SD", self.right_sd)
        form.addRow("Head SD", self.head_sd)
        return w

    def _on_mode(self, idx: int) -> None:
        self.sd_stack.setCurrentIndex(idx)

    def _refresh(self) -> None:
        locked = self.app_state.ssd_info is not None
        self.setEnabled(locked)
        self.hint_label.setText(
            "" if locked else "Lock a destination SSD above to enable this form."
        )

    def _start(self) -> None:
        mode: CollectionMode = self.mode_combo.currentData()
        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        emp = self.employee_edit.text().strip()
        task = self.task_edit.text().strip()

        if not emp:
            QMessageBox.warning(self, "Missing field", "Employee ID is required.")
            return
        if not task:
            QMessageBox.warning(self, "Missing field", "Task type is required.")
            return

        sd_sources: list[tuple[Path, CameraPosition | None]] = []
        if mode == CollectionMode.SINGLE:
            v = self.single_sd.value()
            if v is None:
                QMessageBox.warning(self, "Missing field", "Choose the source SD card.")
                return
            sd_sources.append((v, None))
        else:
            for name, field_widget, pos in [
                ("Left", self.left_sd, CameraPosition.LEFT),
                ("Right", self.right_sd, CameraPosition.RIGHT),
                ("Head", self.head_sd, CameraPosition.HEAD),
            ]:
                v = field_widget.value()
                if v is None:
                    QMessageBox.warning(
                        self, "Missing field", f"Choose the {name} SD card.",
                    )
                    return
                sd_sources.append((v, pos))

        try:
            self.app_state.start_instance(mode, date_str, emp, task, sd_sources)
        except (ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "Cannot start copy", str(exc))
            return

        self.employee_edit.clear()
        self.task_edit.clear()
        self.single_sd.reset()
        self.left_sd.reset()
        self.right_sd.reset()
        self.head_sd.reset()


class InstanceList(QGroupBox):
    def __init__(self, app_state: AppState):
        super().__init__("Copy instances")
        self.app_state = app_state
        self._cards: dict[str, InstanceCard] = {}
        self._build()
        app_state.instance_added.connect(self._on_added)
        app_state.instance_removed.connect(self._on_removed)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.empty_label = QLabel(
            "No copies yet. Fill in the form above and click Start copy."
        )
        self.empty_label.setObjectName("HintLabel")
        layout.addWidget(self.empty_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        inner = QWidget()
        self.inner_layout = QVBoxLayout(inner)
        self.inner_layout.setContentsMargins(0, 0, 0, 0)
        self.inner_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.inner_layout.setSpacing(10)
        self.scroll_area.setWidget(inner)
        layout.addWidget(self.scroll_area, 1)

    def _on_added(self, inst_id: str) -> None:
        inst = self.app_state.instances.get(inst_id)
        if not inst:
            return
        card = InstanceCard(inst, self.app_state)
        self._cards[inst_id] = card
        self.inner_layout.addWidget(card)
        self.empty_label.setVisible(False)

    def _on_removed(self, inst_id: str) -> None:
        card = self._cards.pop(inst_id, None)
        if card:
            self.inner_layout.removeWidget(card)
            card.deleteLater()
        self.empty_label.setVisible(len(self._cards) == 0)


class IngestView(QWidget):
    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)
        root.addWidget(SSDPanel(app_state))
        root.addWidget(NewInstanceForm(app_state))
        root.addWidget(InstanceList(app_state), 1)
