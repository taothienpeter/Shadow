# tray_app.py Specification

**Path**: `client/core/tray_app.py`

## Description
System Tray Application component for Shadow Assistant.
Provides tray icon, background notifications, and comprehensive settings submenus.

## Classes

### `TrayApp(QObject)`

#### Signals
- `toggle_popup_requested = pyqtSignal()`
- `quit_requested = pyqtSignal()`
- `server_toggled = pyqtSignal(bool)`
- `scripts_changed = pyqtSignal(list)`
- `hotkeys_changed = pyqtSignal(dict)`
- `notification_action_triggered = pyqtSignal(str, dict)`

#### Menu Structure
1. **Server Configuration**:
   - Status indicators (Checking / Running / Stopped)
   - Tailscale IP & Port display
   - Enable / Disable Server toggle
   - **Test Connection** (launches `tools/test_connection.py` in terminal)
2. **Scripts Submenu**:
   - Dynamic list of configured scripts with hotkeys (`Alt+1..N`)
   - "Manage Scripts..." dialog
3. **Screen Capture Submenu**:
   - Quick "Capture Screen" test
   - "Screenshot Settings..." dialog (Quality, Engine, Multi-mon)
4. **Hotkeys Submenu**:
   - Read-only quick reference (`Alt+Q`, `Alt+A`, `Alt+1..N`)
   - "Configure Hotkeys..." dialog
5. **Notifications Submenu**:
   - Mute / Unmute toggle
   - "View Notification Log..." dialog
   - "Clear History"
6. **Start with Windows**:
   - Checkable action toggling `client.core.autostart.set_autostart()` in Windows Registry.
7. **Show/Hide Popup**, **Restart**, and **Quit**.
