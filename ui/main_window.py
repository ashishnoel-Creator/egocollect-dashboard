from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from ingest.state import AppState
from ingest.updater import UpdateInfo, check_for_update, check_for_update_async
from ingest.version import GITHUB_REPO, VERSION
from ui.dashboard_view import DashboardView
from ui.ingest_view import IngestView
from ui.settings_view import SettingsView
from ui.update_banner import UpdateBanner


class MainWindow(QMainWindow):
    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.setWindowTitle(f"EgoCollect  ·  v{VERSION}")
        self.resize(1100, 840)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.update_banner = UpdateBanner()
        layout.addWidget(self.update_banner)

        tabs = QTabWidget()
        tabs.addTab(IngestView(app_state), "Ingest")
        tabs.addTab(DashboardView(app_state), "Dashboard")
        tabs.addTab(SettingsView(), "Settings")
        layout.addWidget(tabs, 1)

        self.setCentralWidget(central)

        self._build_menu()
        self._kick_off_update_check()

    def _build_menu(self) -> None:
        bar = self.menuBar()
        help_menu = bar.addMenu("&Help")

        check_action = QAction("Check for updates…", self)
        check_action.triggered.connect(self._check_for_updates_manual)
        help_menu.addAction(check_action)

        about_action = QAction("About EgoCollect", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _kick_off_update_check(self) -> None:
        check_for_update_async(
            VERSION, GITHUB_REPO,
            callback=self._on_update_result_bg,
        )

    def _on_update_result_bg(self, info: UpdateInfo | None) -> None:
        if info is None:
            return
        self.update_banner.show_update(info)

    def _check_for_updates_manual(self) -> None:
        info = check_for_update(VERSION, GITHUB_REPO)
        if info is None:
            QMessageBox.information(
                self, "No updates",
                f"You're on the latest version (v{VERSION}).",
            )
        else:
            self.update_banner.show_update(info)

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About EgoCollect",
            f"<h3>EgoCollect</h3>"
            f"<p>Egocentric Data Collection — v{VERSION}</p>"
            f"<p><a href='https://github.com/{GITHUB_REPO}'>"
            f"github.com/{GITHUB_REPO}</a></p>",
        )
