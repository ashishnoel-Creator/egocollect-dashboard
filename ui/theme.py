STYLESHEET = """
QWidget {
    color: #111827;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: #f6f7f9;
}

QTabWidget::pane {
    border: 1px solid #e5e7eb;
    background: white;
    border-radius: 10px;
    top: -1px;
}

QTabWidget::tab-bar {
    alignment: left;
    left: 8px;
}

QTabBar::tab {
    padding: 9px 20px;
    background: transparent;
    border: 1px solid transparent;
    margin-right: 2px;
    color: #6b7280;
    font-weight: 500;
}

QTabBar::tab:selected {
    background: white;
    color: #111827;
    border: 1px solid #e5e7eb;
    border-bottom: 1px solid white;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}

QTabBar::tab:hover:!selected {
    color: #111827;
}

QGroupBox {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    margin-top: 18px;
    padding: 22px 16px 14px 16px;
    font-weight: 600;
    font-size: 13px;
    color: #111827;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    left: 14px;
    color: #6b7280;
    background: transparent;
    font-size: 11px;
    font-weight: 700;
}

QPushButton {
    background-color: white;
    border: 1px solid #d1d5db;
    border-radius: 7px;
    padding: 7px 14px;
    color: #111827;
    font-weight: 500;
    min-height: 18px;
}
QPushButton:hover {
    background-color: #f9fafb;
    border-color: #9ca3af;
}
QPushButton:pressed {
    background-color: #f3f4f6;
}
QPushButton:disabled {
    background: #f9fafb;
    color: #9ca3af;
    border-color: #e5e7eb;
}

QPushButton#PrimaryButton {
    background-color: #2563eb;
    color: white;
    border: 1px solid #2563eb;
    font-weight: 600;
    padding: 8px 18px;
}
QPushButton#PrimaryButton:hover {
    background-color: #1d4ed8;
    border-color: #1d4ed8;
}
QPushButton#PrimaryButton:pressed {
    background-color: #1e40af;
}
QPushButton#PrimaryButton:disabled {
    background-color: #93c5fd;
    border-color: #93c5fd;
    color: white;
}

QLineEdit, QDateEdit, QComboBox, QTextEdit {
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 7px;
    padding: 6px 10px;
    selection-background-color: #bfdbfe;
    selection-color: #1e40af;
}
QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid #2563eb;
}
QLineEdit:read-only {
    background: #f9fafb;
    color: #4b5563;
}
QLineEdit:disabled, QDateEdit:disabled, QComboBox:disabled {
    background: #f9fafb;
    color: #9ca3af;
}

QComboBox::drop-down, QDateEdit::drop-down {
    border: none;
    width: 22px;
}
QComboBox::down-arrow, QDateEdit::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #6b7280;
    margin-right: 8px;
    width: 0; height: 0;
}
QComboBox QAbstractItemView {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 7px;
    padding: 4px;
    selection-background-color: #dbeafe;
    selection-color: #1e40af;
    outline: none;
}

QProgressBar {
    border: none;
    background: #e5e7eb;
    border-radius: 4px;
    text-align: center;
    max-height: 6px;
    min-height: 6px;
    color: transparent;
}
QProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 4px;
}
QProgressBar#WithText {
    max-height: 18px;
    min-height: 18px;
    color: #4b5563;
    font-size: 11px;
    font-weight: 500;
    background: #e5e7eb;
}
QProgressBar#WithText::chunk {
    background-color: #2563eb;
    border-radius: 4px;
}

QTableWidget {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    gridline-color: #f3f4f6;
    selection-background-color: #dbeafe;
    selection-color: #1e40af;
}
QTableWidget::item { padding: 6px; }
QHeaderView::section {
    background: #f9fafb;
    border: none;
    border-bottom: 1px solid #e5e7eb;
    padding: 8px 10px;
    font-weight: 600;
    font-size: 11px;
    color: #6b7280;
    text-transform: uppercase;
}

QScrollArea { border: none; background: transparent; }

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #d1d5db;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #9ca3af; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: #d1d5db;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #9ca3af; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QFrame#InstanceCard {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
}

QLabel#TitleLabel {
    font-size: 15px;
    font-weight: 600;
    color: #111827;
}
QLabel#SubtitleLabel {
    color: #6b7280;
    font-size: 12px;
}
QLabel#MutedLabel {
    color: #6b7280;
    font-size: 11px;
}
QLabel#HintLabel {
    color: #9ca3af;
    font-style: italic;
    font-size: 11px;
}
QLabel#StatusChip {
    padding: 3px 10px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    background: #f3f4f6;
    color: #4b5563;
}

QListWidget {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    padding: 10px;
    border-radius: 6px;
    margin: 2px;
    color: #111827;
}
QListWidget::item:hover { background: #f3f4f6; }
QListWidget::item:selected { background: #dbeafe; color: #1e40af; }

QMessageBox { background: white; }

QMenu {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 14px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: #dbeafe;
    color: #1e40af;
}

QStatusBar {
    background: transparent;
    color: #6b7280;
    border-top: 1px solid #e5e7eb;
}
"""

STATUS_CHIP_STYLES = {
    "preparing": ("#dbeafe", "#1e40af"),
    "running": ("#dbeafe", "#1e40af"),
    "finalizing": ("#fef3c7", "#92400e"),
    "done_pending_clear": ("#fed7aa", "#9a3412"),
    "cleared": ("#d1fae5", "#065f46"),
    "done_no_clear": ("#f3f4f6", "#4b5563"),
    "failed": ("#fecaca", "#991b1b"),
}


def status_chip_stylesheet(status: str) -> str:
    bg, fg = STATUS_CHIP_STYLES.get(status, ("#f3f4f6", "#4b5563"))
    return (
        f"padding: 3px 10px; border-radius: 10px; "
        f"font-size: 11px; font-weight: 600; "
        f"background: {bg}; color: {fg};"
    )
