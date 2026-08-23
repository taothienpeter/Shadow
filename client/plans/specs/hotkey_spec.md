# hotkey.py Specification

**Path**: `client/core/hotkey.py`

## Description
High-performance native Windows Win32 Hotkey Manager for Shadow Assistant.
Utilizes `user32.dll` (`RegisterHotKey`, `UnregisterHotKey`, `GetMessageW`) on an isolated background message loop thread to register global key combinations with 0% idle CPU usage.

## Classes

### `Win32HotkeyManager`
Native Windows global hotkey listener.

#### Properties
- `_callbacks: dict[str, Callable]`
- `_registered_ids: dict[int, tuple[int, Callable]]`
- `_thread_id: int | None`
- `_running: bool`

#### Key Default Mappings
- `<alt>+q`: Show/Hide Floating Popup (`popup.toggle_requested.emit`)
- `<alt>+a`: Open Scripts Menu (`popup.open_scripts_menu_requested.emit`)
- `<alt>+1..N`: Quick launch configured custom scripts (`tray._run_script(i)`)

#### Methods
- `__init__(callbacks: dict[str, Callable] = None)`
- `_parse_hotkey_str(hotkey_str: str) -> tuple[int, int]`: Parses strings like `"<alt>+q"` into Win32 MOD flags and Virtual Key codes.
- `_msg_loop()`: Win32 message pump processing `WM_HOTKEY` and invoking thread-safe callbacks.
- `start() -> bool`: Starts background listener thread and registers all hotkeys.
- `stop()`: Posts `WM_QUIT` to message loop, unregisters all Win32 hotkeys, and terminates thread cleanly.
- `pause()`: Temporarily stops listener (used when recording new hotkeys in settings dialog).
- `resume()`: Resumes listener after pause.
- `update_callbacks(new_callbacks: dict[str, Callable]) -> bool`: Atomically restarts listener with updated hotkey map.
- `is_running() -> bool`
