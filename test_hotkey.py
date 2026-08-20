"""
Test script to demonstrate hotkey functionality with notepad
"""
import sys
import os
import time

# Add the client directory to the path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'client'))

from client.core.hotkey import HotkeyManager

def main():
    print("AI Assistant Hotkey Test")
    print("=" * 30)
    print("Testing hotkey functionality...")
    print("Try these hotkeys:")
    print("  Alt+Q - Feature Q (opens notepad)")
    print("  Alt+X - Feature X (opens notepad)")
    print("  Alt+C - Feature C (opens notepad)")
    print("Press Ctrl+C in this console to exit")
    print("-" * 30)

    # Create and start hotkey manager with test callbacks
    def on_q():
        print("  -> Triggered: Alt+Q (Toggle Popup)")

    def on_x():
        print("  -> Triggered: Alt+X (Voice Input Mode)")

    def on_c():
        print("  -> Triggered: Alt+C (Context Analysis)")

    hotkey_manager = HotkeyManager({
        "<alt>+q": on_q,
        "<alt>+x": on_x,
        "<alt>+c": on_c,
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
    sys.exit(main())