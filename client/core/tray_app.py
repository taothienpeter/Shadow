"""
System tray menu implementation for the AI Desktop Assistant.

Provides a full-featured context menu with:
- Server configuration (Tailscale IP, port, enable/disable)
- Script runner (preconfigured commands/exe)
- Hotkey display (show available hotkeys)
- Notification toggle (mute/unmute with queuing)
"""
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QSettings
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QFont, QBrush
from client.core.api_client import ApiClient
from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)


class TrayApp(QObject):
    """Manages the system tray icon and context menu."""

    # Signals
    toggle_popup_requested = pyqtSignal()
    server_toggled = pyqtSignal(bool)
    script_run_requested = pyqtSignal(int)  # script index
    notification_toggled = pyqtSignal(bool)  # enabled state
    quit_requested = pyqtSignal()

    def __init__(self, popup, notification_listener, config):
        super().__init__()
        self._popup = popup
        self._notification_listener = notification_listener
        self._config = config

        # State
        self._notifications_muted = False
        self._server_enabled = True
        self._notification_queue: List[Dict] = []
        self._scripts: List[Dict] = []

        # Paths
        app_data_dir = self._get_app_data_dir()
        self._scripts_config_path = app_data_dir / "scripts_config.json"
        self._notification_queue_path = app_data_dir / "notification_queue.json"

        # UI
        self._tray_icon = QSystemTrayIcon(self._create_icon())
        self._tray_icon.setToolTip("AI Desktop Assistant")
        self._tray_icon.setVisible(True)

        # Build menu
        self._build_menu()

        # Load persisted data
        self._load_scripts()
        self._load_notification_queue()
        self._update_pending_count()
        self._update_server_status()

        # Connect tray activation (left-click)
        self._tray_icon.activated.connect(self._on_tray_activated)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def show_message(self, title: str, message: str, msec: int = 3000):
        """Show a tray notification (respects mute state)."""
        try:
            if not self._notifications_muted:
                self._tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, msec)
            else:
                self._queue_notification({"title": title, "message": message})
        except Exception as e:
            # Fallback: print to console if we can't show a message
            print(f"Failed to show tray message: {e}")

    # --------------------------------------------------------------------- #
    # Private: Menu Building
    # --------------------------------------------------------------------- #
    def _build_menu(self):
        """Build the full context menu."""
        try:
            menu = QMenu()
            self._tray_icon.setContextMenu(menu)

            # Server Configuration Submenu
            server_menu = menu.addMenu("Server Configuration")
            self._build_server_menu(server_menu)

            # Scripts Submenu
            scripts_menu = menu.addMenu("Scripts")
            self._build_scripts_menu(scripts_menu)

            # Hotkeys Submenu
            hotkeys_menu = menu.addMenu("Hotkeys")
            self._build_hotkeys_menu(hotkeys_menu)

            # Notifications Submenu
            notifications_menu = menu.addMenu("Notifications")
            self._build_notifications_menu(notifications_menu)

            # Separator
            menu.addSeparator()

            # Show/Hide Popup
            show_hide_action = QAction("Show/Hide Popup", self)
            show_hide_action.triggered.connect(self._emit_toggle_popup)
            menu.addAction(show_hide_action)

            # Quit
            quit_action = QAction("Quit", self)
            quit_action.triggered.connect(self._emit_quit)
            menu.addAction(quit_action)
        except Exception as e:
            print(f"Error building tray menu: {e}")

    def _build_server_menu(self, menu: QMenu):
        """Build the server configuration submenu."""
        try:
            # Status indicators (non-interactive labels)
            status_label = menu.addAction("Status: Checking...")
            status_label.setEnabled(False)
            self._server_status_action = status_label

            ip_label = menu.addAction(f"Tailscale IP: {self._config.tailscale_ip}")
            ip_label.setEnabled(False)

            port_label = menu.addAction(f"Port: {self._config.notification_port}")
            port_label.setEnabled(False)

            menu.addSeparator()

            # Enable/Disable Server toggle
            toggle_text = "Disable Server" if self._server_enabled else "Enable Server"
            self._server_toggle_action = QAction(toggle_text, self)
            self._server_toggle_action.setCheckable(True)
            self._server_toggle_action.setChecked(self._server_enabled)
            self._server_toggle_action.triggered.connect(self._on_server_toggled)
            menu.addAction(self._server_toggle_action)

            # Test Connection
            test_action = QAction("Test Connection", self)
            test_action.triggered.connect(self._on_test_connection)
            menu.addAction(test_action)
        except Exception as e:
            print(f"Error building server menu: {e}")

    def _build_scripts_menu(self, menu: QMenu):
        """Build the scripts submenu (dynamic)."""
        try:
            self._scripts_menu = menu
            self._rebuild_scripts_menu()
        except Exception as e:
            print(f"Error building scripts menu: {e}")

    def _build_hotkeys_menu(self, menu: QMenu):
        """Build the hotkeys display submenu."""
        try:
            # Static hotkey display (from config/mapping)
            q_action = QAction("Alt+Q  →  Toggle Popup", self)
            q_action.setEnabled(False)
            menu.addAction(q_action)

            x_action = QAction("Alt+X  →  Voice Input Mode", self)
            x_action.setEnabled(False)
            menu.addAction(x_action)

            c_action = QAction("Alt+C  →  Run Script (Alt+C)", self)
            c_action.setEnabled(False)
            menu.addAction(c_action)

            menu.addSeparator()

            # Placeholder for future hotkey customization
            change_action = QAction("Change Hotkeys...", self)
            change_action.setEnabled(False)  # Not implemented yet
            menu.addAction(change_action)
        except Exception as e:
            print(f"Error building hotkeys menu: {e}")

    def _build_notifications_menu(self, menu: QMenu):
        """Build the notifications submenu."""
        try:
            self._notifications_toggle_action = QAction(
                "Notifications Active", self
            )
            self._notifications_toggle_action.setCheckable(True)
            self._notifications_toggle_action.setChecked(not self._notifications_muted)
            self._notifications_toggle_action.triggered.connect(
                self._on_notifications_toggled
            )
            menu.addAction(self._notifications_toggle_action)

            # Pending counter
            self._pending_action = menu.addAction("Pending: 0")
            self._pending_action.setEnabled(False)
        except Exception as e:
            print(f"Error building notifications menu: {e}")

    def _rebuild_scripts_menu(self):
        """Rebuild the scripts submenu from current script list."""
        try:
            if not hasattr(self, "_scripts_menu"):
                return

            self._scripts_menu.clear()

            if not self._scripts:
                no_scripts = self._scripts_menu.addAction("No scripts configured")
                no_scripts.setEnabled(False)
                self._scripts_menu.addSeparator()
            else:
                for idx, script in enumerate(self._scripts):
                    # Create submenu for each script
                    script_menu = self._scripts_menu.addMenu(script.get("name", f"Script {idx+1}"))

                    run_action = QAction("Run", self)
                    run_action.triggered.connect(lambda checked, i=idx: self._run_script(i))
                    script_menu.addAction(run_action)

                    # Edit action (placeholder)
                    edit_action = QAction("Edit", self)
                    edit_action.setEnabled(False)  # Not implemented yet
                    script_menu.addAction(edit_action)

                    # Delete action (placeholder)
                    delete_action = QAction("Delete", self)
                    delete_action.setEnabled(False)  # Not implemented yet
                    script_menu.addAction(delete_action)

            # Add separator and "Add New Script" at the end
            self._scripts_menu.addSeparator()
            add_action = self._scripts_menu.addAction("+ Add New Script...")
            add_action.triggered.connect(self._on_add_script)
        except Exception as e:
            print(f"Error rebuilding scripts menu: {e}")

    # --------------------------------------------------------------------- #
    # Private: Signal Handlers
    # --------------------------------------------------------------------- #
    def _emit_toggle_popup(self):
        try:
            self.toggle_popup_requested.emit()
        except Exception as e:
            print(f"Error emitting toggle popup: {e}")

    def _emit_quit(self):
        try:
            self.quit_requested.emit()
        except Exception as e:
            print(f"Error emitting quit: {e}")

    def _on_server_toggled(self, checked: bool):
        try:
            self._server_enabled = checked
            self._server_toggle_action.setText(
                "Disable Server" if checked else "Enable Server"
            )
            self.server_toggled.emit(checked)

            # Start/stop notification listener based on state
            if checked and not self._notification_listener.is_running():
                self._notification_listener.start()
            elif not checked and self._notification_listener.is_running():
                self._notification_listener.stop()

            self._update_server_status()
        except Exception as e:
            print(f"Error toggling server: {e}")
            self.show_message("Server Error", f"Failed to toggle server: {e}", 5000)

    def _on_test_connection(self):
        """Test connection by running the test_connection.py script in a new terminal."""
        try:
            # Resolve path to the root directory where test_connection.py is located
            root_dir = Path(__file__).parent.parent.parent
            script_path = root_dir / "test_connection.py"
            
            if script_path.exists():
                if sys.platform == "win32":
                    subprocess.Popen(f'start cmd /k "python {script_path}"', shell=True)
                else:
                    subprocess.Popen(["python", str(script_path)])
                self.show_message("Test Connection", "Running test script in a new terminal window...", 3000)
            else:
                QMessageBox.warning(None, "File Not Found", f"Cannot find test script at:\n{script_path}")
        except Exception as e:
            print(f"Error testing connection: {e}")
            self.show_message("Connection Test Error", f"Failed to start test: {e}", 5000)

    def _on_notifications_toggled(self, checked: bool):
        try:
            self._notifications_muted = not checked
            self._notifications_toggle_action.setText(
                "Notifications Active" if not self._notifications_muted else "Notifications Muted"
            )
            self.notification_toggled.emit(not self._notifications_muted)

            # If unmuting, replay the queue
            if not self._notifications_muted:
                self._replay_notification_queue()
            self._update_pending_count()
        except Exception as e:
            print(f"Error toggling notifications: {e}")
            self.show_message("Notifications Error", f"Failed to toggle notifications: {e}", 5000)

    def _on_add_script(self):
        """Handle adding a new script via dialog."""
        try:
            # Get script name
            name, ok = QInputDialog.getText(
                None, "Add New Script", "Enter a name for this script:"
            )
            if not ok or not name:
                return

            # Get script path/command
            path, _ = QInputDialog.getText(
                None,
                "Add New Script",
                "Enter command or path to executable (e.g., notepad.exe, cmd, /path/to/script):",
            )
            if not path:
                return

            # Optional working directory
            cwd, ok = QInputDialog.getText(
                None, "Add New Script", "Working directory (optional):", text=""
            )
            if not ok:
                cwd = ""

            # Add to scripts list
            new_script = {"name": name.strip(), "command": path.strip(), "cwd": cwd.strip()}
            self._scripts.append(new_script)
            self._save_scripts()
            self._rebuild_scripts_menu()
        except Exception as e:
            print(f"Error adding script: {e}")
            self.show_message("Add Script Error", f"Failed to add script: {e}", 5000)

    def _run_script(self, index: int):
        """Run a script by index."""
        try:
            if 0 <= index < len(self._scripts):
                script = self._scripts[index]
                self.script_run_requested.emit(index)
                try:
                    # Run the command
                    subprocess.Popen(
                        script["command"],
                        cwd=script["cwd"] if script["cwd"] else None,
                        shell=True,  # Allow shell commands like "dir", "ls"
                    )
                    # Show feedback
                    self.show_message(
                        "Script Running",
                        f"Running: {script['name']}",
                        msec=2000,
                    )
                except Exception as e:
                    self.show_message(
                        "Script Error",
                        f"Failed to run '{script['name']}': {str(e)}",
                        msec=5000,
                    )
            else:
                self.show_message("Script Error", f"Invalid script index: {index}", 3000)
        except Exception as e:
            print(f"Error running script: {e}")
            self.show_message("Script Error", f"Unexpected error running script: {e}", 5000)

    def _on_tray_activated(self, reason):
        """Handle tray icon activation (left-click)."""
        try:
            if reason == QSystemTrayIcon.ActivationReason.Trigger:
                # Left-click toggles popup
                self._emit_toggle_popup()
        except Exception as e:
            print(f"Error handling tray activation: {e}")

    # --------------------------------------------------------------------- #
    # Private: Notification Queue Management
    # --------------------------------------------------------------------- #
    def _queue_notification(self, payload: Dict):
        """Add a notification to the queue when muted."""
        try:
            self._notification_queue.append({
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
                "payload": payload,
            })
            self._save_queue()
            self._update_pending_count()
        except Exception as e:
            print(f"Error queuing notification: {e}")

    def _replay_notification_queue(self):
        """Show all queued notifications when unmuting."""
        try:
            for item in self._notification_queue:
                self._show_notification(item["payload"])
            self._notification_queue.clear()
            self._save_queue()
            self._update_pending_count()
        except Exception as e:
            print(f"Error replaying notification queue: {e}")

    def _show_notification(self, payload: Dict):
        """Show a notification from the queue."""
        try:
            title = payload.get("title", "Notification") if isinstance(payload, dict) and "title" in payload else "Notification"
            if isinstance(payload, dict):
                message = ApiClient.extract_response_text(payload)
            else:
                message = str(payload)
            self._tray_icon.showMessage(
                title, message, QSystemTrayIcon.MessageIcon.Information, 4000
            )
        except Exception as e:
            print(f"Error showing notification: {e}")

    def _update_pending_count(self):
        """Update the pending notifications counter."""
        try:
            count = len(self._notification_queue)
            self._pending_action.setText(f"Pending: {count}")
        except Exception as e:
            print(f"Error updating pending count: {e}")

    def is_notifications_muted(self) -> bool:
        """Return True if notifications are muted."""
        return self._notifications_muted

    def handle_notification(self, payload: Dict):
        """Handle an incoming notification: show if not muted, else queue."""
        try:
            if not self._notifications_muted:
                self._show_notification(payload)
            else:
                self._queue_notification(payload)
        except Exception as e:
            print(f"Error handling notification: {e}")
            self.show_message("Notification Error", f"Failed to handle notification: {e}", 5000)

    # --------------------------------------------------------------------- #
    # Private: Persistence (Scripts & Queue)
    # --------------------------------------------------------------------- #
    def _get_app_data_dir(self) -> Path:
        """Get the application data directory."""
        try:
            if getattr(sys, "frozen", False):
                # Running as compiled executable
                app_data = Path(os.getenv("APPDATA", "")) / "AI Desktop Assistant"
            else:
                # Running from source
                app_data = Path(__file__).parent.parent / "data"
            app_data.mkdir(parents=True, exist_ok=True)
            return app_data
        except Exception as e:
            print(f"Error getting app data dir: {e}")
            # Fallback to current directory
            return Path(".")

    def _load_scripts(self):
        """Load scripts from JSON file."""
        try:
            if self._scripts_config_path.exists():
                with open(self._scripts_config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._scripts = data.get("scripts", [])
            else:
                # Create default scripts if file doesn't exist
                self._scripts = [
                    {"name": "Task Manager", "command": "taskmgr.exe", "cwd": ""},
                    {"name": "Command Prompt", "command": "cmd.exe", "cwd": ""},
                ]
                self._save_scripts()
        except Exception as e:
            print(f"Error loading scripts: {e}")
            self._scripts = []

    def _save_scripts(self):
        """Save scripts to JSON file."""
        try:
            with open(self._scripts_config_path, "w", encoding="utf-8") as f:
                json.dump({"scripts": self._scripts}, f, indent=2)
        except Exception as e:
            print(f"Error saving scripts: {e}")

    def _load_notification_queue(self):
        """Load notification queue from JSON file."""
        try:
            if self._notification_queue_path.exists():
                with open(self._notification_queue_path, "r", encoding="utf-8") as f:
                    self._notification_queue = json.load(f)
            else:
                self._notification_queue = []
        except Exception as e:
            print(f"Error loading notification queue: {e}")
            self._notification_queue = []

    def _save_queue(self):
        """Save notification queue to JSON file."""
        try:
            with open(self._notification_queue_path, "w", encoding="utf-8") as f:
                json.dump(self._notification_queue, f, indent=2)
        except Exception as e:
            print(f"Error saving notification queue: {e}")

    # --------------------------------------------------------------------- #
    # Private: Helpers
    # --------------------------------------------------------------------- #
    def _create_icon(self) -> QIcon:
        """Create or load the tray icon with robust fallback."""
        try:
            # Check potential asset locations
            possible_paths = [
                Path(__file__).parent.parent / "assets" / "icon.png",
                Path(__file__).parent.parent.parent / "client" / "assets" / "icon.png",
                Path(__file__).parent.parent / "client" / "assets" / "icon.png",
            ]
            for p in possible_paths:
                if p.exists():
                    return QIcon(str(p))

            # Programmatic crisp fallback icon: dark indigo circle with white 'S'
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor(0, 0, 0, 0))  # Transparent
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(QColor(0, 122, 255)))  # Apple Blue
            painter.setPen(QColor(255, 255, 255, 40))
            painter.drawRoundedRect(4, 4, 56, 56, 16, 16)
            font = QFont("Segoe UI", 28, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(pixmap.rect(), 0x0084, "S")  # Qt.AlignmentFlag.AlignCenter
            painter.end()
            return QIcon(pixmap)
        except Exception as e:
            print(f"Error creating icon: {e}")
            return QIcon()

    def _update_server_status(self):
        """Update the server status label."""
        try:
            # In a real implementation, this would check actual connection status
            status_text = (
                "Status: Connected" if self._server_enabled else "Status: Disabled"
            )
            self._server_status_action.setText(status_text)
        except Exception as e:
            print(f"Error updating server status: {e}")