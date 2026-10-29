"""啟動介面、套用外觀、攔截未處理的錯誤(寫進 crash.log 並顯示,不會整個閃退)。"""
from __future__ import annotations

import os
import sys
import traceback

STYLE = """
* { font-family: "Microsoft JhengHei UI", "Microsoft JhengHei", "Segoe UI", sans-serif; font-size: 10pt; }
QMainWindow, QWidget { background: #f7f8fb; color: #1f2430; }
QToolBar#mainbar { background: #ffffff; border: none; border-bottom: 1px solid #e4e7ee; spacing: 6px; padding: 6px 10px; }
QToolBar QToolButton { padding: 6px 12px; border-radius: 6px; border: none; background: transparent; }
QToolBar QToolButton:hover { background: #eef2f9; }
QToolBar QToolButton::menu-indicator { image: none; }
QPushButton#segL, QPushButton#segR { padding: 5px 12px; border: 1px solid #cfd5e2; background: #ffffff; color: #4a5468; }
QPushButton#segL { border-top-right-radius: 0; border-bottom-right-radius: 0; border-right: none; }
QPushButton#segR { border-top-left-radius: 0; border-bottom-left-radius: 0; }
QPushButton#segL:checked, QPushButton#segR:checked { background: #2f6fd0; color: white; border-color: #2f6fd0; }
QPushButton#toggle { padding: 5px 12px; border-radius: 14px; border: 1px solid #cfd5e2; color: #4a5468; }
QPushButton#toggle:checked { background: #e8f1fd; color: #1f5fbf; border-color: #9cc1f2; }
QPushButton#primaryBig { background: #2f6fd0; color: white; border: none; font-weight: 600; padding: 7px 18px; border-radius: 7px; }
QPushButton#primaryBig:hover { background: #3a7ce0; }
QPushButton#primaryBig:disabled { background: #a9c3ea; }
QListWidget#nav { background: #ffffff; color: #3b4458; border: none; border-right: 1px solid #e4e7ee; font-size: 10.5pt; padding-top: 10px; outline: 0; }
QListWidget#nav::item { padding: 12px 14px; border-left: 3px solid transparent; }
QListWidget#nav::item:hover { background: #f3f6fb; }
QListWidget#nav::item:selected { background: #eaf2fd; color: #1f5fbf; border-left: 3px solid #2f6fd0; font-weight: 600; }
QLabel#pageTitle { font-size: 16pt; font-weight: 600; color: #1f2a44; padding: 4px 0 0 2px; }
QLabel#hint { color: #6b7385; padding: 2px 2px 6px 2px; }
QLabel#formSection { color: #1f5fbf; font-weight: 600; padding-top: 10px; border-bottom: 1px solid #e4e7ee; }
QLabel#readout { background: #ffffff; border: 1px solid #e4e7ee; border-radius: 8px; padding: 8px 10px; }
QLabel#previewTitle { font-size: 11pt; font-weight: 600; color: #1f2a44; }
QLabel#previewInfo { color: #6b7385; padding: 2px 8px 6px 8px; }
QLabel#stage { font-weight: 600; min-width: 120px; color: #33405e; }
QLabel#lastmsg { color: #5b6478; }
QWidget#statusArea { background: #ffffff; border-top: 1px solid #e4e7ee; }
QGroupBox { background: #ffffff; border: 1px solid #e4e7ee; border-radius: 10px; margin-top: 16px; padding: 10px 8px 8px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #33405e; font-weight: 600; }
QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser, QTableWidget {
    background: #ffffff; border: 1px solid #d6dbe5; border-radius: 6px; padding: 4px 6px; selection-background-color: #2f6fd0; }
QLineEdit:hover, QComboBox:hover { border: 1px solid #b9c3d6; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border: 1px solid #2f6fd0; }
QListWidget { background: #ffffff; border: 1px solid #e4e7ee; border-radius: 8px; padding: 4px; outline: 0; }
QListWidget::item { padding: 7px 6px; border-radius: 5px; }
QListWidget::item:selected { background: #eaf2fd; color: #10203a; }
QListWidget::item:hover { background: #f3f6fb; }
QPushButton, QToolButton { background: #ffffff; border: 1px solid #d0d6e1; border-radius: 6px; padding: 5px 11px; }
QPushButton:hover, QToolButton:hover { background: #f1f5fb; }
QPushButton:checked, QToolButton:checked { background: #eaf2fd; border: 1px solid #2f6fd0; color: #1f5fbf; }
QPushButton#primary, QToolButton#primarySmall { background: #2f6fd0; color: white; border: none; font-weight: 600; }
QPushButton#primary:hover, QToolButton#primarySmall:hover { background: #3a7ce0; }
QPushButton#danger { background: #ffffff; color: #b42318; border: 1px solid #f0b8b2; }
QPushButton#danger:hover { background: #fdecea; }
QPushButton#flat { border: none; background: transparent; color: #1f5fbf; padding: 4px 8px; }
QPushButton#flat:hover { background: #eef3fb; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; padding: 7px 16px; border: none; border-bottom: 2px solid transparent; color: #5b6478; }
QTabBar::tab:selected { color: #1f5fbf; border-bottom: 2px solid #2f6fd0; font-weight: 600; }
QPlainTextEdit#log { font-family: Consolas, "Microsoft JhengHei UI"; font-size: 9pt; background: #fbfcfe; color: #33405e; border: 1px solid #e4e7ee; }
QPlainTextEdit#code { font-family: Consolas, monospace; font-size: 9pt; background: #fbfcfe; }
QProgressBar { border: none; border-radius: 7px; background: #edf0f5; text-align: center; color: #33405e; font-size: 8.5pt; }
QProgressBar::chunk { background: #4c9be8; border-radius: 7px; }
QSplitter::handle { background: #eef0f4; }
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical { height: 3px; }
QScrollArea { background: transparent; border: none; }
QToolTip { background: #fffdf3; color: #1f2430; border: 1px solid #d9cf9f; padding: 7px; border-radius: 4px; font-size: 9.5pt; }
"""


