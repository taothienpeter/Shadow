"""Test script for FloatingPopup module with proper Windows hotkey registration."""

import sys
import os
import argparse
import ctypes
from ctypes import wintypes
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QAbstractNativeEventFilter, Qt
from PyQt6.QtGui import QGuiApplication

# Add client directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'client'))

from client.ui.popup import FloatingPopup

# Win32 API constants and structures
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_NOREPEAT = 0x4000


class HotkeyNativeEventFilter(QAbstractNativeEventFilter):
    """Intercepts WM_HOTKEY from the Windows thread message queue."""

    def __init__(self, popup_instance, hotkey_id=1):
        super().__init__()
        self.popup = popup_instance
        self.hotkey_id = hotkey_id
        self._register_hotkey()

    def _register_hotkey(self):
        """Register Alt+Q as global hotkey (thread-level, NULL hwnd)."""
        ok = user32.RegisterHotKey(
            None,  # hWnd=NULL -> messages go to calling thread
            self.hotkey_id,
            MOD_ALT | MOD_NOREPEAT,
            ord('Q')
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        print("Hotkey Alt+Q registered successfully")

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
                if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                    self.popup.toggle()
                    return (True, 0)
            except Exception as e:
                print(f"Error in nativeEventFilter: {e}")
        return (False, 0)

    def cleanup(self):
        """Unregister hotkey when cleaning up."""
        user32.UnregisterHotKey(None, self.hotkey_id)


def test_popup_only():
    """Test popup visualization only (no hotkeys)."""
    print("Testing FloatingPopup visualization...")
    print("Close the popup window to end the test.")

    app = QApplication(sys.argv)
    popup = FloatingPopup()
    popup.show_at_cursor()

    return app.exec()


def test_with_hotkeys():
    """Test popup with proper Windows hotkey integration."""
    print("Testing FloatingPopup with Windows RegisterHotKey integration...")
    print("Try these hotkeys:")
    print("  Alt+Q - Toggle popup (should give keyboard focus)")
    print("Close the popup window or press Ctrl+C in console to end test.")

    app = QApplication(sys.argv)
    popup = FloatingPopup()

    hotkey_filter = HotkeyNativeEventFilter(popup, hotkey_id=1)
    app.installNativeEventFilter(hotkey_filter)

    # Show initially for testing
    popup.show_at_cursor()

    try:
        result = app.exec()
    except KeyboardInterrupt:
        print("\nReceived interrupt signal...")
        result = 0
    finally:
        hotkey_filter.cleanup()

    return result


def main():
    parser = argparse.ArgumentParser(description='Test FloatingPopup module')
    parser.add_argument(
        '--with-hotkeys',
        action='store_true',
        help='Test with hotkey integration (default: popup only)'
    )
    parser.add_argument(
        '--no-hotkeys',
        dest='with_hotkeys',
        action='store_false',
        help='Test popup visualization only'
    )
    parser.set_defaults(with_hotkeys=False)

    args = parser.parse_args()

    if args.with_hotkeys:
        return test_with_hotkeys()
    else:
        return test_popup_only()


if __name__ == "__main__":
    sys.exit(main())
