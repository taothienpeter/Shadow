"""Test script for FloatingPopup module."""

import sys
import os
import argparse

# Add client directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'client'))

from PyQt6.QtWidgets import QApplication
from client.ui.popup import FloatingPopup
from client.core.hotkey import HotkeyManager


def test_popup_only():
    """Test popup visualization only (no hotkeys)."""
    print("Testing FloatingPopup visualization...")
    print("Close the popup window to end the test.")

    app = QApplication(sys.argv)
    popup = FloatingPopup()
    popup.show_at_cursor()

    return app.exec()


def test_with_hotkeys():
    """Test popup with hotkey integration."""
    print("Testing FloatingPopup with hotkey integration...")
    print("Try these hotkeys:")
    print("  Alt+Q - Toggle popup")
    print("  Alt+X - Voice mode")
    print("  Alt+C - Set context text")
    print("Close the popup window or press Ctrl+C in console to end test.")

    app = QApplication(sys.argv)
    popup = FloatingPopup()

    # Set up hotkeys to control popup - use thread-safe signals to avoid
    # QBasicTimer errors from pynput listener thread
    hotkeys = HotkeyManager(callbacks={
        '<alt>+q': popup.toggle_requested.emit,
        '<alt>+x': popup.voice_mode_requested.emit,
        '<alt>+c': lambda: popup.set_context_text_requested.emit("Context: Test from hotkey"),
    })

    if not hotkeys.start():
        print("Failed to start hotkey listener!")
        return 1

    # Show popup initially
    popup.show_at_cursor()

    try:
        result = app.exec()
    except KeyboardInterrupt:
        print("\nReceived interrupt signal...")
        result = 0
    finally:
        hotkeys.stop()

    return result


def main():
    parser = argparse.ArgumentParser(description='Test FloatingPopup module')
    parser.add_argument(
        '--with-hotkeys',
        action='store_true',
        help='Test with hotkey integration (default: popup only)'
    )

    args = parser.parse_args()

    if args.with_hotkeys:
        return test_with_hotkeys()
    else:
        return test_popup_only()


if __name__ == "__main__":
    sys.exit(main())