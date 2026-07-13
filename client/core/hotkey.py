"""
Hotkey module for AI Desktop Assistant
Listens for global hotkeys and triggers actions
"""

import sys
from typing import Callable, Dict
try:
    from pynput import keyboard
    HOTKEY_AVAILABLE = True
except ImportError:
    HOTKEY_AVAILABLE = False
    print("Warning: pynput not available. Hotkey functionality disabled.")


class HotkeyManager:
    """Manages global hotkey registration and handling"""

    def __init__(self, callbacks: dict[str, Callable] = None):
        self.listener = None
        self.running = False
        self._callbacks = callbacks or {}

        # Warn if no callbacks provided
        if not self._callbacks:
            print("Warning: No hotkey callbacks provided")

    def start(self):
        """Start the hotkey listener"""
        if not HOTKEY_AVAILABLE:
            print("Cannot start hotkey listener: pynput not available")
            return False

        if self.running:
            print("Hotkey listener already running")
            return True

        if not self._callbacks:
            print("Warning: No hotkey callbacks provided - listener will not triggers any actions")
            return False

        try:
            # Start the listener
            self.listener = keyboard.GlobalHotKeys(self._callbacks)
            self.listener.start()
            self.running = True
            print("Hotkey listener started successfully")
            print("Registered hotkeys:")
            for hotkey_str in self._callbacks.keys():
                print(f"  {hotkey_str}")
            return True

        except Exception as e:
            import traceback
            print(f"Failed to start hotkey listener: {e}")
            traceback.print_exc()
            return False

    def stop(self):
        """Stop the hotkey listener"""
        if self.listener and self.running:
            self.listener.stop()
            self.listener = None
            self.running = False
            print("Hotkey listener stopped")

    def is_running(self):
        """Check if hotkey listener is running"""
        return self.running


def test_hotkey():
    """Test function to demonstrate hotkey functionality"""
    import time

    print("Starting hotkey test...")
    print("Try pressing:")
    print("  Alt+Q - Toggle popup")
    print("  Alt+X - Voice input mode")
    print("  Alt+C - Screenshot + context analysis")
    print("Press Ctrl+C in this console to exit")

    # Create and start hotkey manager with test callbacks
    def test_q():
        print("Hotkey Q triggered: Toggle popup")

    def test_x():
        print("Hotkey X triggered: Voice input mode")

    def test_c():
        print("Hotkey C triggered: Screenshot + context analysis")

    hotkey_manager = HotkeyManager(callbacks={
        '<alt>+q': test_q,
        '<alt>+x': test_x,
        '<alt>+c': test_c,
    })

    if hotkey_manager.start():
        print("Hotkey listener started successfully!")
        print("Listening for hotkeys... (check console for output)")

        try:
            # Keep alive and listen for keyboard interrupt
            while hotkey_manager.is_running():
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nReceived interrupt signal...")
        finally:
            print("Stopping hotkey listener...")
            hotkey_manager.stop()
            print("Hotkey listener stopped.")
    else:
        print("Failed to start hotkey listener!")
        return 1

    return 0


if __name__ == "__main__":
    test_hotkey()