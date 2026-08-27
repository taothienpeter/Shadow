# hotkey.py Specification

**Path**: `client/core/hotkey.py`

## Description
High-performance native Windows Win32 Hotkey Manager for Shadow Assistant (with cross-platform `pynput` fallback).
Utilizes `user32.dll` (`RegisterHotKey`, `UnregisterHotKey`, `GetMessageW`, `PeekMessageW`) on an isolated background message loop thread to register global key combinations with 0% idle CPU usage.

## Classes & Functions

### `Win32HotkeyManager`
Native Windows global hotkey listener.

#### Properties
- `_callbacks: dict[str, Callable]`
- `_registered_ids: dict[int, tuple[str, Callable]]`
- `_thread: threading.Thread | None`
- `_thread_id: int | None`
- `_running: bool`
- `_was_running_before_pause: bool`
- `_started_evt: threading.Event`

#### Key Default Mappings
- `<alt>+q`: Show/Hide Floating Popup (`popup.toggle_requested.emit`)
- `<alt>+a`: Open Scripts Menu (`popup.open_scripts_menu_requested.emit`)
- `<alt>+1..N`: Quick launch configured custom scripts (`tray._run_script(i)`)

#### Methods
- `__init__(callbacks: dict[str, Callable])`
- `parse_hotkey_string(hotkey_str: str) -> tuple[int, int]`: Parses strings like `"<alt>+q"`, `"ctrl+shift+a"`, or `"alt+space"` into Win32 MOD flags and Virtual Key codes via `VK_MAPPING` and ASCII/F-keys/Numpad.
- `_msg_loop()`: Forces thread message queue creation via `PeekMessageW`, registers hotkeys (with `MOD_NOREPEAT` fallback), Win32 message pump processing `WM_HOTKEY` and invoking callbacks.
- `start() -> bool`: Starts background listener thread and registers all hotkeys.
- `stop()`: Posts `WM_QUIT` to message loop, unregisters all Win32 hotkeys, and terminates thread cleanly.
- `pause()`: Temporarily stops listener (used when recording new hotkeys in settings dialog).
- `resume()`: Resumes listener after pause.
- `update_callbacks(new_callbacks: dict[str, Callable]) -> bool`: Atomically restarts listener with updated hotkey map.
- `is_running() -> bool`

### Global Functions & Helpers
- `pause_hotkeys()`: Reference-counted hotkey pause for dialogs and recording inputs.
- `resume_hotkeys()`: Decrements pause ref-count and resumes when 0.
- `reset_hotkey_pause()`: Forces pause ref-count to 0 and immediately resumes listener.
- `get_active_hotkey_manager() -> Win32HotkeyManager | None`

### Key Conflict Troubleshooting (Win32 Error 1409)
If Win32 error 1409 occurs (`ERROR_HOTKEY_ALREADY_REGISTERED`), another process (such as a previous instance of `Shadow.exe` or another application using the same shortcut) is holding the hotkey. The previous instance must be closed via Task Manager / System Tray.
