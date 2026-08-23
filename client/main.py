#!/usr/bin/env python3
"""
Main entrypoint for the AI Desktop Assistant.

Orchestrates all components:
- Qt application and system tray
- API client for server communication
- Floating popup UI (search/compose, context display, snipping tool)
- Screenshot capture
- Context collection (screenshot + app info → API)
- Notification listener (inbound HTTP from n8n via Tailscale)
- Global hotkey manager
"""

import sys
import os
import signal

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

from client.core import (
    ApiClient,
    AsyncRunner,
    ContextCollector,
    HotkeyManager,
    NotificationListener,
    ScreenshotCapture,
    TrayApp,
)
from client.ui.popup import FloatingPopup
from client.config import ClientConfig


def main():
    # Single instance guard on Windows to prevent hotkey conflicts
    _mutex = None
    if sys.platform == "win32":
        import ctypes
        ERROR_ALREADY_EXISTS = 183
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\ShadowAssistantSingleInstanceMutex")
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            print("⚠️  Another instance of Shadow Assistant is already running.", flush=True)
            print("Please close the existing instance from the System Tray or Task Manager before starting a new one.", flush=True)
            sys.exit(0)

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

    # Input layer
    screenshot = ScreenshotCapture()
    context_collector = ContextCollector(
        screenshot=screenshot,
        api_client=api_client,
        async_runner=async_runner,
    )

    # UI components (with context collector attached for multimodal vision chat)
    popup = FloatingPopup(
        api_client=api_client,
        async_runner=async_runner,
        context_collector=context_collector,
    )

    # Notification listener (for inbound notifications from n8n via Tailscale)
    notification_listener = NotificationListener(
        host=config.tailscale_ip,
        port=config.notification_port,
        auth_token=config.n8n_auth_token,
    )

    # System tray app
    tray = TrayApp(popup, notification_listener, config)

    # Sync scripts and config path to popup
    popup.set_scripts(tray.get_current_scripts(), tray._scripts_config_path)
    tray.scripts_changed.connect(lambda s: popup.set_scripts(s, tray._scripts_config_path))
    popup.scripts_changed.connect(tray._on_scripts_updated_from_manager)

    # Connect tray signals to popup/actions
    tray.toggle_popup_requested.connect(popup.toggle_requested.emit)
    tray.quit_requested.connect(app.quit)

    # Handle screen capture requested from tray
    def _on_tray_capture_requested(mode: str):
        if mode == "snippet":
            popup._trigger_snipping()
        elif mode == "window":
            context_collector.capture_and_analyze(mode="window")
        else:
            context_collector.capture_and_analyze(mode="full")

    tray.capture_requested.connect(_on_tray_capture_requested)

    # Apply & react to screenshot settings updates
    def _apply_screenshot_settings(cfg: dict):
        if "quality" in cfg:
            screenshot.quality = int(cfg["quality"])
        if "max_dimension" in cfg:
            screenshot.max_dimension = int(cfg["max_dimension"])
        if "monitor_index" in cfg:
            screenshot.monitor_index = int(cfg["monitor_index"])
        if "recent_apps_limit" in cfg:
            context_collector.MAX_RECENT_APPS = int(cfg["recent_apps_limit"])

    _apply_screenshot_settings(tray.get_screenshot_settings())
    tray.screenshot_settings_changed.connect(_apply_screenshot_settings)

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
    def _on_analysis_started():
        popup.set_context_text("Analyzing screen context...")
        popup.show_at_cursor()
        tray.show_message("Context Analyzer", "Capturing and analyzing screen...", 2000)

    def _on_context_ready(response: dict):
        text = ApiClient.extract_response_text(response)
        popup.set_context_text(f"Context: {text}")
        truncated = text[:100] + ("..." if len(text) > 100 else "")
        tray.show_message("Context Analyzed", truncated, 5000)

    def _on_context_error(error_msg: str):
        popup.set_context_text(f"Context Error: {error_msg}")
        tray.show_message("Context Error", error_msg[:100], 5000)

    context_collector.analysis_started.connect(_on_analysis_started)
    context_collector.context_ready.connect(_on_context_ready)
    context_collector.context_error.connect(_on_context_error)

    # Hotkeys setup with initial mapping from tray (persisted config + scripts)
    def _build_hotkey_map(cfg: dict) -> dict:
        mapping = {}
        # 1. System hotkeys
        if "hotkey_popup" in cfg and cfg["hotkey_popup"]:
            mapping[cfg["hotkey_popup"]] = popup.toggle_requested.emit
        if "hotkey_scripts" in cfg and cfg["hotkey_scripts"]:
            mapping[cfg["hotkey_scripts"]] = popup.open_scripts_menu

        # 2. Script quick-launch hotkeys (e.g. Alt+1, Alt+2, Alt+3, Alt+4, etc.)
        current_scripts = tray.get_current_scripts()
        for idx, script in enumerate(current_scripts):
            hk = TrayApp.get_script_hotkey(script, idx)
            if hk and hk not in mapping:
                mapping[hk] = (lambda i=idx: lambda: tray._run_script(i))(idx)

        return mapping

    initial_hotkeys = _build_hotkey_map(tray.get_current_hotkeys())
    hotkeys = HotkeyManager(initial_hotkeys)

    def _refresh_all_hotkeys():
        new_map = _build_hotkey_map(tray.get_current_hotkeys())
        hotkeys.update_callbacks(new_map)

    tray.hotkeys_changed.connect(lambda cfg: _refresh_all_hotkeys())
    tray.scripts_changed.connect(lambda scripts: _refresh_all_hotkeys())

    def cleanup():
        """Clean shutdown of all components."""
        print("Shutting down...", flush=True)
        try:
            hotkeys.stop()
        except Exception as e:
            print(f"Error stopping hotkeys: {e}")

        try:
            notification_listener.stop()
        except Exception as e:
            print(f"Error stopping notification listener: {e}")

        try:
            # Close HTTP connection pools
            future = async_runner.run_coro(api_client.close())
            future.result(timeout=2.0)
        except Exception:
            pass

        try:
            async_runner.stop()
        except Exception as e:
            print(f"Error stopping async runner: {e}")

    # Connect cleanup to app quit
    app.aboutToQuit.connect(cleanup)

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