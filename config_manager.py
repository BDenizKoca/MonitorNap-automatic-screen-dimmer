"""Configuration management for MonitorNap application."""

import os
import json
from typing import Dict, Any

from logging_utils import log_message


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
