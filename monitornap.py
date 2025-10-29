"""MonitorNap - Automatic monitor dimming application.

Main application entry point and window management.
"""

import sys
import os
import time
import signal
import atexit
import threading
import ctypes
from ctypes import wintypes
from datetime import datetime
from typing import Optional, List, Dict, Any

import keyboard
from monitorcontrol import get_monitors
import screeninfo

from PyQt6.QtCore import Qt, QTimer, QAbstractNativeEventFilter
from PyQt6.QtGui import QIcon, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLabel, QPushButton, QFileDialog, QGroupBox, QColorDialog
)

# Platform-specific imports
if os.name == 'nt':
    import winreg

__version__ = "1.2.1"

# Import local modules
from logging_utils import log_message, LOG_CACHE, set_debug_mode
from monitor_controller import MonitorController
from config_manager import ConfigManager
from tray_icon import TrayIcon
from ui_components import MonitorSettingsWidget


# -------------------------------------------------------------------------------------
# Icon Resolution
# -------------------------------------------------------------------------------------
def resource_path(relative: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller builds."""
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.exists(base):
        return os.path.join(base, relative)
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


def resolve_icon_path() -> str:
    """Resolve icon path from multiple candidates."""
    for name in ("myicon.ico", "icon.png"):
        p = resource_path(name)
        if os.path.exists(p):
            return p
    return ""


ICON_PATH = resolve_icon_path()


# -------------------------------------------------------------------------------------
# Set Process DPI Awareness
# -------------------------------------------------------------------------------------
if os.name == 'nt':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError) as e:
        log_message(f"Failed to set DPI awareness: {e}", debug=True)


# -------------------------------------------------------------------------------------
# Windows Startup Registry
# -------------------------------------------------------------------------------------
def set_startup_registry(enabled: bool, script_path: Optional[str] = None, args: str = "") -> None:
    """Set or remove application from Windows startup registry."""
    if os.name != 'nt':
        log_message("Startup registry not supported on this platform.")
        return
    reg_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "MonitorNap"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_key_path, 0, winreg.KEY_ALL_ACCESS) as key:
            if enabled:
                if not script_path:
                    script_path = os.path.abspath(sys.argv[0])
                value = f'"{script_path}" {args}'.strip()
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, value)
                log_message(f"Set MonitorNap to start at login: {value}")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    log_message("Removed MonitorNap from startup.")
                except FileNotFoundError:
                    log_message("MonitorNap not found in startup registry.")
    except (OSError, PermissionError, FileNotFoundError) as e:
        log_message(f"Failed to modify startup registry: {e}")


# -------------------------------------------------------------------------------------
# Hotkey Recording Thread
# -------------------------------------------------------------------------------------
class RecordHotkeyThread(threading.Thread):
    """Thread for recording global hotkey combinations."""

    def __init__(self) -> None:
        super().__init__()
        self.result: Optional[str] = None

    def run(self) -> None:
        """Record a hotkey combination from user input."""
        try:
            self.result = keyboard.read_hotkey(suppress=False)
        except Exception as e:
            log_message(f"Error reading hotkey: {e}")
            self.result = None


# -------------------------------------------------------------------------------------
# Main Application Window
# -------------------------------------------------------------------------------------
class MainWindow(QMainWindow):
    """Main application window for MonitorNap."""

    def __init__(self, controllers: List[MonitorController], config_manager: ConfigManager) -> None:
        super().__init__()
        self.controllers = controllers
        self.config_manager = config_manager
        self.config = config_manager.config

        self.setWindowTitle("MonitorNap")
        self.setWindowIcon(QApplication.instance().app_icon)
        self.resize(750, 600)

        self.record_thread: Optional[RecordHotkeyThread] = None
        self.record_poll_timer = QTimer()
        self.record_poll_timer.setInterval(200)
        self.record_poll_timer.timeout.connect(self._check_record_thread_done)

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        # Main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # Status label
        self.status_label = QLabel("MonitorNap is running")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        main_layout.addWidget(self.status_label)

        # Info label
        info_label = QLabel(
            "MonitorNap dims each monitor after a period of inactivity (based on cursor and fullscreen checks).\n"
            "Minimizing to tray does not stop dimming; it continues in the background.\n"
            "Press Exit to quit (brightness will be restored)."
        )
        info_label.setStyleSheet("color: gray; font-size: 10px;")
        main_layout.addWidget(info_label)

        # Global Settings Group
        self._add_global_settings(main_layout)

        # Monitor Settings Group (scrollable)
        self._add_monitor_settings(main_layout)

        # Quick Actions Group
        self._add_quick_actions(main_layout)

        # Bottom controls
        self._add_bottom_controls(main_layout)

    def _add_global_settings(self, layout: QVBoxLayout):
        """Add global settings section."""
        from PyQt6.QtWidgets import QGridLayout, QCheckBox, QSlider, QSpinBox, QLineEdit

        global_group = QGroupBox("Global Settings")
        global_layout = QGridLayout(global_group)

        # Inactivity settings
        inactivity_label = QLabel("Inactivity (s):")
        self.inactivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.inactivity_slider.setRange(1, 600)
        self.inactivity_slider.setValue(self.config["inactivity_limit"])
        self.inactivity_spin = QSpinBox()
        self.inactivity_spin.setRange(1, 600)
        self.inactivity_spin.setValue(self.config["inactivity_limit"])
        self.inactivity_slider.valueChanged.connect(self.inactivity_spin.setValue)
        self.inactivity_spin.valueChanged.connect(self.inactivity_slider.setValue)
        global_layout.addWidget(inactivity_label, 0, 0)
        global_layout.addWidget(self.inactivity_slider, 0, 1)
        global_layout.addWidget(self.inactivity_spin, 0, 2)

        # Awake mode
        self.awake_checkbox = QCheckBox("Awake Mode")
        self.awake_checkbox.setChecked(self.config["awake_mode"])
        self.awake_checkbox.toggled.connect(self.on_awake_toggled)
        global_layout.addWidget(self.awake_checkbox, 1, 0)

        # Shortcut controls
        from PyQt6.QtWidgets import QHBoxLayout
        shortcut_layout = QHBoxLayout()
        self.shortcut_label = QLabel(f"Shortcut: {self.config['awake_mode_shortcut']}")
        self.shortcut_input = QLineEdit()
        self.shortcut_input.setPlaceholderText("e.g. ctrl+alt+a")
        self.record_button = QPushButton("Record Shortcut")
        self.record_button.clicked.connect(self._on_record_shortcut)
        self.shortcut_button = QPushButton("Set Shortcut")
        self.shortcut_button.clicked.connect(self._set_awake_shortcut)
        shortcut_layout.addWidget(self.shortcut_label)
        shortcut_layout.addWidget(self.shortcut_input)
        shortcut_layout.addWidget(self.record_button)
        shortcut_layout.addWidget(self.shortcut_button)
        global_layout.addLayout(shortcut_layout, 1, 1, 1, 2)

        # Startup options
        self.startup_checkbox = QCheckBox("Start on Windows Startup" if os.name == 'nt' else "Start on login (not supported)")
        self.startup_checkbox.setChecked(self.config.get("start_on_startup", False))
        if os.name != 'nt':
            self.startup_checkbox.setEnabled(False)
        self.startup_checkbox.toggled.connect(self._on_startup_toggled)
        global_layout.addWidget(self.startup_checkbox, 2, 0)

        self.start_min_checkbox = QCheckBox("Start Minimized to Tray")
        self.start_min_checkbox.setChecked(self.config.get("start_minimized", False))
        self.start_min_checkbox.toggled.connect(self._on_start_min_toggled)
        global_layout.addWidget(self.start_min_checkbox, 2, 1)

        layout.addWidget(global_group)

    def _add_monitor_settings(self, layout: QVBoxLayout):
        """Add monitor settings section with scrollable content."""
        from PyQt6.QtWidgets import QScrollArea

        monitors_group = QGroupBox("Monitor Settings")
        group_layout = QVBoxLayout(monitors_group)

        # Create scroll area for monitors
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(300)  # Limit height to ~2-3 monitors visible

        # Container widget for monitor widgets
        scroll_content = QWidget()
        monitors_layout = QVBoxLayout(scroll_content)
        monitors_layout.setContentsMargins(0, 0, 0, 0)

        for ctl in self.controllers:
            mon_widget = MonitorSettingsWidget(
                monitor_index=ctl.monitor_index,
                config=ctl.cfg,
                controller=ctl,
                on_color_picked=lambda c=ctl: self._pick_overlay_color(c)
            )
            monitors_layout.addWidget(mon_widget)
            monitors_layout.addSpacing(5)

        monitors_layout.addStretch()
        scroll.setWidget(scroll_content)
        group_layout.addWidget(scroll)
        layout.addWidget(monitors_group)

    def _add_quick_actions(self, layout: QVBoxLayout):
        """Add quick actions section."""
        from PyQt6.QtWidgets import QHBoxLayout

        actions_group = QGroupBox("Quick Actions")
        actions_layout = QHBoxLayout(actions_group)

        nap_now_btn = QPushButton("Nap Now")
        nap_now_btn.setToolTip("Immediately dim all monitors")
        nap_now_btn.clicked.connect(self.nap_now)

        resume_now_btn = QPushButton("Resume Now")
        resume_now_btn.setToolTip("Resume dimming immediately (cancel any pause)")
        resume_now_btn.clicked.connect(self.resume_now)

        pause_label = QLabel("Pause Dimming:")

        actions_layout.addWidget(nap_now_btn)
        actions_layout.addWidget(resume_now_btn)
        actions_layout.addWidget(pause_label)

        for minutes in (15, 30, 60):
            btn = QPushButton(f"{minutes} min")
            btn.clicked.connect(lambda _, m=minutes: self.pause_dimming(m))
            actions_layout.addWidget(btn)

        layout.addWidget(actions_group)

    def _add_bottom_controls(self, layout: QVBoxLayout):
        """Add bottom control buttons."""
        from PyQt6.QtWidgets import QHBoxLayout

        bottom_layout = QHBoxLayout()

        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(self._on_apply_clicked)
        bottom_layout.addWidget(btn_apply)

        btn_print_logs = QPushButton("Print Logs")
        btn_print_logs.clicked.connect(self._on_print_logs)
        bottom_layout.addWidget(btn_print_logs)

        btn_minimize = QPushButton("Minimize to Tray")
        btn_minimize.clicked.connect(self.minimize_to_tray)
        bottom_layout.addWidget(btn_minimize)

        btn_exit = QPushButton("Exit")
        btn_exit.setStyleSheet("font-weight: bold;")
        btn_exit.clicked.connect(self._on_exit)
        bottom_layout.addWidget(btn_exit)

        layout.addLayout(bottom_layout)

    # Action handlers
    def toggle_awake_mode(self):
        """Toggle awake mode manually."""
        if hasattr(self, "_pause_timer") and self._pause_timer.isActive():
            self._pause_timer.stop()
            log_message("Cleared pause timer due to manual toggle")
        if hasattr(self, "_pause_update_timer"):
            self._pause_update_timer.stop()

        new_state = not self.config["awake_mode"]
        self.on_awake_toggled(new_state)

    def nap_now(self):
        """Immediately dim all monitors."""
        log_message("UI: Nap now triggered")
        for ctl in self.controllers:
            ctl.dim()

    def pause_dimming(self, minutes: int):
        """Pause dimming for specified minutes."""
        log_message(f"UI: Pause dimming for {minutes} minutes")

        if hasattr(self, "_pause_timer") and self._pause_timer.isActive():
            self._pause_timer.stop()

        if not self.config.get("awake_mode", False):
            self.on_awake_toggled(True)

        self._pause_timer = QTimer(self)
        self._pause_timer.setSingleShot(True)
        self._pause_timer.setInterval(max(1, minutes) * 60 * 1000)
        self._pause_timer.timeout.connect(self._pause_timeout)
        self._pause_timer.start()

        if hasattr(self, "_pause_update_timer"):
            self._pause_update_timer.stop()
        self._pause_update_timer = QTimer(self)
        self._pause_update_timer.setInterval(30000)
        self._pause_update_timer.timeout.connect(self._update_pause_status)
        self._pause_update_timer.start()

        self.status_label.setText(f"Awake Mode ON - Paused for {minutes} minutes")
        log_message(f"Dimming paused for {minutes} minutes")

    def resume_now(self):
        """Resume dimming immediately."""
        log_message("UI: Resume now")
        if hasattr(self, "_pause_timer") and self._pause_timer.isActive():
            self._pause_timer.stop()
            log_message("Cleared pause timer due to manual resume")
        if hasattr(self, "_pause_update_timer"):
            self._pause_update_timer.stop()
        if self.config.get("awake_mode", False):
            self.on_awake_toggled(False)

    def on_awake_toggled(self, state: bool):
        """Handle awake mode changes."""
        if not state and hasattr(self, "_pause_timer") and self._pause_timer.isActive():
            self._pause_timer.stop()
            log_message("Cleared pause timer due to manual awake mode OFF")
        if not state and hasattr(self, "_pause_update_timer"):
            self._pause_update_timer.stop()

        self.config["awake_mode"] = state
        if self.awake_checkbox.isChecked() != state:
            self.awake_checkbox.blockSignals(True)
            self.awake_checkbox.setChecked(state)
            self.awake_checkbox.blockSignals(False)

        if state:
            pause_active = hasattr(self, "_pause_timer") and self._pause_timer.isActive()
            if pause_active:
                remaining = self._pause_timer.remainingTime() // 1000 // 60
                self.status_label.setText(f"Awake Mode ON - Paused for {remaining} more minutes")
            else:
                self.status_label.setText("Awake Mode is ON (no dimming)")
            log_message("Awake Mode turned ON")
        else:
            self.status_label.setText("MonitorNap is running")
            for c in self.controllers:
                c.last_active = time.time()
            log_message("Awake Mode turned OFF")

        app = QApplication.instance()
        if hasattr(app, "tray_icon"):
            try:
                app.tray_icon.refresh_tooltip()
            except Exception:
                pass
        try:
            self.config_manager.save_config()
        except Exception:
            pass

    def _pause_timeout(self):
        """Called when pause timer expires."""
        log_message("Pause timer expired - resuming dimming")
        if hasattr(self, "_pause_update_timer"):
            self._pause_update_timer.stop()
        self.on_awake_toggled(False)

    def _update_pause_status(self):
        """Update status label during pause."""
        if hasattr(self, "_pause_timer") and self._pause_timer.isActive():
            remaining = self._pause_timer.remainingTime() // 1000 // 60
            if remaining > 0:
                self.status_label.setText(f"Awake Mode ON - Paused for {remaining} more minutes")
                app = QApplication.instance()
                if hasattr(app, "tray_icon"):
                    try:
                        app.tray_icon.refresh_tooltip()
                    except Exception:
                        pass
            else:
                if hasattr(self, "_pause_update_timer"):
                    self._pause_update_timer.stop()

    def _pick_overlay_color(self, ctl: MonitorController):
        """Pick overlay color for a monitor."""
        color = QColorDialog.getColor(QColor(ctl.cfg["overlay_color"]), self, "Select Overlay Color")
        if color.isValid():
            ctl.cfg["overlay_color"] = color.name()
            if ctl.overlay:
                ctl.overlay.set_overlay_color(color.name())
            log_message(f"Overlay color changed to {color.name()}")
            try:
                self.config_manager.save_config()
            except Exception:
                pass

    def _on_apply_clicked(self):
        """Apply settings."""
        new_inactivity = self.inactivity_spin.value()
        self.config["inactivity_limit"] = new_inactivity
        self.config_manager.save_config()
        log_message(f"Settings applied: inactivity_limit={new_inactivity}")
        for c in self.controllers:
            c.restore_dim()
            c.last_active = time.time()
        log_message("Settings applied. Dimming timers reset and brightness restored.")

    def _on_print_logs(self):
        """Save logs to file."""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Logs")
        if not folder:
            log_message("Print logs canceled.")
            return
        filename = f"MonitorNap-Logs-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        filepath = os.path.join(folder, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                for line in LOG_CACHE:
                    f.write(line + "\n")
            log_message(f"Logs saved to {filepath}")
        except Exception as e:
            log_message(f"Error saving logs: {e}")

    def _on_startup_toggled(self, state: bool):
        """Handle startup toggle."""
        self.config["start_on_startup"] = state
        args = "--minimized" if self.config.get("start_minimized", False) else ""
        set_startup_registry(state, args=args)
        log_message(f"Start on startup set to {state}")

    def _on_start_min_toggled(self, state: bool):
        """Handle start minimized toggle."""
        self.config["start_minimized"] = state
        if self.config.get("start_on_startup", False):
            args = "--minimized" if state else ""
            set_startup_registry(True, args=args)
        log_message(f"Start minimized set to {state}")

    def _on_record_shortcut(self):
        """Start recording a hotkey."""
        if self.record_thread and self.record_thread.is_alive():
            log_message("Hotkey recording already in progress.")
            return
        self.record_thread = RecordHotkeyThread()
        self.record_thread.start()
        self.record_poll_timer.start()
        log_message("Recording hotkey. Press ESC to cancel.")

    def _check_record_thread_done(self):
        """Check if hotkey recording is complete."""
        if self.record_thread and not self.record_thread.is_alive():
            self.record_poll_timer.stop()
            result = self.record_thread.result
            self.record_thread = None
            if result and result != "esc":
                log_message(f"Recorded hotkey: {result}")
                self.shortcut_input.setText(result)
            else:
                log_message("Hotkey recording canceled.")

    def _set_awake_shortcut(self):
        """Set new awake mode shortcut."""
        new_hotkey = self.shortcut_input.text().strip()
        if not new_hotkey:
            return
        old_hotkey = self.config.get("awake_mode_shortcut", "")
        try:
            keyboard.remove_hotkey(old_hotkey)
        except KeyError:
            pass
        try:
            keyboard.add_hotkey(new_hotkey, self.toggle_awake_mode)
            self.config["awake_mode_shortcut"] = new_hotkey
            log_message(f"Set new awake hotkey to {new_hotkey}")
            self.shortcut_label.setText(f"Shortcut: {new_hotkey}")
        except Exception as e:
            log_message(f"Failed to set hotkey: {e}")

    def closeEvent(self, event):
        """Handle window close event."""
        log_message("Window close event: hiding to tray.")
        event.ignore()
        self.hide()

    def _on_exit(self):
        """Exit the application."""
        log_message("Exit clicked. Restoring brightness and exiting.")
        app = QApplication.instance()
        if hasattr(app, "cleanup"):
            app.cleanup()
        QApplication.quit()
        os._exit(0)

    def minimize_to_tray(self):
        """Minimize window to tray."""
        log_message("Minimizing to tray.")
        self.hide()


# -------------------------------------------------------------------------------------
# Display Change Event Filter (Windows)
# -------------------------------------------------------------------------------------
class DisplayChangeEventFilter(QAbstractNativeEventFilter):
    """Filter for detecting display configuration changes on Windows."""

    WM_DISPLAYCHANGE = 0x007E

    def __init__(self, on_change_callback):
        super().__init__()
        self.on_change_callback = on_change_callback

    def nativeEventFilter(self, eventType, message):
        try:
            if eventType == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == self.WM_DISPLAYCHANGE:
                    app = QApplication.instance()
                    try:
                        if getattr(app, "_display_change_debounce", None):
                            app._display_change_debounce.stop()
                    except Exception:
                        pass
                    app._display_change_debounce = QTimer()
                    app._display_change_debounce.setSingleShot(True)
                    app._display_change_debounce.setInterval(200)
                    app._display_change_debounce.timeout.connect(self.on_change_callback)
                    app._display_change_debounce.start()
        except Exception as e:
            log_message(f"Native event filter error: {e}")
        return (False, 0)


# -------------------------------------------------------------------------------------
# Main Application Class
# -------------------------------------------------------------------------------------
class MonitorNapApplication(QApplication):
    """Main application class for MonitorNap."""

    def __init__(self, argv, config_manager: ConfigManager):
        super().__init__(argv)
        self.setQuitOnLastWindowClosed(False)

        # Initialize application icon
        icon_path = resolve_icon_path()
        if icon_path and os.path.exists(icon_path):
            self.app_icon = QIcon(icon_path)
            log_message(f"Loaded icon from: {icon_path}")
        else:
            log_message("Warning: Icon files not found, using default system icon")
            self.app_icon = QIcon()
        self.setWindowIcon(self.app_icon)

        self.config_manager = config_manager
        self.config = config_manager.config
        set_debug_mode(bool(self.config.get("debug_mode", False)))

        # Initialize monitor controllers
        self.controllers = []
        if not self.config["monitors"]:
            monitors = screeninfo.get_monitors()
            for i in range(len(monitors)):
                new_m = {
                    "monitor_index": i,
                    "display_index": i,
                    "ddc_index": i,
                    "enable_hardware_dimming": True,
                    "enable_software_dimming": True,
                    "hardware_dimming_level": 30,
                    "software_dimming_level": 0.5,
                    "overlay_color": "#000000"
                }
                self.config["monitors"].append(new_m)
            log_message("Auto-created monitor config from enumeration.")

        for mcfg in self.config["monitors"]:
            ctl = MonitorController(mcfg, self.config)
            self.controllers.append(ctl)

        # Create main window
        self.main_window = MainWindow(self.controllers, self.config_manager)

        # Create system tray icon
        from PyQt6.QtWidgets import QSystemTrayIcon
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log_message("System tray is not available on this system")

        self.tray_icon = TrayIcon(self.app_icon, self.main_window, self.main_window)
        self.tray_icon.show()

        if self.tray_icon.isVisible():
            log_message("Tray icon is visible")
        else:
            log_message("Warning: Tray icon is not visible")
        self.tray_icon.setToolTip("MonitorNap - Right-click for options")

        # Register global hotkey
        old_hotkey = self.config.get("awake_mode_shortcut", "")
        if old_hotkey:
            try:
                keyboard.add_hotkey(old_hotkey, self.main_window.toggle_awake_mode)
                log_message(f"Registered default hotkey: {old_hotkey}")
            except Exception as e:
                log_message(f"Error registering hotkey {old_hotkey}: {e}")

        # Show or hide window based on startup settings
        cli_min = any(arg.lower() == "--minimized" for arg in sys.argv[1:])
        if self.config.get("start_minimized", False) or cli_min:
            self.main_window.hide()
            log_message("Starting minimized.")
        else:
            self.main_window.show()
            log_message("Starting with main window visible.")

        # Periodic geometry refresh
        self._geometry_timer = QTimer()
        self._geometry_timer.setInterval(3000)
        self._geometry_timer.timeout.connect(self.refresh_all_geometries)
        self._geometry_timer.start()

        # Install native event filter for Windows display changes
        if os.name == 'nt':
            try:
                self._display_event_filter = DisplayChangeEventFilter(self.refresh_all_geometries)
                self.installNativeEventFilter(self._display_event_filter)
                log_message("Installed native WM_DISPLAYCHANGE event filter.")
            except Exception as e:
                log_message(f"Failed to install native event filter: {e}")

    def cleanup(self):
        """Cleanup before exit."""
        log_message("Cleaning up: restoring brightness and saving config.")
        for ctl in self.controllers:
            ctl.immediate_restore()
        self.config_manager.save_config()

    def refresh_all_geometries(self):
        """Refresh geometry for all monitors."""
        try:
            for ctl in self.controllers:
                ctl.refresh_geometry()
        except Exception as e:
            log_message(f"Geometry refresh error: {e}")


# -------------------------------------------------------------------------------------
# Main Entry Point
# -------------------------------------------------------------------------------------
def main():
    """Main entry point for MonitorNap application."""
    log_message("MonitorNap starting up...")
    signal.signal(signal.SIGINT, lambda sig, frame: QApplication.instance().quit())
    signal.signal(signal.SIGTERM, lambda sig, frame: QApplication.instance().quit())

    # Enable high DPI support
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass

    config_manager = ConfigManager()
    app = MonitorNapApplication(sys.argv, config_manager)
    atexit.register(lambda: (app.cleanup(), log_message("MonitorNap has shut down.")))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
