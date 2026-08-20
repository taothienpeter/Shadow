#!/usr/bin/env python3
"""
Main entrypoint for the AI Desktop Assistant.

Orchestrates all components:
- Qt application and system tray
- API client for server communication
- Floating popup UI (search/compose, context display, voice mode)
- Screenshot capture
- Context collection (screenshot + app info → API)
- Notification listener (inbound HTTP from n8n via Tailscale)
- Global hotkey manager
"""

import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add the parent directory of the script to sys.path so that the client package can be found
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from client.core.async_runner import AsyncRunner
from client.core.hotkey import HotkeyManager
from client.core.api_client import ApiClient
from client.core.screenshot import ScreenshotCapture
from client.core.context_collector import ContextCollector
from client.core.notification_listener import NotificationListener
from client.core.tray_app import TrayApp
from client.ui.popup import FloatingPopup
from client.config import ClientConfig


def main():
    print("Starting AI Desktop Assistant...", flush=True)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    config = ClientConfig()

    # Shared async runner for all async operations
    async_runner = AsyncRunner()
    async_runner.start()

    # Infrastructure
    api_client = ApiClient(
        webhook_url=config.n8n_webhook_url,
        api_key=config.n8n_api_key,
    )

    # UI components
    popup = FloatingPopup(api_client=api_client, async_runner=async_runner)

    # Notification listener (for inbound notifications from n8n via Tailscale)
    notification_listener = NotificationListener(
        host=config.tailscale_ip,
        port=config.notification_port,
        auth_token=config.n8n_auth_token,
    )

    # System tray app (replaces inline QSystemTrayIcon setup)
    tray = TrayApp(popup, notification_listener, config)

    # Connect tray signals to popup/actions
    tray.toggle_popup_requested.connect(popup.toggle_requested.emit)
    tray.quit_requested.connect(app.quit)
    # For backward compatibility with existing popup signals
    # (TrayApp doesn't emit popup_show_requested yet, we'll use toggle for now)

    # Input layer
    screenshot = ScreenshotCapture()
    context_collector = ContextCollector(
        screenshot=screenshot,
        api_client=api_client,
        async_runner=async_runner,
    )

    # Show inbound notifications in popup context area and as system tray notification
    def _on_inbound_notification(data):
        display_text = ApiClient.extract_response_text(data)
        popup.set_context_text(f"Notification: {display_text}")
        tray.handle_notification(data)

    notification_listener.notification_received.connect(_on_inbound_notification)
    notification_listener.start()

    # Outbound ask-respond responses: show as system tray notification
    def _show_response_tray(response: dict):
        text = ApiClient.extract_response_text(response)
        truncated = text[:100] + ("..." if len(text) > 100 else "")
        tray.show_message(
            "AI Response",
            truncated,
            5000,
        )

    popup.response_received.connect(_show_response_tray)

    # Context collector response / error feedback
    def _on_context_ready(response: dict):
        text = ApiClient.extract_response_text(response)
        popup.set_context_text(f"Context: {text}")
        truncated = text[:100] + ("..." if len(text) > 100 else "")
        tray.show_message("Context Analyzed", truncated, 5000)

    def _on_context_error(error_msg: str):
        popup.set_context_text(f"Context Error: {error_msg}")
        tray.show_message("Context Error", error_msg[:100], 5000)

    context_collector.context_ready.connect(_on_context_ready)
    context_collector.context_error.connect(_on_context_error)

    # Hotkeys
    hotkeys = HotkeyManager({
        "<alt>+q": popup.toggle_requested.emit,
        "<alt>+x": popup.voice_mode_requested.emit,
        "<alt>+c": context_collector.capture_and_analyze,
    })

    def cleanup():
        """Clean shutdown of all components."""
        print("Shutting down...")
        hotkeys.stop()
        notification_listener.stop()
        async_runner.stop()
        # ApiClient cleanup is handled by its __aexit__ or explicit close if needed
        # For now, rely on the async_runner stopping which will cancel pending tasks

    # Connect cleanup to app quit
    app.aboutToQuit.connect(cleanup)

    import signal
    # Allow Python to catch Ctrl+C and gracefully quit
    signal.signal(signal.SIGINT, lambda sig, frame: app.quit())
    
    # A dummy timer lets the Python interpreter run periodically to process OS signals
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    # Start
    hotkeys.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()