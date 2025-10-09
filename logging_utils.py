"""Logging utilities for MonitorNap application.

This module provides logging functionality that can be imported by all other modules
without creating circular dependencies.
"""

from collections import deque
from datetime import datetime

# Logging cache and debug mode
LOG_CACHE = deque(maxlen=10000)
DEBUG_MODE = False

def log_message(msg: str, debug: bool = False) -> None:
    """Log a message with timestamp to both console and cache.
    
    Args:
        msg: The message to log
        debug: If True, only log when DEBUG_MODE is enabled
    """
    if debug and not DEBUG_MODE:
        return
    t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = "[DEBUG]" if debug else "[INFO]"
    line = f"{prefix} {t} - {msg}"
    LOG_CACHE.append(line)
    print(line)

def set_debug_mode(enabled: bool) -> None:
    """Set the global debug mode flag.
    
    Args:
        enabled: Whether to enable debug mode
    """
    global DEBUG_MODE
    DEBUG_MODE = enabled
