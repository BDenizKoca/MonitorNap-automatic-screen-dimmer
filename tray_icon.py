"""System tray icon for MonitorNap application."""

import os
from typing import TYPE_CHECKING
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QToolTip, QApplication
from PyQt6.QtGui import QAction, QIcon, QCursor

from logging_utils import log_message

if TYPE_CHECKING:
    from monitornap import MainWindow


def resource_path(relative: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller builds."""
    import sys
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.exists(base):
        return os.path.join(base, relative)
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


class TrayIcon(QSystemTrayIcon):
    """System tray icon with context menu for MonitorNap."""

    def __init__(self, icon: QIcon, parent, main_window: "MainWindow"):
        super().__init__(icon, parent)
        self.main_window = main_window

        # Ensure the icon is set immediately
        self.setIcon(icon)

        # Prepare icons for states (fallback to the same icon if no alt found)
        self.icon_normal = QApplication.instance().app_icon
        awake_candidates = [
            "myicon-awake.ico",
            "icon-awake.png",
            "awake.ico",
            "awake.png",
        ]
        awake_icon_path = None
        for nm in awake_candidates:
            p = resource_path(nm)
            if os.path.exists(p):
                awake_icon_path = p
                break
        self.icon_awake = QIcon(awake_icon_path) if awake_icon_path else QApplication.instance().app_icon

        self._setup_menu()
        self.activated.connect(self.on_click)
        self.refresh_tooltip()

    def _setup_menu(self):
        """Setup the context menu for the tray icon."""
        menu = QMenu(self.parent())

        show_act = QAction("Show/Hide", self)
        show_act.triggered.connect(self.toggle_main_window)
        menu.addAction(show_act)

        toggle_awake_act = QAction("Toggle Awake Mode", self)
        toggle_awake_act.triggered.connect(self.toggle_awake_mode)
        menu.addAction(toggle_awake_act)

        nap_now_act = QAction("Nap Now", self)
        nap_now_act.triggered.connect(self.nap_now)
        menu.addAction(nap_now_act)

        pause_menu = QMenu("Pause Dimming", self.parent())
        for minutes in (15, 30, 60):
            act = QAction(f"{minutes} minutes", self)
            act.triggered.connect(lambda _, m=minutes: self.pause_dimming(m))
            pause_menu.addAction(act)
        menu.addMenu(pause_menu)

        resume_act = QAction("Resume Now", self)
        resume_act.triggered.connect(self.resume_now)
        menu.addAction(resume_act)

        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.exit_app)
        menu.addAction(exit_act)

        self.setContextMenu(menu)

    def refresh_tooltip(self):
        """Update tooltip based on current state."""
        try:
            awake = self.main_window.config.get("awake_mode", False)
            if awake:
                # Check if there's an active pause timer
                if hasattr(self.main_window, "_pause_timer") and self.main_window._pause_timer.isActive():
                    remaining = self.main_window._pause_timer.remainingTime() // 1000 // 60
                    tip = f"MonitorNap - Paused for {remaining} more minutes"
                else:
                    tip = "MonitorNap - Awake (manual)"
            else:
                tip = "MonitorNap - Dimming enabled"
        except Exception:
            tip = "MonitorNap"
        self.setToolTip(tip)

        # Swap tray icon based on awake state
        try:
            awake = self.main_window.config.get("awake_mode", False)
            self.setIcon(self.icon_awake if awake else self.icon_normal)
        except Exception:
            self.setIcon(self.icon_normal)

    def on_click(self, reason):
        """Handle tray icon click."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_main_window()

    def toggle_main_window(self):
        """Toggle visibility of main window."""
        if self.main_window.isVisible():
            self.main_window.hide()
            log_message("Tray: Hiding main window.")
        else:
            self.main_window.showNormal()
            self.main_window.activateWindow()
            log_message("Tray: Showing main window.")

    def toggle_awake_mode(self):
        """Toggle awake mode."""
        self.main_window.toggle_awake_mode()
        self.refresh_tooltip()

    def nap_now(self):
        """Immediately dim all monitors."""
        log_message("Tray: Nap now triggered")
        for ctl in self.main_window.controllers:
            ctl.dim()

    def pause_dimming(self, minutes: int):
        """Pause dimming for specified minutes."""
        log_message(f"Tray: Pause dimming for {minutes} minutes")
        self.main_window.pause_dimming(minutes)
        self.refresh_tooltip()
        QToolTip.showText(QCursor.pos(), f"Dimming paused for {minutes} minutes")

    def resume_now(self):
        """Resume dimming immediately."""
        log_message("Tray: Resume now")
        self.main_window.resume_now()
        self.refresh_tooltip()
        QToolTip.showText(QCursor.pos(), "Dimming resumed")

    def exit_app(self):
        """Exit the application."""
        log_message("Tray: Exiting application.")
        app = QApplication.instance()
        if hasattr(app, 'cleanup'):
            app.cleanup()
        QApplication.quit()
        os._exit(0)
