"""Monitor Controller for MonitorNap application.

This module contains the MonitorController class that handles individual
monitor dimming, activity detection, and hardware/software controls.
"""

import os
import time
from typing import Optional, Dict, Any
from PyQt6.QtCore import QObject, QTimer, QRect
from PyQt6.QtGui import QCursor
from monitorcontrol import get_monitors
import screeninfo

from logging_utils import log_message


class OverlayWindow:
    """Overlay window for software dimming."""
    
    def __init__(self, rect: QRect, color: str = "#000000"):
        from PyQt6.QtWidgets import QWidget
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPainter, QColor
        
        self.overlay_color = color
        self.widget = QWidget()
        self.init_window(rect)
    
    def init_window(self, rect: QRect) -> None:
        """Initialize the overlay window."""
        from PyQt6.QtCore import Qt
        
        flags = (Qt.WindowType.FramelessWindowHint |
                 Qt.WindowType.WindowStaysOnTopHint |
                 Qt.WindowType.Tool |
                 Qt.WindowType.BypassWindowManagerHint)
        self.widget.setWindowFlags(flags)
        self.widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.widget.setGeometry(rect)
        self.widget.setWindowOpacity(0.0)
    
    def paintEvent(self, event) -> None:
        """Paint the overlay."""
        from PyQt6.QtGui import QPainter, QColor
        
        painter = QPainter(self.widget)
        col = QColor(self.overlay_color)
        painter.setOpacity(self.widget.windowOpacity())
        painter.fillRect(self.widget.rect(), col)
    
    def set_opacity(self, opacity: float) -> None:
        """Set the overlay opacity."""
        self.widget.setWindowOpacity(opacity)
        self.widget.update()
    
    def set_overlay_color(self, color_str: str) -> None:
        """Set the overlay color."""
        self.overlay_color = color_str
        self.widget.update()
    
    def show(self) -> None:
        """Show the overlay."""
        self.widget.show()
    
    def hide(self) -> None:
        """Hide the overlay."""
        self.widget.hide()
    
    def setGeometry(self, rect: QRect) -> None:
        """Set the overlay geometry."""
        self.widget.setGeometry(rect)
        self.widget.update()
    
    def windowOpacity(self) -> float:
        """Get the current window opacity."""
        return self.widget.windowOpacity()


