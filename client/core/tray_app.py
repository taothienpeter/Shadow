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

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QSettings, Qt
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QFont, QBrush
from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from client.core.api_client import ApiClient
from client.core.script_runner import run_script


class TrayApp(QObject):
    """Manages the system tray icon and context menu."""

    # Signals
    toggle_popup_requested = pyqtSignal()
    server_toggled = pyqtSignal(bool)
    script_run_requested = pyqtSignal(int)  # script index
    scripts_changed = pyqtSignal(list)  # list of scripts updated
    notification_toggled = pyqtSignal(bool)  # enabled state
    hotkeys_changed = pyqtSignal(dict)  # new hotkeys config mapping
    capture_requested = pyqtSignal(str)  # "full" | "window" | "snippet"
    screenshot_settings_changed = pyqtSignal(dict)  # updated screenshot parameters
    quit_requested = pyqtSignal()

    def __init__(self, app, config_loader, config):
        super().__init__()
        self._app = app
        self._config_loader = config_loader
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
        self._hotkeys_config_path = app_data_dir / "hotkeys_config.json"
        self._screenshot_config_path = app_data_dir / "screenshot_config.json"
        self._hotkeys = self._load_hotkeys()
        self._screenshot_settings = self._load_screenshot_settings()
        # Load persisted data first
        self._load_scripts()
        self._load_notification_queue()

        # UI
        self._tray_icon = QSystemTrayIcon(self._create_icon())
        self._tray_icon.setToolTip("AI Desktop Assistant")
        self._tray_icon.setVisible(True)

        # Build menu
        self._build_menu()

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

            # Screen Capture Submenu
            capture_menu = menu.addMenu("Screen Capture")
            self._build_capture_menu(capture_menu)

            # Hotkeys Submenu
            hotkeys_menu = menu.addMenu("Hotkeys")
            self._build_hotkeys_menu(hotkeys_menu)

            # Notifications Submenu
            notifications_menu = menu.addMenu("Notifications")
            self._build_notifications_menu(notifications_menu)

            # Separator
            menu.addSeparator()

            # Start with Windows (Autostart Toggle)
            from client.core.autostart import is_autostart_enabled
            self._autostart_action = QAction("Start with Windows", self)
            self._autostart_action.setCheckable(True)
            self._autostart_action.setChecked(is_autostart_enabled())
            self._autostart_action.triggered.connect(self._on_autostart_toggled)
            menu.addAction(self._autostart_action)

            # Show/Hide Popup
            show_hide_action = QAction("Show/Hide Popup", self)
            show_hide_action.triggered.connect(self._emit_toggle_popup)
            menu.addAction(show_hide_action)

            # Restart
            restart_action = QAction("Restart", self)
            restart_action.triggered.connect(self._restart_app)
            menu.addAction(restart_action)

            # Quit
            quit_action = QAction("Quit", self)
            quit_action.triggered.connect(self._emit_quit)
            menu.addAction(quit_action)
        except Exception as e:
            print(f"Error building tray menu: {e}")

    def _on_autostart_toggled(self, checked: bool):
        """Toggle Windows startup registry entry."""
        from client.core.autostart import set_autostart
        success = set_autostart(checked)
        if success:
            state_str = "enabled" if checked else "disabled"
            self.show_message("Startup Settings", f"Auto-start with Windows {state_str}.", 3000)
        else:
            self._autostart_action.setChecked(not checked)
            self.show_message("Startup Settings", "Failed to update startup configuration.", 4000)

    def _restart_app(self):
        """Restart the assistant application."""
        import sys
        from PyQt6.QtCore import QProcess
        from PyQt6.QtWidgets import QApplication
        QProcess.startDetached(sys.executable, sys.argv)
        QApplication.quit()

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

    def _load_hotkeys(self) -> Dict[str, str]:
        """Load hotkeys mapping from json or config defaults."""
        default = {
            "hotkey_popup": getattr(self._config, "hotkey_popup", "<alt>+q"),
            "hotkey_scripts": getattr(self._config, "hotkey_scripts", "<alt>+a"),
        }
        try:
            if self._hotkeys_config_path.exists():
                with open(self._hotkeys_config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default.update(data)
        except Exception as e:
            print(f"Error loading hotkeys config: {e}")
        return default

    def get_current_hotkeys(self) -> Dict[str, str]:
        """Return the current active hotkeys mapping."""
        return dict(self._hotkeys)

    @staticmethod
    def get_script_hotkey(script: dict, index: int = 0) -> str:
        """Return explicit hotkey for script if configured, else empty string."""
        return script.get("hotkey", "").strip().lower()

    def _build_hotkeys_menu(self, menu: QMenu):
        """Build the hotkeys display submenu."""
        try:
            self._hotkeys_menu = menu
            self._rebuild_hotkeys_menu()
        except Exception as e:
            print(f"Error building hotkeys menu: {e}")

    def _rebuild_hotkeys_menu(self):
        """Rebuild hotkey menu items reflecting active configuration."""
        if not hasattr(self, "_hotkeys_menu"):
            return
        try:
            self._hotkeys_menu.clear()

            def format_key(k: str) -> str:
                return " + ".join([p.strip("<>").upper() for p in k.split("+") if p.strip()])

            p_str = format_key(self._hotkeys.get("hotkey_popup", "<alt>+q"))
            s_str = format_key(self._hotkeys.get("hotkey_scripts", "<alt>+a"))

            q_action = QAction(f"{p_str}  →  Toggle Popup", self)
            q_action.setEnabled(False)
            self._hotkeys_menu.addAction(q_action)

            s_action = QAction(f"{s_str}  →  Scripts Menu", self)
            s_action.setEnabled(False)
            self._hotkeys_menu.addAction(s_action)

            # Display active script shortcuts ONLY if explicitly assigned
            active_script_hotkeys = [
                (script, self.get_script_hotkey(script, idx))
                for idx, script in enumerate(self._scripts)
                if self.get_script_hotkey(script, idx)
            ]

            if active_script_hotkeys:
                self._hotkeys_menu.addSeparator()
                s_header = QAction("Script Shortcuts", self)
                s_header.setEnabled(False)
                self._hotkeys_menu.addAction(s_header)

                for script, hk in active_script_hotkeys:
                    s_key = format_key(hk)
                    s_name = script.get("name", "Script")
                    s_action = QAction(f"{s_key}  →  Run: {s_name}", self)
                    s_action.setEnabled(False)
                    self._hotkeys_menu.addAction(s_action)

            self._hotkeys_menu.addSeparator()

            change_action = QAction("Change Hotkeys...", self)
            change_action.triggered.connect(self._on_change_hotkeys)
            self._hotkeys_menu.addAction(change_action)
        except Exception as e:
            print(f"Error rebuilding hotkeys menu: {e}")

    def _on_change_hotkeys(self):
        """Open hotkeys configuration dialog."""
        try:
            from client.ui.hotkey_dialog import HotkeySettingsDialog
            dialog = HotkeySettingsDialog(self._hotkeys_config_path, self._hotkeys)
            dialog.hotkeys_updated.connect(self._on_hotkeys_updated)
            dialog.exec()
        except Exception as e:
            print(f"Error opening hotkey dialog: {e}")
            self.show_message("Hotkey Error", f"Failed to open settings: {e}", 4000)

    def _on_hotkeys_updated(self, new_hotkeys: dict):
        """Handle updated hotkeys from dialog."""
        self._hotkeys = new_hotkeys
        self._rebuild_hotkeys_menu()
        self.hotkeys_changed.emit(new_hotkeys)
        self.show_message("Hotkeys Updated", "New shortcuts applied immediately!", 3000)

    def _load_screenshot_settings(self) -> dict:
        """Load screen capture settings from JSON file or default."""
        defaults = {
            "quality": 70,
            "max_dimension": 1920,
            "monitor_index": 0,
            "recent_apps_limit": 4,
        }
        try:
            if self._screenshot_config_path.exists():
                with open(self._screenshot_config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    defaults.update(data)
        except Exception as e:
            print(f"Error loading screenshot settings: {e}")
        return defaults

    def get_screenshot_settings(self) -> dict:
        """Return current screenshot settings."""
        return dict(self._screenshot_settings)

    def _save_screenshot_settings(self, new_settings: dict):
        """Save settings, emit signal, and notify user."""
        self._screenshot_settings.update(new_settings)
        try:
            self._screenshot_config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._screenshot_config_path, "w", encoding="utf-8") as f:
                json.dump(self._screenshot_settings, f, indent=2)
        except Exception as e:
            print(f"Error saving screenshot settings: {e}")

        self.screenshot_settings_changed.emit(self._screenshot_settings)
        self._rebuild_capture_menu()

    def _rebuild_capture_menu(self):
        """Rebuild the screen capture menu to update checkmarks."""
        if hasattr(self, "_capture_menu") and self._capture_menu:
            self._capture_menu.clear()
            self._build_capture_menu(self._capture_menu)

    def _build_capture_menu(self, menu: QMenu):
        """Build the screen capture submenu with quick triggers and live parameter controls."""
        try:
            self._capture_menu = menu

            # 1. Quick Capture Triggers
            full_action = QAction("Capture Full Screen", self)
            full_action.triggered.connect(lambda: self.capture_requested.emit("full"))
            menu.addAction(full_action)

            window_action = QAction("Capture Active Window", self)
            window_action.triggered.connect(lambda: self.capture_requested.emit("window"))
            menu.addAction(window_action)

            snip_action = QAction("Interactive Area Snipping", self)
            snip_action.triggered.connect(lambda: self.capture_requested.emit("snippet"))
            menu.addAction(snip_action)

            menu.addSeparator()

            # 2. Quality Presets
            quality_menu = menu.addMenu("Quality Preset")
            current_q = int(self._screenshot_settings.get("quality", 70))
            q_options = [
                ("High Quality (90%)", 90),
                ("Balanced (70%)", 70),
                ("Performance (50%)", 50),
            ]
            for label, q_val in q_options:
                action = QAction(label, self)
                action.setCheckable(True)
                action.setChecked(current_q == q_val)
                action.triggered.connect(lambda checked, q=q_val: self._save_screenshot_settings({"quality": q}))
                quality_menu.addAction(action)

            # 3. Max Resolution Presets
            res_menu = menu.addMenu("Max Resolution")
            current_dim = int(self._screenshot_settings.get("max_dimension", 1920))
            res_options = [
                ("1080p Full HD (1920px)", 1920),
                ("2K QHD (2560px)", 2560),
                ("4K UHD (3840px)", 3840),
                ("720p HD (1280px)", 1280),
                ("Original (No Resize)", 0),
            ]
            for label, dim_val in res_options:
                action = QAction(label, self)
                action.setCheckable(True)
                action.setChecked(current_dim == dim_val)
                action.triggered.connect(lambda checked, d=dim_val: self._save_screenshot_settings({"max_dimension": d}))
                res_menu.addAction(action)

            # 4. Display Monitor
            mon_menu = menu.addMenu("Capture Monitor")
            current_mon = int(self._screenshot_settings.get("monitor_index", 0))
            all_mon_action = QAction("All Monitors", self)
            all_mon_action.setCheckable(True)
            all_mon_action.setChecked(current_mon == 0)
            all_mon_action.triggered.connect(lambda checked: self._save_screenshot_settings({"monitor_index": 0}))
            mon_menu.addAction(all_mon_action)

            primary_mon_action = QAction("Primary Monitor Only", self)
            primary_mon_action.setCheckable(True)
            primary_mon_action.setChecked(current_mon == 1)
            primary_mon_action.triggered.connect(lambda checked: self._save_screenshot_settings({"monitor_index": 1}))
            mon_menu.addAction(primary_mon_action)

            menu.addSeparator()

            # 5. Advanced Settings Dialog
            config_action = QAction("⚙  Configure Screen Capture...", self)
            config_action.triggered.connect(self._on_open_screenshot_settings)
            menu.addAction(config_action)

        except Exception as e:
            print(f"Error building capture menu: {e}")

    def _on_open_screenshot_settings(self):
        """Open the Screenshot Settings modal dialog."""
        try:
            from client.ui.screenshot_dialog import ScreenshotSettingsDialog
            dlg = ScreenshotSettingsDialog(
                config_path=self._screenshot_config_path,
                current_settings=self._screenshot_settings,
                parent=None,
            )
            dlg.settings_updated.connect(self._on_screenshot_settings_dialog_updated)
            dlg.exec()
        except Exception as e:
            print(f"Error opening screenshot settings dialog: {e}")

    def _on_screenshot_settings_dialog_updated(self, new_settings: dict):
        """Callback when user saves settings in the dialog."""
        self._screenshot_settings = new_settings
        self.screenshot_settings_changed.emit(new_settings)
        self._rebuild_capture_menu()
        self.show_message("Settings Saved", "Screen capture settings applied successfully!", 3000)



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

    def get_current_scripts(self) -> List[Dict]:
        """Return a copy of the current configured scripts list."""
        return list(self._scripts)

    def _rebuild_scripts_menu(self):
        """Rebuild the scripts submenu from current script list."""
        try:
            if not hasattr(self, "_scripts_menu"):
                return

            self._scripts_menu.clear()

            if not self._scripts:
                no_scripts = self._scripts_menu.addAction("No scripts configured")
                no_scripts.setEnabled(False)
            else:
                for idx, script in enumerate(self._scripts):
                    script_name = script.get("name", f"Script {idx+1}")
                    hk = self.get_script_hotkey(script, idx)
                    if hk:
                        hk_fmt = " + ".join([p.strip("<>").upper() for p in hk.split("+") if p.strip()])
                        menu_title = f"{idx+1}. {script_name}  [{hk_fmt}]"
                    else:
                        menu_title = f"{idx+1}. {script_name}"

                    script_menu = self._scripts_menu.addMenu(menu_title)

                    run_action = QAction("▶ Run", self)
                    run_action.triggered.connect(lambda checked, i=idx: self._run_script(i))
                    script_menu.addAction(run_action)

                    edit_action = QAction("Edit...", self)
                    edit_action.triggered.connect(lambda checked, i=idx: self._on_edit_script(i))
                    script_menu.addAction(edit_action)

                    delete_action = QAction("Delete", self)
                    delete_action.triggered.connect(lambda checked, i=idx: self._on_delete_script(i))
                    script_menu.addAction(delete_action)

            # Bottom options
            self._scripts_menu.addSeparator()
            add_action = self._scripts_menu.addAction("+ Add New Script...")
            add_action.triggered.connect(self._on_add_script)

            manage_action = self._scripts_menu.addAction("Manage Scripts...")
            manage_action.triggered.connect(self._on_manage_scripts)
        except Exception as e:
            print(f"Error rebuilding scripts menu: {e}")

    def _on_add_script(self):
        """Open dialog to add a new script."""
        try:
            from client.ui.script_dialog import ScriptEditDialog
            dlg = ScriptEditDialog(parent=None)
            if dlg.exec() == 1:
                new_data = dlg.get_data()
                self._scripts.append(new_data)
                self._save_scripts()
                self._rebuild_scripts_menu()
                self.scripts_changed.emit(self._scripts)
                self.show_message("Script Added", f"Added '{new_data['name']}'", 2000)
        except Exception as e:
            print(f"Error adding script: {e}")
            self.show_message("Script Error", f"Failed to add script: {e}", 4000)

    def _on_edit_script(self, index: int):
        """Open dialog to edit an existing script."""
        try:
            if 0 <= index < len(self._scripts):
                from client.ui.script_dialog import ScriptEditDialog
                dlg = ScriptEditDialog(script=self._scripts[index], parent=None)
                if dlg.exec() == 1:
                    updated_data = dlg.get_data()
                    self._scripts[index] = updated_data
                    self._save_scripts()
                    self._rebuild_scripts_menu()
                    self.scripts_changed.emit(self._scripts)
                    self.show_message("Script Updated", f"Updated '{updated_data['name']}'", 2000)
        except Exception as e:
            print(f"Error editing script: {e}")

    def _on_delete_script(self, index: int):
        """Delete a script by index."""
        try:
            if 0 <= index < len(self._scripts):
                name = self._scripts[index].get("name", "this script")
                reply = QMessageBox.question(
                    None,
                    "Delete Script",
                    f"Are you sure you want to delete '{name}'?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._scripts.pop(index)
                    self._save_scripts()
                    self._rebuild_scripts_menu()
                    self.scripts_changed.emit(self._scripts)
                    self.show_message("Script Deleted", f"Deleted '{name}'", 2000)
        except Exception as e:
            print(f"Error deleting script: {e}")

    def _on_manage_scripts(self):
        """Open full Script Manager dialog."""
        try:
            from client.ui.script_dialog import ScriptManagerDialog
            dlg = ScriptManagerDialog(self._scripts_config_path, self._scripts, parent=None)
            dlg.scripts_updated.connect(self._on_scripts_updated_from_manager)
            dlg.exec()
        except Exception as e:
            print(f"Error opening script manager: {e}")

    def _on_scripts_updated_from_manager(self, new_scripts: list):
        self._scripts = new_scripts
        self._rebuild_scripts_menu()
        self.scripts_changed.emit(self._scripts)

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
            # Resolve path to test_connection.py in tools/ or root
            root_dir = Path(__file__).resolve().parents[2]
            script_path = root_dir / "tools" / "test_connection.py"
            if not script_path.exists():
                script_path = root_dir / "test_connection.py"
            
            if script_path.exists():
                if sys.platform == "win32":
                    subprocess.Popen(f'start cmd /k "\"{sys.executable}\" \"{script_path}\""', shell=True)
                else:
                    subprocess.Popen([sys.executable, str(script_path)])
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

    def _run_script(self, index: int):
        """Run a script by index."""
        try:
            if 0 <= index < len(self._scripts):
                script = self._scripts[index]
                self.script_run_requested.emit(index)
                success, msg = run_script(script)
                if success:
                    self.show_message(
                        "Script Running",
                        f"Running: {script.get('name', 'Script')}",
                        msec=2000,
                    )
                else:
                    self.show_message(
                        "Script Error",
                        msg,
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
        """Show queued notifications when unmuting with overflow summary."""
        try:
            total = len(self._notification_queue)
            if total == 0:
                return

            # Show at most 3 notifications to avoid spamming the user
            items_to_show = self._notification_queue[:3]
            for item in items_to_show:
                self._show_notification(item["payload"])

            if total > 3:
                remaining = total - 3
                self.show_message(
                    "Missed Notifications",
                    f"...plus {remaining} more notification{'s' if remaining != 1 else ''} received while muted.",
                    4000
                )

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
            painter.drawText(pixmap.rect(), int(Qt.AlignmentFlag.AlignCenter), "S")
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