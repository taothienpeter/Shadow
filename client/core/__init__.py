"""
Core modules for AI Desktop Assistant (Shadow).
"""

from client.core.api_client import ApiClient
from client.core.async_runner import AsyncRunner
from client.core.context_collector import ContextCollector
from client.core.hotkey import HotkeyManager
from client.core.notification_listener import NotificationListener
from client.core.screenshot import ScreenshotCapture
from client.core.script_runner import run_script
from client.core.autostart import is_autostart_enabled, set_autostart
from client.core.tray_app import TrayApp

__all__ = [
    "ApiClient",
    "AsyncRunner",
    "ContextCollector",
    "HotkeyManager",
    "NotificationListener",
    "ScreenshotCapture",
    "run_script",
    "TrayApp",
    "is_autostart_enabled",
    "set_autostart",
]
