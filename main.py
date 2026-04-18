from __future__ import annotations

import sys
import threading

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from ingest.drive_sync import DriveSync
from ingest.state import AppState
from ui.main_window import MainWindow
from ui.theme import STYLESHEET


def _init_drive_sync_in_background(state: AppState) -> None:
    def _run():
        ds = DriveSync()
        ds.initialize()
        state.attach_drive_sync(ds)
    threading.Thread(target=_run, daemon=True).start()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("EgoCollect")
    app.setOrganizationName("EgoCollect")
    app.setStyle("Fusion")

    font = QFont()
    font.setPointSize(13)
    app.setFont(font)

    app.setStyleSheet(STYLESHEET)

    state = AppState()
    _init_drive_sync_in_background(state)

    window = MainWindow(state)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
