from __future__ import annotations

import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from ingest.state import AppState
from ui.main_window import MainWindow
from ui.theme import STYLESHEET


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
    window = MainWindow(state)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
