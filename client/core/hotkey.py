"""
Hotkey module for AI Desktop Assistant.
Uses native Windows RegisterHotKey API (with pynput fallback) to guarantee
zero key-bleeding into background workspaces and active applications.
"""

import sys
import time
import threading
from typing import Callable, Dict, Optional

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # Win32 Constants
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012

    def parse_hotkey_string(hotkey_str: str) -> tuple[int, int]:
        """
        Parse a hotkey string like '<alt>+q' or 'ctrl+alt+x' into (modifiers, vk_code).
        """
        modifiers = MOD_NOREPEAT
        vk_code = 0

        # Normalize parts
        parts = [p.strip().lower().strip("<>").strip() for p in hotkey_str.split("+") if p.strip()]

        for part in parts:
            if part in ("alt", "menu"):
                modifiers |= MOD_ALT
            elif part in ("ctrl", "control"):
                modifiers |= MOD_CONTROL
            elif part in ("shift",):
                modifiers |= MOD_SHIFT
            elif part in ("win", "super", "cmd"):
                modifiers |= MOD_WIN
            elif len(part) == 1:
                # Single character (a-z, 0-9)
                vk_code = ord(part.upper())
            elif part.startswith("f") and part[1:].isdigit():
                # Function keys F1 - F24
                f_num = int(part[1:])
                if 1 <= f_num <= 24:
                    vk_code = 0x70 + (f_num - 1)
            elif part in ("space", "spacebar"):
                vk_code = 0x20
            elif part in ("enter", "return"):
                vk_code = 0x0D
            elif part in ("esc", "escape"):
                vk_code = 0x1B
            elif part in ("tab",):
                vk_code = 0x09

        return modifiers, vk_code


class Win32HotkeyManager:
    """Windows native hotkey listener using RegisterHotKey."""

    def __init__(self, callbacks: dict[str, Callable]):
        global _current_manager_instance
        _current_manager_instance = self
        self._callbacks = callbacks
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._running = False
        self._was_running_before_pause = False
        self._started_evt = threading.Event()
        self._registered_ids = {}

    def start(self) -> bool:
        if self._running:
            return True

        self._started_evt.clear()
        self._thread = threading.Thread(target=self._msg_loop, daemon=True, name="Win32HotkeyThread")
        self._thread.start()

        # Wait for thread to initialize and register hotkeys
        if self._started_evt.wait(timeout=3.0):
            self._running = True
            print("Hotkey listener started successfully (Native Windows Win32)")
            print("Registered hotkeys:")
            for hotkey_str in self._callbacks.keys():
                print(f"  {hotkey_str}")
            return True
        else:
            print("Failed to start Win32 hotkey listener within timeout.")
            return False

    def _msg_loop(self):
        self._thread_id = kernel32.GetCurrentThreadId()

        # Register all hotkeys in this thread's message queue
        self._registered_ids.clear()
        for idx, (hotkey_str, cb) in enumerate(self._callbacks.items(), start=1):
            mods, vk = parse_hotkey_string(hotkey_str)
            if vk != 0:
                success = user32.RegisterHotKey(None, idx, mods, vk)
                if success:
                    self._registered_ids[idx] = (hotkey_str, cb)
                else:
                    print(f"Warning: Failed to register hotkey '{hotkey_str}' (error code: {ctypes.GetLastError()})")

        self._started_evt.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                hotkey_id = msg.wParam
                if hotkey_id in self._registered_ids:
                    _, cb = self._registered_ids[hotkey_id]
                    try:
                        cb()
                    except Exception as e:
                        print(f"Error in hotkey callback: {e}")

            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Cleanup registrations
        for hotkey_id in self._registered_ids:
            user32.UnregisterHotKey(None, hotkey_id)
        self._registered_ids.clear()

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            self._thread_id = None
        self._running = False
        print("Hotkey listener stopped")

    def pause(self):
        """Temporarily stop listener so focused dialogs can record hotkeys without triggering them."""
        if self._running:
            self._was_running_before_pause = True
            self.stop()
            print("Hotkey listener paused for key recording")

    def resume(self):
        """Resume listener if it was running before pause."""
        if self._was_running_before_pause:
            self._was_running_before_pause = False
            self.start()
            print("Hotkey listener resumed")

    def update_callbacks(self, new_callbacks: dict[str, Callable]) -> bool:
        """Dynamically update registered hotkeys and restart listener."""
        self.stop()
        self._callbacks = new_callbacks
        return self.start()

    def is_running(self) -> bool:
        return self._running


# ── Fallback implementation using pynput ─────────────────────────
try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False


class PynputHotkeyManager:
    """Fallback hotkey manager using pynput for non-Windows platforms."""

    def __init__(self, callbacks: dict[str, Callable]):
        global _current_manager_instance
        _current_manager_instance = self
        self._callbacks = callbacks
        self.listener = None
        self.running = False
        self._was_running_before_pause = False

    def start(self) -> bool:
        if not PYNPUT_AVAILABLE:
            print("Cannot start hotkey listener: pynput not available")
            return False
        if self.running:
            return True
        try:
            self.listener = keyboard.GlobalHotKeys(self._callbacks)
            self.listener.start()
            self.running = True
            print("Hotkey listener started successfully (pynput fallback)")
            return True
        except Exception as e:
            print(f"Failed to start pynput hotkey listener: {e}")
            return False

    def stop(self):
        if self.listener and self.running:
            self.listener.stop()
            self.listener = None
            self.running = False
            print("Hotkey listener stopped")

    def pause(self):
        if self.running:
            self._was_running_before_pause = True
            self.stop()

    def resume(self):
        if self._was_running_before_pause:
            self._was_running_before_pause = False
            self.start()

    def update_callbacks(self, new_callbacks: dict[str, Callable]) -> bool:
        """Dynamically update registered hotkeys and restart listener."""
        self.stop()
        self._callbacks = new_callbacks
        return self.start()

    def is_running(self) -> bool:
        return self.running


# Global instance and pause/resume helpers
_current_manager_instance = None
_pause_depth = 0


def get_active_hotkey_manager():
    global _current_manager_instance
    return _current_manager_instance


def pause_hotkeys():
    """Suspend global hotkeys (ref-counted) so inputs can record keys cleanly."""
    global _pause_depth
    _pause_depth += 1
    mgr = get_active_hotkey_manager()
    if mgr and _pause_depth == 1:
        mgr.pause()


def resume_hotkeys():
    """Resume global hotkeys when recording or dialog finishes."""
    global _pause_depth
    if _pause_depth > 0:
        _pause_depth -= 1
    mgr = get_active_hotkey_manager()
    if mgr and _pause_depth == 0:
        mgr.resume()


# Main Export
if IS_WINDOWS:
    HotkeyManager = Win32HotkeyManager
else:
    HotkeyManager = PynputHotkeyManager