def _excepthook(win_ref):
    def hook(t, v, tb):
        txt = "".join(traceback.format_exception(t, v, tb))
        try:
            from lumeasy import lumenv
            os.makedirs(lumenv.APPDATA, exist_ok=True)
            with open(os.path.join(lumenv.APPDATA, "crash.log"), "a", encoding="utf-8") as f:
                f.write(txt + "\n")
        except OSError:
            pass
        w = win_ref()
        if w is not None:
            try:
                w.log("程式錯誤(已記錄,可以繼續用):" + str(v), "error")
                return
            except Exception:  # noqa: BLE001
                pass
        sys.__excepthook__(t, v, tb)
    return hook


def _quick_tip_style():
    from PySide6.QtWidgets import QProxyStyle, QStyle

    class QuickTipStyle(QProxyStyle):
        """滑鼠停 0.35 秒就出現提示(Windows 預設要等比較久)。"""
        def styleHint(self, hint, option=None, widget=None, data=None):
            if hint == QStyle.SH_ToolTip_WakeUpDelay:
                return 350
            if hint == QStyle.SH_ToolTip_FallAsleepDelay:
                return 4000
            return super().styleHint(hint, option, widget, data)
    return QuickTipStyle


def main():
    from PySide6.QtWidgets import QApplication
    QuickTipStyle = _quick_tip_style()
    from PySide6.QtGui import QIcon
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LumEasy.App")
        except Exception:  # noqa: BLE001
            pass
    app = QApplication(sys.argv)
    app.setStyle(QuickTipStyle("Fusion"))
    app.setStyleSheet(STYLE)
    icon = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "icon.ico")
    if not os.path.exists(icon):
        icon = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "icon.ico")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    from lumeasy.gui.mainwin import MainWindow
    import weakref
    w = MainWindow()
    sys.excepthook = _excepthook(weakref.ref(w))
    w.show()
    return app.exec()
