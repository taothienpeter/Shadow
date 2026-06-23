"""
Hotkey module for AI Desktop Assistant
Listens for global hotkeys and triggers actions
"""

import sys
import subprocess
from typing import Callable, Dict
try:
    from pynput import keyboard
    HOTKEY_AVAILABLE = True
except ImportError:
    HOTKEY_AVAILABLE = False
    print("Warning: pynput not available. Hotkey functionality disabled.")


class HotkeyManager:
    """Manages global hotkey registration and handling"""

    def __init__(self, callbacks: dict = None):
        self.listener = None
        self.running = False

        # Default hotkey mappings: {hotkey_string: callback_function}
        # These can be overridden by the callbacks parameter
        self.hotkey_map = {
            '<alt>+q': self.open_notepad_q,  # Feature Q hotkey
            '<alt>+x': self.open_notepad_x,  # Feature X hotkey
            '<alt>+c': self.open_notepad_c,  # Feature C hotkey
        }

        # Override defaults with provided callbacks
        if callbacks:
            for combo, cb in callbacks.items():
                if combo in self.hotkey_map:
                    self.hotkey_map[combo] = cb

    def open_notepad_q(self):
        """Callback for Q hotkey - opens notepad"""
        print("Hotkey Q triggered: Opening notepad")
        try:
            subprocess.Popen(['notepad.exe'])
        except Exception as e:
            print(f"Failed to open notepad: {e}")

    def open_notepad_x(self):
        """Callback for X hotkey - opens notepad"""
        print("Hotkey X triggered: Opening notepad")
        try:
            subprocess.Popen(['notepad.exe'])
        except Exception as e:
            print(f"Failed to open notepad: {e}")

    def open_notepad_c(self):
        """Callback for C hotkey - opens notepad"""
        print("Hotkey C triggered: Opening notepad")
        try:
            subprocess.Popen(['notepad.exe'])
        except Exception as e:
            print(f"Failed to open notepad: {e}")

    def start(self):
        """Start the hotkey listener"""
        if not HOTKEY_AVAILABLE:
            print("Cannot start hotkey listener: pynput not available")
            return False

        if self.running:
            print("Hotkey listener already running")
            return True

        try:
            # Start the listener
            self.listener = keyboard.GlobalHotKeys({
                hotkey_str: callback for hotkey_str, callback in self.hotkey_map.items()
            })
            self.listener.start()
            self.running = True
            print("Hotkey listener started successfully")
            print("Registered hotkeys:")
            for hotkey_str in self.hotkey_map.keys():
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
    print("  Alt+Q - Feature Q (opens notepad)")
    print("  Alt+X - Feature X (opens notepad)")
    print("  Alt+C - Feature C (opens notepad)")
    print("Press Ctrl+C in this console to exit")

    # Create and start hotkey manager
    hotkey_manager = HotkeyManager()

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