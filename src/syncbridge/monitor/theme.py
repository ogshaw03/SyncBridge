"""Dark theme of the monitor (2026-10-20, the user's request): deep navy surfaces, the teal-to-
blue gradient of the SyncBridge icon as the accent, colored dots for the hub state.

    theme.apply(app)            Fusion style + palette + style sheet
    theme.dark_title_bar(w)     Windows 10/11: dark title bar for this window only
"""
from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

BG = "#030405"          # window
SURFACE = "#08090d"     # tables, cards
SURFACE_2 = "#0e1117"   # headers, inputs, buttons
SURFACE_3 = "#161b24"   # hover
BORDER = "#1a202b"
TEXT = "#e6ebf2"
MUTED = "#8a95a8"
TEAL = "#22d3c5"
BLUE = "#3b82f6"
SELECTION = "#1d3a5c"
RED = "#f87171"
AMBER = "#fbbf24"

GRADIENT = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 %s, stop:1 %s)" % (TEAL, BLUE)

# hub state -> dot color (hubs.RUNNING, NOT_RESPONDING, STALE, UNKNOWN)
STATE_COLORS = {"running": TEAL, "not_responding": AMBER, "stale": "#64748b", "unknown": "#a78bfa"}
# transfer status -> result color
RESULT_COLORS = {"applied": TEAL, "running": BLUE, "cancelled": MUTED, "unchanged": MUTED, "failed": AMBER, "error": RED}
# log level -> text color
LEVEL_COLORS = {"DEBUG": "#64748b", "INFO": "#9fb0c6", "WARNING": AMBER, "ERROR": RED, "CRITICAL": RED}

STYLE = """
QMainWindow, QWidget { background: %(BG)s; color: %(TEXT)s; }
QLabel { background: transparent; }
QLabel#title { font-size: 15pt; font-weight: 600; color: %(TEXT)s; }
QLabel#version { color: %(MUTED)s; font-size: 9pt; padding-top: 6px; }
QLabel#section { color: %(MUTED)s; font-size: 8pt; font-weight: 600; letter-spacing: 1px; }
QLabel#detail { color: %(TEXT)s; background: %(SURFACE)s; border: 1px solid %(BORDER)s;
                border-left: 3px solid %(TEAL)s; border-radius: 6px; padding: 7px 10px; }
QWidget#header { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #09262f, stop:0.22 #06161d, stop:0.6 %(BG)s, stop:1 %(BG)s);
                 border-bottom: 1px solid %(BORDER)s; }

QTableWidget { background: %(SURFACE)s; alternate-background-color: #06070a; border: 1px solid %(BORDER)s;
               border-radius: 8px; gridline-color: transparent; selection-background-color: %(SELECTION)s;
               outline: 0; }
QTableWidget::item { padding: 0 8px; border: none; }
QTableWidget::item:selected { background: %(SELECTION)s; }
QHeaderView { background: transparent; }
QHeaderView::section { background: %(SURFACE_2)s; color: %(MUTED)s; border: none;
                       border-bottom: 1px solid %(BORDER)s; padding: 7px 8px; font-weight: 600; }
QHeaderView::section:first { border-top-left-radius: 8px; }
QHeaderView::section:last { border-top-right-radius: 8px; }
QTableCornerButton::section { background: %(SURFACE_2)s; border: none; }

QPushButton { background: %(SURFACE_2)s; color: %(TEXT)s; border: 1px solid %(BORDER)s; border-radius: 6px;
              padding: 6px 14px; }
QPushButton:hover { background: %(SURFACE_3)s; border-color: #3a4760; }
QPushButton:pressed { background: #0a0d12; }
QPushButton:disabled { color: #4b5566; background: #07090c; border-color: #141922; }
QPushButton#primary { background: %(GRADIENT)s; color: #06121a; border: none; font-weight: 700; }
QPushButton#primary:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4be3d7, stop:1 #5b97f8); }
QPushButton#danger { color: %(RED)s; border-color: #5a2a2f; background: #1e1518; }
QPushButton#danger:hover { background: #2a1a1e; border-color: %(RED)s; }
QPushButton#danger:disabled { color: #4b5566; background: #07090c; border-color: #141922; }

QCheckBox { color: %(MUTED)s; spacing: 6px; }
QCheckBox::indicator { width: 14px; height: 14px; border-radius: 4px; border: 1px solid #3a4760; background: %(SURFACE_2)s; }
QCheckBox::indicator:checked { background: %(GRADIENT)s; border: none; }

QComboBox { background: %(SURFACE_2)s; border: 1px solid %(BORDER)s; border-radius: 6px; padding: 4px 10px; min-width: 90px; }
QComboBox QAbstractItemView { background: %(SURFACE_2)s; border: 1px solid %(BORDER)s; selection-background-color: %(SELECTION)s; }

QTabWidget::pane { border: none; top: -1px; }
QTabBar::tab { background: transparent; color: %(MUTED)s; padding: 8px 16px; border: none;
               border-bottom: 2px solid transparent; margin-right: 4px; }
QTabBar::tab:hover { color: %(TEXT)s; }
QTabBar::tab:selected { color: %(TEXT)s; border-bottom: 2px solid %(TEAL)s; font-weight: 600; }

QPlainTextEdit { background: #010102; color: %(TEXT)s; border: 1px solid %(BORDER)s; border-radius: 8px;
                 padding: 6px; font-family: "Cascadia Mono", Consolas, monospace; font-size: 9pt;
                 selection-background-color: %(SELECTION)s; }

QSplitter::handle { background: transparent; height: 10px; }
QStatusBar { background: #010102; color: %(MUTED)s; border-top: 1px solid %(BORDER)s; padding-left: 12px; }
QStatusBar::item { border: none; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2c3546; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #3a4760; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #2c3546; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { background: none; border: none; width: 0; height: 0; }

QToolTip { background: %(SURFACE_2)s; color: %(TEXT)s; border: 1px solid %(BORDER)s; padding: 4px 6px; }
QMessageBox { background: %(SURFACE)s; }
""" % dict(BG=BG, SURFACE=SURFACE, SURFACE_2=SURFACE_2, SURFACE_3=SURFACE_3, BORDER=BORDER, TEXT=TEXT,
           MUTED=MUTED, TEAL=TEAL, SELECTION=SELECTION, RED=RED, GRADIENT=GRADIENT)


def apply(app: QApplication) -> None:
    app.setStyle(QStyleFactory.create("Fusion"))
    palette = QPalette()
    for role, color in ((QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, SURFACE),
                        (QPalette.AlternateBase, "#06070a"), (QPalette.Text, TEXT), (QPalette.Button, SURFACE_2),
                        (QPalette.ButtonText, TEXT), (QPalette.Highlight, SELECTION),
                        (QPalette.HighlightedText, TEXT), (QPalette.ToolTipBase, SURFACE_2),
                        (QPalette.ToolTipText, TEXT), (QPalette.PlaceholderText, MUTED)):
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#4b5566"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#4b5566"))
    app.setPalette(palette)
    app.setFont(QFont("Yu Gothic UI", 10))
    app.setStyleSheet(STYLE)


def dark_title_bar(widget) -> None:
    """Windows 10 (1809+) / 11: ask DWM for a dark title bar for this window. Other systems: nothing.

    Only this window's attribute is set (DWMWA_USE_IMMERSIVE_DARK_MODE); no system setting changes.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        value = ctypes.c_int(1)
        for attribute in (20, 19):          # 20 on current Windows, 19 on early Windows 10 builds
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                          ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass
