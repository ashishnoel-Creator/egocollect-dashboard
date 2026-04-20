from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from ingest.updater import (
    UpdateInfo, apply_mac_update, apply_windows_update,
    download_update, is_frozen,
)


class _DownloadWorker(QThread):
    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(str)
    errored = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        path = download_update(
            self.url,
            progress_cb=lambda done, total: self.progress.emit(done, total),
        )
        if path is None:
            self.errored.emit("Download failed.")
            return
        self.finished_ok.emit(str(path))


class UpdateDialog(QDialog):
    def __init__(self, info: UpdateInfo, parent=None):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle("Install update")
        self.setModal(True)
        self.resize(460, 200)
        self._worker: _DownloadWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)

        title = QLabel(f"Installing {info.latest_version}")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        self.status_label = QLabel("Preparing download…")
        self.status_label.setObjectName("SubtitleLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("WithText")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.close_btn = QPushButton("Cancel")
        self.close_btn.clicked.connect(self.reject)
        button_row.addWidget(self.close_btn)
        layout.addLayout(button_row)

    def start(self):
        url = self._asset_url_for_platform()
        if url is None:
            QMessageBox.critical(
                self, "No installer available",
                "This release doesn't include an installer for your platform.",
            )
            self.reject()
            return
        self._worker = _DownloadWorker(url)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_downloaded)
        self._worker.errored.connect(self._on_error)
        self._worker.start()
        self.exec()

    def _asset_url_for_platform(self) -> str | None:
        if sys.platform == "darwin":
            return self.info.mac_asset_url
        if sys.platform == "win32":
            return self.info.win_asset_url
        return None

    def _on_progress(self, done: int, total: int):
        if total > 0:
            if self.progress_bar.maximum() != total:
                self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)
            mb_done = done / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.status_label.setText(
                f"Downloading… {mb_done:.1f} MB of {mb_total:.1f} MB"
            )

    def _on_error(self, msg: str):
        QMessageBox.critical(self, "Update failed", msg)
        self.reject()

    def _on_downloaded(self, path_str: str):
        path = Path(path_str)
        try:
            if sys.platform == "darwin":
                if not is_frozen():
                    QMessageBox.information(
                        self.parent(), "Update downloaded",
                        f"Saved to {path}. Running from source; install "
                        "the DMG manually.",
                    )
                    self.accept()
                    return
                self.status_label.setText(
                    "Installing… the app will quit and relaunch automatically."
                )
                silent = apply_mac_update(path)
                self.accept()
                if silent:
                    QMessageBox.information(
                        self.parent(), "Installing update",
                        f"EgoCollect will quit now and relaunch as "
                        f"{self.info.latest_version}. This takes about 5 "
                        "seconds — no action needed.",
                    )
                    QApplication.instance().quit()
                else:
                    QMessageBox.information(
                        self.parent(), "Update downloaded",
                        f"Couldn't auto-install — Finder has opened the DMG. "
                        "Quit EgoCollect, drag the new version into "
                        "Applications, then relaunch.",
                    )
            elif sys.platform == "win32":
                if not is_frozen():
                    QMessageBox.information(
                        self.parent(), "Update downloaded",
                        f"Downloaded to {path}. Extract it manually to "
                        "replace your install.",
                    )
                    self.accept()
                    return
                apply_windows_update(path)
                self.accept()
                QApplication.instance().quit()
            else:
                QMessageBox.information(
                    self.parent(), "Update downloaded",
                    f"Saved to {path}. Install manually.",
                )
                self.accept()
        except Exception as exc:
            QMessageBox.critical(self.parent(), "Update failed", str(exc))
            self.reject()


class UpdateBanner(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._info: UpdateInfo | None = None
        self.setStyleSheet(
            "QFrame { background: #eff6ff; border: 1px solid #bfdbfe; "
            "border-radius: 10px; }"
        )
        self.hide()
        self._build()

    def _build(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title = QLabel()
        self.title.setStyleSheet(
            "color: #1e40af; font-weight: 600; font-size: 13px; "
            "background: transparent; border: none;"
        )
        self.subtitle = QLabel()
        self.subtitle.setStyleSheet(
            "color: #1d4ed8; font-size: 11px; "
            "background: transparent; border: none;"
        )
        self.subtitle.setWordWrap(True)
        text_col.addWidget(self.title)
        text_col.addWidget(self.subtitle)
        row.addLayout(text_col, 1)

        self.install_btn = QPushButton("Install update")
        self.install_btn.setObjectName("PrimaryButton")
        self.install_btn.clicked.connect(self._on_install)
        row.addWidget(self.install_btn)

        self.dismiss_btn = QPushButton("Later")
        self.dismiss_btn.clicked.connect(self.hide)
        row.addWidget(self.dismiss_btn)

    def show_update(self, info: UpdateInfo):
        self._info = info
        self.title.setText(f"Update available — {info.latest_version}")
        notes = (info.release_notes or "").strip().splitlines()
        first = notes[0] if notes else ""
        self.subtitle.setText(
            first[:200] if first else "A newer version is available on GitHub."
        )
        self.show()

    def _on_install(self):
        if not self._info:
            return
        dlg = UpdateDialog(self._info, self.window())
        dlg.start()
        self.hide()
