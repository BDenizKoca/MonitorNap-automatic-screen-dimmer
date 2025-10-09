import sys
import os
import json
import time
import signal
import atexit
import threading
import ctypes
from ctypes import wintypes
from collections import deque
from datetime import datetime
from typing import Optional, Dict, List, Any, Callable

import keyboard
from monitorcontrol import get_monitors
import screeninfo

from PyQt6.QtCore import Qt, QTimer, QRect, QObject, QAbstractNativeEventFilter
from PyQt6.QtGui import QIcon, QPainter, QColor, QAction, QCursor, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QCheckBox, QPushButton, QSlider, QLineEdit, QColorDialog,
    QSystemTrayIcon, QMenu, QMessageBox, QGroupBox, QFileDialog, QSpinBox, QToolTip
)

# Platform-specific imports
if os.name == 'nt':
    import win32api
    import win32gui
    import winreg

__version__ = "1.2.0"

# -------------------------------------------------------------------------------------
# Icon Resolution
# -------------------------------------------------------------------------------------
# Resource and Icon Paths (works both in dev and PyInstaller builds)
# -------------------------------------------------------------------------------------
def resource_path(relative: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller onefile/onedir."""
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.exists(base):
        return os.path.join(base, relative)
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)

def resolve_icon_path() -> str:
    for name in ("myicon.ico", "icon.png"):
        p = resource_path(name)
        if os.path.exists(p):
            return p
    return ""

ICON_PATH = resolve_icon_path()

# -------------------------------------------------------------------------------------
# Logging Utilities
# -------------------------------------------------------------------------------------
from logging_utils import log_message, LOG_CACHE, set_debug_mode

# -------------------------------------------------------------------------------------
# Set Process DPI Awareness
# -------------------------------------------------------------------------------------
if os.name == 'nt':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError) as e:
        log_message(f"Failed to set DPI awareness: {e}", debug=True)

# -------------------------------------------------------------------------------------
# Configuration Manager
# -------------------------------------------------------------------------------------
class ConfigManager:
    """Manages application configuration loading and saving."""
    
    def __init__(self) -> None:
        self.CONFIG_FILE = self.get_config_path()
        self.DEFAULT_CONFIG: Dict[str, Any] = {
            "monitors": [],
            "inactivity_limit": 10,
            "overlay_fade_time": 0.5,
            "overlay_fade_steps": 10,
            "awake_mode": False,
            "debug_mode": False,
            "start_on_startup": False,
            "start_minimized": False,
            "awake_mode_shortcut": "ctrl+alt+a"
        }
        self.config = self.load_config()

    def get_config_path(self) -> str:
        """Get the path to the configuration file based on the operating system."""
        if os.name == "nt":
            appdata = os.getenv("APPDATA")
            cfg_dir = os.path.join(appdata, "MonitorNap") if appdata else "."
            os.makedirs(cfg_dir, exist_ok=True)
            return os.path.join(cfg_dir, "monitornap_config.json")
        else:
            return os.path.join(".", "monitornap_config.json")

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file, creating default if not exists."""
        if not os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, "w") as f:
                json.dump(self.DEFAULT_CONFIG, f, indent=4)
            log_message(f"Created default config at {self.CONFIG_FILE}")
            return self.DEFAULT_CONFIG.copy()
        try:
            with open(self.CONFIG_FILE, "r") as f:
                loaded = json.load(f)
            merged = {**self.DEFAULT_CONFIG, **loaded}
            for m in merged["monitors"]:
                m.setdefault("monitor_index", 0)
                # New: keep separate indices for display geometry and DDC/CI
                m.setdefault("display_index", m.get("monitor_index", 0))
                m.setdefault("ddc_index", m.get("monitor_index", 0))
                m.setdefault("enable_hardware_dimming", True)
                m.setdefault("enable_software_dimming", True)
                m.setdefault("hardware_dimming_level", 30)
                m.setdefault("software_dimming_level", 0.5)
                m.setdefault("overlay_color", "#000000")
            log_message(f"Loaded config from {self.CONFIG_FILE}")
            return merged
        except (json.JSONDecodeError, IOError, OSError) as e:
            log_message(f"Error loading config: {e}")
            return self.DEFAULT_CONFIG.copy()

    def save_config(self) -> None:
        """Save current configuration to file."""
        try:
            with open(self.CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
            log_message("Configuration saved.")
        except (IOError, OSError) as e:
            log_message(f"Error saving config: {e}")

# -------------------------------------------------------------------------------------
# Set Startup Registry (Windows)
# -------------------------------------------------------------------------------------
def set_startup_registry(enabled: bool, script_path: Optional[str] = None, args: str = "") -> None:
    """Set or remove application from Windows startup registry.
    
    Args:
        enabled: If True, add to startup; if False, remove from startup
        script_path: Path to executable (defaults to current script)
        args: Command line arguments to pass
    """
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
                value = f"\"{script_path}\" {args}".strip()
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

# Import modular components
from monitor_controller import MonitorController, OverlayWindow
from ui_components import MonitorSettingsWidget, GlobalSettingsWidget, QuickActionsWidget

# MonitorController is now imported from monitor_controller.py

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
    """Main application window for MonitorNap.
    
    This class handles the main UI, user interactions, and coordinates
    between the monitor controllers and configuration management.
    """
    
    def __init__(self, controllers: List[MonitorController], config_manager: ConfigManager) -> None:
        """Initialize the main window.
        
        Args:
            controllers: List of monitor controllers
            config_manager: Configuration manager instance
        """
        super().__init__()
        self.controllers = controllers
        self.config_manager = config_manager
        self.config = config_manager.config

        self.setWindowTitle("MonitorNap")
        self.setWindowIcon(QApplication.instance().app_icon)
        self.resize(720, 480)

        self.record_thread: Optional[RecordHotkeyThread] = None
        self.record_poll_timer = QTimer()
        self.record_poll_timer.setInterval(200)
        self.record_poll_timer.timeout.connect(self.check_record_thread_done)

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        self.status_label = QLabel("MonitorNap is running")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        main_layout.addWidget(self.status_label)

        info_label = QLabel(
            "MonitorNap dims each monitor after a period of inactivity (based on cursor and fullscreen checks).\n"
            "Minimizing to tray does not stop dimming; it continues in the background.\n"
            "Press Exit to quit (brightness will be restored)."
        )
        info_label.setStyleSheet("color: gray; font-size: 10px;")
        main_layout.addWidget(info_label)

        # Global Settings
        global_group = QGroupBox("Global Settings")
        global_layout = QGridLayout(global_group)

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

        self.awake_checkbox = QCheckBox("Awake Mode")
        self.awake_checkbox.setChecked(self.config["awake_mode"])
        self.awake_checkbox.toggled.connect(self.on_awake_toggled)
        global_layout.addWidget(self.awake_checkbox, 1, 0)

        # Shortcut controls
        shortcut_layout = QHBoxLayout()
        self.shortcut_label = QLabel(f"Shortcut: {self.config['awake_mode_shortcut']}")
        self.shortcut_input = QLineEdit()
        self.shortcut_input.setPlaceholderText("e.g. ctrl+alt+a")
        self.record_button = QPushButton("Record Shortcut")
        self.record_button.clicked.connect(self.on_record_shortcut)
        self.shortcut_button = QPushButton("Set Shortcut")
        self.shortcut_button.clicked.connect(self.set_awake_shortcut)
        shortcut_layout.addWidget(self.shortcut_label)
        shortcut_layout.addWidget(self.shortcut_input)
        shortcut_layout.addWidget(self.record_button)
        shortcut_layout.addWidget(self.shortcut_button)
        global_layout.addLayout(shortcut_layout, 1, 1, 1, 2)

        self.startup_checkbox = QCheckBox("Start on Windows Startup" if os.name == 'nt' else "Start on login (not supported)")
        self.startup_checkbox.setChecked(self.config.get("start_on_startup", False))
        if os.name != 'nt':
            self.startup_checkbox.setEnabled(False)
        self.startup_checkbox.toggled.connect(self.on_startup_toggled)
        global_layout.addWidget(self.startup_checkbox, 2, 0)

        self.start_min_checkbox = QCheckBox("Start Minimized to Tray")
        self.start_min_checkbox.setChecked(self.config.get("start_minimized", False))
        self.start_min_checkbox.toggled.connect(self.on_start_min_toggled)
        global_layout.addWidget(self.start_min_checkbox, 2, 1)

        main_layout.addWidget(global_group)

        # Monitor Settings
        monitors_group = QGroupBox("Monitor Settings")
        monitors_layout = QVBoxLayout(monitors_group)
        for ctl in self.controllers:
            mon_ui = self.make_monitor_ui(ctl)
            monitors_layout.addWidget(mon_ui)
            monitors_layout.addSpacing(5)
        main_layout.addWidget(monitors_group)

  # Quick Actions (same as tray menu)
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

        main_layout.addWidget(actions_group)

        # Bottom controls
        bottom_layout = QHBoxLayout()
        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(self.on_apply_clicked)
        bottom_layout.addWidget(btn_apply)
        btn_print_logs = QPushButton("Print Logs")
        btn_print_logs.clicked.connect(self.on_print_logs)
        bottom_layout.addWidget(btn_print_logs)
        btn_minimize = QPushButton("Minimize to Tray")
        btn_minimize.clicked.connect(self.minimize_to_tray)
        bottom_layout.addWidget(btn_minimize)
        btn_exit = QPushButton("Exit")
        btn_exit.setStyleSheet("font-weight: bold;")
        btn_exit.clicked.connect(self.on_exit)
        bottom_layout.addWidget(btn_exit)
        main_layout.addLayout(bottom_layout)

    def toggle_awake_mode(self):
        """Toggle awake mode manually - this should cancel any pause timer"""
        # Clear any active pause timer when manually toggling
        if hasattr(self, "_pause_timer") and self._pause_timer.isActive():
            self._pause_timer.stop()
            log_message("Cleared pause timer due to manual toggle")
        if hasattr(self, "_pause_update_timer"):
            self._pause_update_timer.stop()
        
        new_state = not self.config["awake_mode"]
        self.on_awake_toggled(new_state)

    def make_monitor_ui(self, ctl):
        box = QGroupBox(f"Monitor {ctl.monitor_index + 1}")
        grid = QGridLayout(box)

        # Minimal mapping: a simple display selector and Identify
        row = 0
        monitors = screeninfo.get_monitors()
        disp_count = len(monitors)
        disp_label = QLabel("Display:")
        disp_spin = QSpinBox()
        disp_spin.setRange(0, max(0, disp_count - 1))
        disp_spin.setValue(int(ctl.display_index))
        disp_spin.valueChanged.connect(lambda _=None, c=ctl, ds=disp_spin, b=box: self.on_display_selected(c, ds, b))
        identify_btn = QPushButton("Identify")
        identify_btn.clicked.connect(lambda _: ctl.identify())
        grid.addWidget(disp_label, row, 0)
        grid.addWidget(disp_spin, row, 1)
        grid.addWidget(identify_btn, row, 2)

        # Hardware dimming controls
        row += 1
        hw_check = QCheckBox("Enable Hardware Dimming")
        hw_check.setChecked(ctl.cfg["enable_hardware_dimming"])
        hw_check.toggled.connect(lambda s, c=ctl: self.on_hw_toggled(s, c))
        grid.addWidget(hw_check, row, 0, 1, 3)

        row += 1
        hw_slider_label = QLabel(f"HW Level: {ctl.cfg['hardware_dimming_level']}%")
        hw_slider = QSlider(Qt.Orientation.Horizontal)
        hw_slider.setRange(1, 100)
        hw_slider.setValue(ctl.cfg["hardware_dimming_level"])
        hw_slider.valueChanged.connect(lambda val, c=ctl, lab=hw_slider_label: self.hw_slider_changed(val, c, lab))
        grid.addWidget(hw_slider_label, row, 0)
        grid.addWidget(hw_slider, row, 1, 1, 2)

        # Software dimming controls
        row += 1
        sw_check = QCheckBox("Enable Software Dimming")
        sw_check.setChecked(ctl.cfg["enable_software_dimming"])
        sw_check.toggled.connect(lambda s, c=ctl: self.on_sw_toggled(s, c))
        grid.addWidget(sw_check, row, 0, 1, 3)

        row += 1
        sw_slider_label = QLabel(f"SW Level: {int(ctl.cfg['software_dimming_level']*100)}%")
        sw_slider = QSlider(Qt.Orientation.Horizontal)
        sw_slider.setRange(1, 100)
        sw_slider.setValue(int(ctl.cfg["software_dimming_level"]*100))
        sw_slider.valueChanged.connect(lambda val, c=ctl, lab=sw_slider_label: self.sw_slider_changed(val, c, lab))
        grid.addWidget(sw_slider_label, row, 0)
        grid.addWidget(sw_slider, row, 1, 1, 2)

        # Overlay color and identify button
        row += 1
        color_btn = QPushButton("Overlay Color")
        color_btn.clicked.connect(lambda _: self.pick_overlay_color(ctl))
        grid.addWidget(color_btn, row, 0)
        return box

    def on_display_selected(self, ctl, disp_spin: QSpinBox, box: QGroupBox):
        try:
            new_disp = int(disp_spin.value())
            ctl.cfg["display_index"] = new_disp
            ctl.set_indices(new_disp, ctl.ddc_index)
            box.setTitle(f"Monitor {ctl.monitor_index + 1}")
            # Autosave
            try:
                self.config_manager.save_config()
            except Exception:
                pass
        except Exception as e:
            log_message(f"Failed to set display index: {e}")

    # Removed complex visual selection and status helpers for simplicity

    def nap_now(self):
        """Immediately dim all monitors (same as tray action)"""
        log_message("UI: Nap now triggered")
        for ctl in self.controllers:
            ctl.dim()

    def pause_dimming(self, minutes: int):
        """Pause dimming for specified minutes (same as tray action)"""
        log_message(f"UI: Pause dimming for {minutes} minutes")
        
        # Clear any existing pause timer first
        if hasattr(self, "_pause_timer") and self._pause_timer.isActive():
            self._pause_timer.stop()
        
        # Turn on awake mode if not already on
        if not self.config.get("awake_mode", False):
            self.on_awake_toggled(True)
        
        # Set new pause timer
        self._pause_timer = QTimer(self)
        self._pause_timer.setSingleShot(True)
        self._pause_timer.setInterval(max(1, minutes) * 60 * 1000)
        self._pause_timer.timeout.connect(lambda: self._pause_timeout())
        self._pause_timer.start()
        
        # Set up a periodic update timer to refresh status during pause
        if hasattr(self, "_pause_update_timer"):
            self._pause_update_timer.stop()
        self._pause_update_timer = QTimer(self)
        self._pause_update_timer.setInterval(30000)  # Update every 30 seconds
        self._pause_update_timer.timeout.connect(self._update_pause_status)
        self._pause_update_timer.start()
        
        # Update status to show pause info
        self.status_label.setText(f"Awake Mode ON - Paused for {minutes} minutes")
        log_message(f"Dimming paused for {minutes} minutes")

    def _pause_timeout(self):
        """Called when pause timer expires"""
        log_message("Pause timer expired - resuming dimming")
        # Stop the update timer
        if hasattr(self, "_pause_update_timer"):
            self._pause_update_timer.stop()
        self.on_awake_toggled(False)

    def _update_pause_status(self):
        """Update status label and tray tooltip during pause"""
        if hasattr(self, "_pause_timer") and self._pause_timer.isActive():
            remaining = self._pause_timer.remainingTime() // 1000 // 60
            if remaining > 0:
                self.status_label.setText(f"Awake Mode ON - Paused for {remaining} more minutes")
                # Update tray tooltip
                app = QApplication.instance()
                if hasattr(app, "tray_icon"):
                    try:
                        app.tray_icon.refresh_tooltip()
                    except Exception:
                        pass
            else:
                # Timer about to expire, stop updates
                if hasattr(self, "_pause_update_timer"):
                    self._pause_update_timer.stop()

    def resume_now(self):
        """Resume dimming immediately (same as tray action)"""
        log_message("UI: Resume now")
        # Stop any active pause timer and update timer
        if hasattr(self, "_pause_timer") and self._pause_timer.isActive():
            self._pause_timer.stop()
            log_message("Cleared pause timer due to manual resume")
        if hasattr(self, "_pause_update_timer"):
            self._pause_update_timer.stop()
        # Turn off awake mode
        if self.config.get("awake_mode", False):
            self.on_awake_toggled(False)

    

    def on_apply_clicked(self):
        new_inactivity = self.inactivity_spin.value()
        self.config["inactivity_limit"] = new_inactivity
        self.config_manager.save_config()
        log_message(f"Settings applied: inactivity_limit={new_inactivity}")
        for c in self.controllers:
            c.restore_dim()
            c.last_active = time.time()
        # Silent confirmation instead of noisy message box
        log_message("Settings applied. Dimming timers reset and brightness restored.")

    def on_print_logs(self):
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
            # Silent success log instead of noisy message box
            log_message(f"Logs saved to {filepath}")
        except Exception as e:
            log_message(f"Error saving logs: {e}")

    def closeEvent(self, event):
        log_message("Window close event: hiding to tray.")
        event.ignore()
        self.hide()

    def on_exit(self):
        log_message("Exit clicked. Restoring brightness and exiting.")
        app = QApplication.instance()
        if hasattr(app, "cleanup"):
            app.cleanup()
        QApplication.quit()
        os._exit(0)

    def minimize_to_tray(self):
        log_message("Minimizing to tray.")
        self.hide()

    def hw_slider_changed(self, value, ctl, label):
        ctl.cfg["hardware_dimming_level"] = value
        label.setText(f"HW Level: {value}%")
        # Autosave
        try:
            self.config_manager.save_config()
        except Exception:
            pass

    def sw_slider_changed(self, value, ctl, label):
        ctl.cfg["software_dimming_level"] = value / 100.0
        label.setText(f"SW Level: {value}%")
        # Autosave
        try:
            self.config_manager.save_config()
        except Exception:
            pass

    def on_hw_toggled(self, state, ctl):
        if not state:
            ctl.disable_hw_dimming()
        else:
            ctl.cfg["enable_hardware_dimming"] = True
        try:
            self.config_manager.save_config()
        except Exception:
            pass

    def on_sw_toggled(self, state, ctl):
        if not state:
            ctl.disable_sw_dimming()
        else:
            ctl.cfg["enable_software_dimming"] = True
        try:
            self.config_manager.save_config()
        except Exception:
            pass

    def pick_overlay_color(self, ctl):
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

    def on_awake_toggled(self, state):
        """Handle awake mode changes from any source"""
        # If manually turning OFF awake mode, clear any pause timer
        if not state and hasattr(self, "_pause_timer") and self._pause_timer.isActive():
            self._pause_timer.stop()
            log_message("Cleared pause timer due to manual awake mode OFF")
        if not state and hasattr(self, "_pause_update_timer"):
            self._pause_update_timer.stop()
        
        self.config["awake_mode"] = state
        # Update the checkbox to reflect the current state (avoid infinite loop)
        if self.awake_checkbox.isChecked() != state:
            self.awake_checkbox.blockSignals(True)
            self.awake_checkbox.setChecked(state)
            self.awake_checkbox.blockSignals(False)
        
        if state:
            # Check if this is from a pause timer
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
        
        # Refresh tray tooltip if available
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

    def on_startup_toggled(self, state):
        self.config["start_on_startup"] = state
        args = "--minimized" if self.config.get("start_minimized", False) else ""
        set_startup_registry(state, args=args)
        log_message(f"Start on startup set to {state}")

    def on_start_min_toggled(self, state):
        self.config["start_minimized"] = state
        # If startup is enabled, update the registry command to include/remove the flag
        if self.config.get("start_on_startup", False):
            args = "--minimized" if state else ""
            set_startup_registry(True, args=args)
        log_message(f"Start minimized set to {state}")

    def on_record_shortcut(self):
        if self.record_thread and self.record_thread.is_alive():
            log_message("Hotkey recording already in progress.")
            return
        self.record_thread = RecordHotkeyThread()
        self.record_thread.start()
        self.record_poll_timer.start()
        # Silent recording instead of noisy message box
        log_message("Recording hotkey. Press ESC to cancel.")
        log_message("Started hotkey recording.")

    def check_record_thread_done(self):
        if self.record_thread and not self.record_thread.is_alive():
            self.record_poll_timer.stop()
            result = self.record_thread.result
            self.record_thread = None
            if result and result != "esc":
                log_message(f"Recorded hotkey: {result}")
                self.shortcut_input.setText(result)
            else:
                log_message("Hotkey recording canceled.")

    def set_awake_shortcut(self):
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
            # Silent error instead of noisy warning box
            log_message(f"Failed to set hotkey: {e}")

# -------------------------------------------------------------------------------------
# System Tray Icon
# -------------------------------------------------------------------------------------
class TrayIcon(QSystemTrayIcon):
    def __init__(self, icon, parent, main_window: MainWindow):
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

        menu = QMenu(parent)
        show_act = QAction("Show/Hide", self)
        show_act.triggered.connect(self.toggle_main_window)
        menu.addAction(show_act)

        toggle_awake_act = QAction("Toggle Awake Mode", self)
        toggle_awake_act.triggered.connect(self.toggle_awake_mode)
        menu.addAction(toggle_awake_act)

        nap_now_act = QAction("Nap Now", self)
        nap_now_act.triggered.connect(self.nap_now)
        menu.addAction(nap_now_act)

        pause_menu = QMenu("Pause Dimming", parent)
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
        self.activated.connect(self.on_click)
        self.refresh_tooltip()

    def refresh_tooltip(self):
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
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_main_window()

    def toggle_main_window(self):
        if self.main_window.isVisible():
            self.main_window.hide()
            log_message("Tray: Hiding main window.")
        else:
            self.main_window.showNormal()
            self.main_window.activateWindow()
            log_message("Tray: Showing main window.")

    def toggle_awake_mode(self):
        self.main_window.toggle_awake_mode()
        self.refresh_tooltip()

    def nap_now(self):
        # Immediately dim all monitors regardless of inactivity timer
        log_message("Tray: Nap now triggered")
        for ctl in self.main_window.controllers:
            ctl.dim()

    def pause_dimming(self, minutes: int):
        # Use the main window's pause method for consistency
        log_message(f"Tray: Pause dimming for {minutes} minutes")
        self.main_window.pause_dimming(minutes)
        self.refresh_tooltip()
        # Small visual feedback
        QToolTip.showText(QCursor.pos(), f"Dimming paused for {minutes} minutes")

    def resume_now(self):
        # Use the main window's resume method for consistency
        log_message("Tray: Resume now")
        self.main_window.resume_now()
        self.refresh_tooltip()
        QToolTip.showText(QCursor.pos(), "Dimming resumed")

    def exit_app(self):
        log_message("Tray: Exiting application.")
        app = QApplication.instance()
        if hasattr(app, 'cleanup'):
            app.cleanup()
        QApplication.quit()
        os._exit(0)

# -------------------------------------------------------------------------------------
# Main Application Class
# -------------------------------------------------------------------------------------
class DisplayChangeEventFilter(QAbstractNativeEventFilter):
    WM_DISPLAYCHANGE = 0x007E

    def __init__(self, on_change_callback):
        super().__init__()
        self.on_change_callback = on_change_callback

    def nativeEventFilter(self, eventType, message):
        try:
            # eventType is typically b"windows_generic_MSG" on Windows
            if eventType == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == self.WM_DISPLAYCHANGE:
                    # Debounce: schedule a refresh shortly to coalesce bursts
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
        # Do not filter out the event
        return (False, 0)

class MonitorNapApplication(QApplication):
    def __init__(self, argv, config_manager):
        super().__init__(argv)
        self.setQuitOnLastWindowClosed(False)
        
        # Initialize application icon (now that QApplication exists)
        icon_path = resolve_icon_path()
        if icon_path and os.path.exists(icon_path):
            self.app_icon = QIcon(icon_path)
            log_message(f"Loaded icon from: {icon_path}")
        else:
            log_message("Warning: Icon files not found, using default system icon")
            self.app_icon = QIcon()  # Use default system icon
        self.setWindowIcon(self.app_icon)
        
        self.config_manager = config_manager
        self.config = config_manager.config
        # Set global debug mode flag
        set_debug_mode(bool(self.config.get("debug_mode", False)))

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

        self.main_window = MainWindow(self.controllers, self.config_manager)
        
        # Check if system tray is available
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log_message("System tray is not available on this system")
        
        self.tray_icon = TrayIcon(self.app_icon, self.main_window, self.main_window)
        # Expose tray icon on app for easy access from MainWindow
        setattr(self, "tray_icon", self.tray_icon)
        self.tray_icon.show()
        
        # Force tray icon to be visible and set tooltip
        if self.tray_icon.isVisible():
            log_message("Tray icon is visible")
        else:
            log_message("Warning: Tray icon is not visible")
        self.tray_icon.setToolTip("MonitorNap - Right-click for options")

        old_hotkey = self.config.get("awake_mode_shortcut", "")
        if old_hotkey:
            try:
                keyboard.add_hotkey(old_hotkey, self.main_window.toggle_awake_mode)
                log_message(f"Registered default hotkey: {old_hotkey}")
            except Exception as e:
                # Silent error instead of noisy warning box
                log_message(f"Error registering hotkey {old_hotkey}: {e}")

        # Allow --minimized CLI flag to force minimized startup
        cli_min = any(arg.lower() == "--minimized" for arg in sys.argv[1:])
        if self.config.get("start_minimized", False) or cli_min:
            self.main_window.hide()
            log_message("Starting minimized.")
        else:
            self.main_window.show()
            log_message("Starting with main window visible.")

        # Periodically refresh monitor geometry to handle display changes
        self._geometry_timer = QTimer()
        self._geometry_timer.setInterval(3000)
        self._geometry_timer.timeout.connect(self.refresh_all_geometries)
        self._geometry_timer.start()

        # Install native event filter for instant WM_DISPLAYCHANGE handling - Windows only
        if os.name == 'nt':
            try:
                self._display_event_filter = DisplayChangeEventFilter(self.refresh_all_geometries)
                self.installNativeEventFilter(self._display_event_filter)
                log_message("Installed native WM_DISPLAYCHANGE event filter.")
            except Exception as e:
                log_message(f"Failed to install native event filter: {e}")

    def cleanup(self):
        log_message("Cleaning up: restoring brightness and saving config.")
        for ctl in self.controllers:
            ctl.immediate_restore()  # Immediate restoration of brightness
        self.config_manager.save_config()

    def refresh_all_geometries(self):
        try:
            for ctl in self.controllers:
                ctl.refresh_geometry()
        except Exception as e:
            log_message(f"Geometry refresh error: {e}")

# -------------------------------------------------------------------------------------
# Main Entry Point
# -------------------------------------------------------------------------------------
def main():
    log_message("MonitorNap starting up...")
    signal.signal(signal.SIGINT, lambda sig, frame: QApplication.instance().quit())
    signal.signal(signal.SIGTERM, lambda sig, frame: QApplication.instance().quit())

    # Enable high DPI pixmaps so tray/taskbar icons stay crisp at higher scales
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
