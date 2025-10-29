"""UI Components for MonitorNap application.

This module contains UI helper classes and components to keep the main
application file clean and maintainable.
"""

from typing import Dict, Any, Optional, Callable, TYPE_CHECKING
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QCheckBox, QPushButton, QSlider, QSpinBox
)

from logging_utils import log_message

if TYPE_CHECKING:
    from monitor_controller import MonitorController


class MonitorSettingsWidget(QGroupBox):
    """Widget for individual monitor settings."""

    def __init__(self, monitor_index: int, config: Dict[str, Any],
                 controller: "MonitorController",
                 on_color_picked: Callable):
        super().__init__(f"Monitor {monitor_index + 1}")
        self.monitor_index = monitor_index
        self.config = config
        self.controller = controller
        self.on_color_picked = on_color_picked

        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Set up the monitor settings UI."""
        grid = QGridLayout(self)

        # Display selector and identify button
        row = 0
        import screeninfo
        monitors = screeninfo.get_monitors()
        disp_count = len(monitors)

        disp_label = QLabel("Display:")
        self.disp_spin = QSpinBox()
        self.disp_spin.setRange(0, max(0, disp_count - 1))
        self.disp_spin.setValue(int(self.config.get("display_index", 0)))
        self.disp_spin.valueChanged.connect(self._on_display_selected)

        identify_btn = QPushButton("Identify")
        identify_btn.clicked.connect(lambda: self.controller.identify())

        grid.addWidget(disp_label, row, 0)
        grid.addWidget(self.disp_spin, row, 1)
        grid.addWidget(identify_btn, row, 2)
        
        # Hardware dimming controls
        row += 1
        self.hw_check = QCheckBox("Enable Hardware Dimming")
        self.hw_check.setChecked(self.config.get("enable_hardware_dimming", True))
        self.hw_check.toggled.connect(self._on_hw_toggled)
        grid.addWidget(self.hw_check, row, 0, 1, 3)
        
        row += 1
        self.hw_slider_label = QLabel(f"HW Level: {self.config.get('hardware_dimming_level', 30)}%")
        self.hw_slider = QSlider(Qt.Orientation.Horizontal)
        self.hw_slider.setRange(1, 100)
        self.hw_slider.setValue(self.config.get("hardware_dimming_level", 30))
        self.hw_slider.valueChanged.connect(self._on_hw_slider_changed)
        grid.addWidget(self.hw_slider_label, row, 0)
        grid.addWidget(self.hw_slider, row, 1, 1, 2)
        
        # Software dimming controls
        row += 1
        self.sw_check = QCheckBox("Enable Software Dimming")
        self.sw_check.setChecked(self.config.get("enable_software_dimming", True))
        self.sw_check.toggled.connect(self._on_sw_toggled)
        grid.addWidget(self.sw_check, row, 0, 1, 3)
        
        row += 1
        sw_level = int(self.config.get("software_dimming_level", 0.5) * 100)
        self.sw_slider_label = QLabel(f"SW Level: {sw_level}%")
        self.sw_slider = QSlider(Qt.Orientation.Horizontal)
        self.sw_slider.setRange(1, 100)
        self.sw_slider.setValue(sw_level)
        self.sw_slider.valueChanged.connect(self._on_sw_slider_changed)
        grid.addWidget(self.sw_slider_label, row, 0)
        grid.addWidget(self.sw_slider, row, 1, 1, 2)
        
        # Overlay color button
        row += 1
        color_btn = QPushButton("Overlay Color")
        color_btn.clicked.connect(self._on_color_picked)
        grid.addWidget(color_btn, row, 0)
    
    def _on_display_selected(self) -> None:
        """Handle display selection change."""
        try:
            new_disp = int(self.disp_spin.value())
            self.config["display_index"] = new_disp
            self.controller.set_indices(new_disp, self.controller.ddc_index)
            self.setTitle(f"Monitor {self.controller.monitor_index + 1}")
        except Exception as e:
            log_message(f"Failed to set display index: {e}")

    def _on_hw_toggled(self, state: bool) -> None:
        """Handle hardware dimming toggle."""
        if not state:
            self.controller.disable_hw_dimming()
        else:
            self.config["enable_hardware_dimming"] = True

    def _on_sw_toggled(self, state: bool) -> None:
        """Handle software dimming toggle."""
        if not state:
            self.controller.disable_sw_dimming()
        else:
            self.config["enable_software_dimming"] = True

    def _on_hw_slider_changed(self, value: int) -> None:
        """Handle hardware dimming slider change."""
        self.config["hardware_dimming_level"] = value
        self.hw_slider_label.setText(f"HW Level: {value}%")

    def _on_sw_slider_changed(self, value: int) -> None:
        """Handle software dimming slider change."""
        self.config["software_dimming_level"] = value / 100.0
        self.sw_slider_label.setText(f"SW Level: {value}%")

    def _on_color_picked(self) -> None:
        """Handle color picker button click."""
        self.on_color_picked()


class GlobalSettingsWidget(QGroupBox):
    """Widget for global application settings."""
    
    def __init__(self, config: Dict[str, Any], on_inactivity_changed: Callable,
                 on_awake_toggled: Callable, on_startup_toggled: Callable,
                 on_start_min_toggled: Callable, on_record_shortcut: Callable,
                 on_set_shortcut: Callable):
        super().__init__("Global Settings")
        self.config = config
        self.on_inactivity_changed = on_inactivity_changed
        self.on_awake_toggled = on_awake_toggled
        self.on_startup_toggled = on_startup_toggled
        self.on_start_min_toggled = on_start_min_toggled
        self.on_record_shortcut = on_record_shortcut
        self.on_set_shortcut = on_set_shortcut
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Set up the global settings UI."""
        import os
        grid = QGridLayout(self)
        
        # Inactivity settings
        inactivity_label = QLabel("Inactivity (s):")
        self.inactivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.inactivity_slider.setRange(1, 600)
        self.inactivity_slider.setValue(self.config.get("inactivity_limit", 10))
        self.inactivity_spin = QSpinBox()
        self.inactivity_spin.setRange(1, 600)
        self.inactivity_spin.setValue(self.config.get("inactivity_limit", 10))
        self.inactivity_slider.valueChanged.connect(self.inactivity_spin.setValue)
        self.inactivity_spin.valueChanged.connect(self.inactivity_slider.setValue)
        self.inactivity_spin.valueChanged.connect(self._on_inactivity_changed)
        
        grid.addWidget(inactivity_label, 0, 0)
        grid.addWidget(self.inactivity_slider, 0, 1)
        grid.addWidget(self.inactivity_spin, 0, 2)
        
        # Awake mode
        self.awake_checkbox = QCheckBox("Awake Mode")
        self.awake_checkbox.setChecked(self.config.get("awake_mode", False))
        self.awake_checkbox.toggled.connect(self.on_awake_toggled)
        grid.addWidget(self.awake_checkbox, 1, 0)
        
        # Shortcut controls
        shortcut_layout = QHBoxLayout()
        self.shortcut_label = QLabel(f"Shortcut: {self.config.get('awake_mode_shortcut', 'ctrl+alt+a')}")
        self.shortcut_input = QLineEdit()
        self.shortcut_input.setPlaceholderText("e.g. ctrl+alt+a")
        self.record_button = QPushButton("Record Shortcut")
        self.record_button.clicked.connect(self.on_record_shortcut)
        self.shortcut_button = QPushButton("Set Shortcut")
        self.shortcut_button.clicked.connect(self.on_set_shortcut)
        shortcut_layout.addWidget(self.shortcut_label)
        shortcut_layout.addWidget(self.shortcut_input)
        shortcut_layout.addWidget(self.record_button)
        shortcut_layout.addWidget(self.shortcut_button)
        grid.addLayout(shortcut_layout, 1, 1, 1, 2)
        
        # Startup options
        self.startup_checkbox = QCheckBox("Start on Windows Startup" if os.name == 'nt' else "Start on login (not supported)")
        self.startup_checkbox.setChecked(self.config.get("start_on_startup", False))
        if os.name != 'nt':
            self.startup_checkbox.setEnabled(False)
        self.startup_checkbox.toggled.connect(self.on_startup_toggled)
        grid.addWidget(self.startup_checkbox, 2, 0)
        
        self.start_min_checkbox = QCheckBox("Start Minimized to Tray")
        self.start_min_checkbox.setChecked(self.config.get("start_minimized", False))
        self.start_min_checkbox.toggled.connect(self.on_start_min_toggled)
        grid.addWidget(self.start_min_checkbox, 2, 1)
    
    def _on_inactivity_changed(self, value: int) -> None:
        """Handle inactivity limit change."""
        self.config["inactivity_limit"] = value
        self.on_inactivity_changed(value)
    
    def update_awake_state(self, state: bool) -> None:
        """Update awake checkbox state without triggering events."""
        self.awake_checkbox.blockSignals(True)
        self.awake_checkbox.setChecked(state)
        self.awake_checkbox.blockSignals(False)


class QuickActionsWidget(QGroupBox):
    """Widget for quick action buttons."""
    
    def __init__(self, on_nap_now: Callable, on_resume_now: Callable,
                 on_pause_dimming: Callable):
        super().__init__("Quick Actions")
        self.on_nap_now = on_nap_now
        self.on_resume_now = on_resume_now
        self.on_pause_dimming = on_pause_dimming
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Set up the quick actions UI."""
        layout = QHBoxLayout(self)
        
        nap_now_btn = QPushButton("Nap Now")
        nap_now_btn.setToolTip("Immediately dim all monitors")
        nap_now_btn.clicked.connect(self.on_nap_now)
        
        resume_now_btn = QPushButton("Resume Now")
        resume_now_btn.setToolTip("Resume dimming immediately (cancel any pause)")
        resume_now_btn.clicked.connect(self.on_resume_now)
        
        pause_label = QLabel("Pause Dimming:")
        
        layout.addWidget(nap_now_btn)
        layout.addWidget(resume_now_btn)
        layout.addWidget(pause_label)
        
        for minutes in (15, 30, 60):
            btn = QPushButton(f"{minutes} min")
            btn.clicked.connect(lambda _, m=minutes: self.on_pause_dimming(m))
            layout.addWidget(btn)