class MonitorController(QObject):
    """Controller for individual monitor dimming and activity detection."""
    
    def __init__(self, monitor_cfg: Dict[str, Any], global_cfg: Dict[str, Any], parent: Optional[QObject] = None):
        super().__init__(parent)
        self.cfg = monitor_cfg
        self.global_cfg = global_cfg
        self.is_dimmed = False
        self.restore_in_progress = False
        self.last_active = time.time()
        
        # Indices: original user index, plus separate display/DDC indices for mapping
        self.monitor_index = self.cfg["monitor_index"]
        self.display_index = self.cfg.get("display_index", self.monitor_index)
        self.ddc_index = self.cfg.get("ddc_index", self.monitor_index)
        self.monitorcontrol_monitor = None
        self.original_brightness = None
        
        # Monitor geometry
        self.left = 0
        self.top = 0
        self.width = 1
        self.height = 1
        
        self.overlay = None
        
        # Variables for QTimer-based hardware fade
        self.fade_timer = None
        self.current_fade_step = 0
        self.fade_steps = 0
        self.fade_start = 0
        self.fade_target = 0
        self.fade_step_size = 0
        
        self.init_monitor()
        self.check_timer = QTimer()
        self.check_timer.setInterval(2000)  # Reduced frequency from 1s to 2s for better performance
        self.check_timer.timeout.connect(self.check_inactivity)
        self.check_timer.start()
        
        # Cache for expensive operations
        self._last_cursor_check = 0
        self._last_window_check = 0
        self._cursor_cache_duration = 0.5  # Cache cursor position for 500ms
        self._window_cache_duration = 1.0   # Cache window check for 1s
    
    def init_monitor(self) -> None:
        """Initialize monitor hardware and software components."""
        # Initialize DDC/CI monitor based on ddc_index
        ddc_idx = self.ddc_index
        all_mc = get_monitors()
        if 0 <= ddc_idx < len(all_mc):
            self.monitorcontrol_monitor = all_mc[ddc_idx]
            try:
                with self.monitorcontrol_monitor:
                    self.original_brightness = self.monitorcontrol_monitor.get_luminance()
            except Exception as e:
                log_message(f"Failed to read brightness from DDC monitor {ddc_idx}: {e}")
                self.original_brightness = None
        else:
            self.monitorcontrol_monitor = None
        
        # Initialize geometry based on display_index
        self._update_geometry_from_system()
        rect = QRect(self.left, self.top, self.width, self.height)
        self.overlay = OverlayWindow(rect, color=self.cfg.get("overlay_color", "#000000"))
        self.overlay.hide()
        log_message(
            f"Initialized MonitorController for display {self.display_index} (ddc {ddc_idx}): pos=({self.left},{self.top}), "
            f"size=({self.width}x{self.height}), brightness={self.original_brightness}"
        )
    
    def _update_geometry_from_system(self) -> None:
        """Update monitor geometry from system."""
        idx = self.display_index
        monitors = screeninfo.get_monitors()
        if 0 <= idx < len(monitors):
            mon = monitors[idx]
            self.left, self.top = mon.x, mon.y
            self.width, self.height = mon.width, mon.height
        else:
            self.left, self.top, self.width, self.height = 0, 0, 800, 600
    
    def refresh_geometry(self) -> None:
        """Refresh monitor geometry and update overlay."""
        prev = (self.left, self.top, self.width, self.height)
        self._update_geometry_from_system()
        now = (self.left, self.top, self.width, self.height)
        if now != prev and self.overlay:
            rect = QRect(self.left, self.top, self.width, self.height)
            self.overlay.setGeometry(rect)
            self.overlay.update()
            log_message(
                f"Monitor {self.monitor_index} geometry updated: pos=({self.left},{self.top}), size=({self.width}x{self.height})",
                debug=True,
            )
    
    def is_monitor_active(self) -> bool:
        """Check if the monitor is currently active (cursor or fullscreen app)."""
        current_time = time.time()
        
        # Check cursor position with caching
        if current_time - self._last_cursor_check > self._cursor_cache_duration:
            cursor_pos = QCursor.pos()
            x, y = cursor_pos.x(), cursor_pos.y()
            if self.left <= x < (self.left + self.width) and self.top <= y < (self.top + self.height):
                return True
            self._last_cursor_check = current_time
        
        # Check if the foreground window substantially covers this monitor (fullscreen or borderless) - Windows only
        if os.name == 'nt' and current_time - self._last_window_check > self._window_cache_duration:
            try:
                import win32gui
                fg_hwnd = win32gui.GetForegroundWindow()
                if fg_hwnd and win32gui.IsWindowVisible(fg_hwnd):
                    win_left, win_top, win_right, win_bottom = win32gui.GetWindowRect(fg_hwnd)
                    # Compute overlap area ratio
                    mon_left, mon_top = self.left, self.top
                    mon_right, mon_bottom = self.left + self.width, self.top + self.height
                    inter_left = max(mon_left, win_left)
                    inter_top = max(mon_top, win_top)
                    inter_right = min(mon_right, win_right)
                    inter_bottom = min(mon_bottom, win_bottom)
                    inter_w = max(0, inter_right - inter_left)
                    inter_h = max(0, inter_bottom - inter_top)
                    inter_area = inter_w * inter_h
                    mon_area = max(1, self.width * self.height)
                    if inter_area / mon_area >= 0.95:
                        return True
                self._last_window_check = current_time
            except Exception:
                pass
        return False
    
    def check_inactivity(self) -> None:
        """Check for inactivity and dim/restore monitor as needed."""
        if self.global_cfg["awake_mode"]:
            if self.is_dimmed:
                self.restore_dim()
            return
        
        if self.is_monitor_active():
            self.last_active = time.time()
            if self.is_dimmed:
                self.restore_dim()
        else:
            idle_time = time.time() - self.last_active
            if idle_time >= self.global_cfg["inactivity_limit"] and not self.is_dimmed:
                self.dim()
    
    def dim(self) -> None:
        """Dim the monitor using hardware and/or software methods."""
        try:
            if self.is_dimmed:
                return
            self.is_dimmed = True
            # Software dimming
            if self.cfg.get("enable_software_dimming", True) and self.overlay:
                target_opacity = max(0.0, min(1.0, float(self.cfg.get("software_dimming_level", 0.5))))
                self.overlay.show()
                self.fade_overlay(target_opacity)
            # Hardware dimming
            if self.cfg.get("enable_hardware_dimming", True) and self.original_brightness is not None:
                self.fade_hardware(down=True)
        except Exception as e:
            log_message(f"Error during dim(): {e}")
    
    def restore_dim(self) -> None:
        """Restore monitor from dimmed state."""
        self.is_dimmed = False
        # For instant wake-up, use immediate restore instead of fade
        self.immediate_restore()
    
    def immediate_restore(self) -> None:
        """Immediately restore monitor brightness and hide overlay."""
        # Stop any active fade timer
        if self.fade_timer and self.fade_timer.isActive():
            self.fade_timer.stop()
        # Immediately set hardware brightness back to original
        if self.monitorcontrol_monitor and self.original_brightness is not None:
            self.set_brightness(self.original_brightness)
        # Immediately hide the overlay and reset opacity
        if self.overlay:
            self.overlay.hide()
            self.overlay.set_opacity(0.0)
        self.is_dimmed = False
    
    def set_brightness(self, value: int) -> None:
        """Set monitor brightness via DDC/CI."""
        if not self.monitorcontrol_monitor:
            return
        try:
            with self.monitorcontrol_monitor:
                self.monitorcontrol_monitor.set_luminance(value)
        except Exception as e:
            log_message(f"Error setting brightness on monitor {self.monitor_index}: {e}")
    
    def identify(self, duration_ms: int = 1000, opacity: float = 0.6) -> None:
        """Flash the overlay briefly to identify this monitor."""
        if not self.overlay:
            return
        try:
            self.overlay.show()
            self.fade_overlay(max(0.0, min(1.0, opacity)))
            QTimer.singleShot(duration_ms, lambda: self.fade_overlay(0.0))
        except Exception as e:
            log_message(f"Identify failed on monitor {self.monitor_index}: {e}")
    
    def fade_hardware(self, down: bool = True) -> None:
        """Fade hardware brightness smoothly."""
        if self.restore_in_progress:
            return
        self.restore_in_progress = True
        
        # Determine starting brightness by reading the current value when possible
        start = None
        if self.monitorcontrol_monitor:
            try:
                with self.monitorcontrol_monitor:
                    start = int(self.monitorcontrol_monitor.get_luminance())
            except Exception as e:
                log_message(f"[fade_hardware] Failed to read current brightness: {e}")
        if start is None:
            # Fallback to last known original or a sane default
            start = int(self.original_brightness) if self.original_brightness is not None else 100
        
        if down:
            level = max(0, min(100, int(self.cfg["hardware_dimming_level"])))
            target = max(0, min(100, int(round(start * (1 - level / 100.0)))))
        else:
            # Restore up to the original brightness if known, otherwise keep current
            target = int(self.original_brightness) if self.original_brightness is not None else start
        
        steps = self.global_cfg["overlay_fade_steps"]
        duration = self.global_cfg["overlay_fade_time"]
        # Make wake-up (restore) almost instant
        if not down:
            duration = max(0.01, duration * 0.05)  # 20x faster, almost instant
            steps = min(steps, 3)  # Use fewer steps for faster wake
        if steps <= 0:
            steps = 1
        self.fade_step_size = (target - start) / steps if steps else 0
        interval_ms = int((duration / steps) * 1000)
        self.current_fade_step = 0
        self.fade_steps = steps
        self.fade_start = start
        self.fade_target = target
        self.fade_timer = QTimer()
        self.fade_timer.setInterval(interval_ms)
        self.fade_timer.timeout.connect(self._do_fade)
        self.fade_timer.start()
    
    def _do_fade(self) -> None:
        """Execute one step of hardware brightness fade."""
        self.current_fade_step += 1
        new_value = self.fade_start + self.fade_step_size * self.current_fade_step
        if ((self.fade_step_size > 0 and new_value >= self.fade_target) or 
            (self.fade_step_size < 0 and new_value <= self.fade_target) or 
            self.current_fade_step >= self.fade_steps):
            new_value = self.fade_target
            self.set_brightness(int(new_value))
            self.fade_timer.stop()
            self.restore_in_progress = False
        else:
            self.set_brightness(int(new_value))
    
    def fade_overlay(self, target_opacity: float) -> None:
        """Fade overlay opacity smoothly."""
        current = self.overlay.windowOpacity()
        steps = self.global_cfg["overlay_fade_steps"]
        if steps <= 0:
            steps = 1
        total_time = self.global_cfg["overlay_fade_time"]
        # Speed up when restoring (fading out to 0) - almost instant wake animation
        if target_opacity < current:
            total_time = max(0.01, total_time * 0.05)  # 20x faster, almost instant
            steps = min(steps, 3)  # Use fewer steps for faster wake
        step_opacity = (target_opacity - current) / steps
        step_delay_ms = max(1, int((total_time / steps) * 1000))
        self._fade_overlay_step(current, target_opacity, step_opacity, step_delay_ms)
    
    def _fade_overlay_step(self, current: float, target: float, step_opacity: float, delay: int) -> None:
        """Execute one step of overlay fade."""
        next_val = current + step_opacity
        if (step_opacity > 0 and next_val >= target) or (step_opacity < 0 and next_val <= target):
            next_val = target
        self.overlay.set_opacity(next_val)
        if abs(next_val - target) > 0.01:
            QTimer.singleShot(delay, lambda: self._fade_overlay_step(next_val, target, step_opacity, delay))
        else:
            if abs(target) < 0.01:
                self.overlay.hide()
    
    def set_indices(self, display_index: int, ddc_index: int) -> None:
        """Update display and DDC indices and reinitialize."""
        # Update indices and re-init geometry and DDC monitor
        self.display_index = max(0, int(display_index))
        self.ddc_index = max(0, int(ddc_index))
        # Update DDC
        all_mc = get_monitors()
        self.monitorcontrol_monitor = None
        self.original_brightness = None
        if 0 <= self.ddc_index < len(all_mc):
            self.monitorcontrol_monitor = all_mc[self.ddc_index]
            try:
                with self.monitorcontrol_monitor:
                    self.original_brightness = self.monitorcontrol_monitor.get_luminance()
            except Exception as e:
                log_message(f"DDC probe failed on index {self.ddc_index}: {e}", debug=True)
        # Update geometry and overlay
        self.refresh_geometry()
    
    def disable_hw_dimming(self) -> None:
        """Disable hardware dimming and restore brightness."""
        if self.is_dimmed and self.original_brightness is not None:
            self.set_brightness(self.original_brightness)
        self.cfg["enable_hardware_dimming"] = False
    
    def disable_sw_dimming(self) -> None:
        """Disable software dimming and hide overlay."""
        if self.is_dimmed and self.overlay:
            self.overlay.hide()
            self.overlay.set_opacity(0.0)
        self.cfg["enable_software_dimming"] = False