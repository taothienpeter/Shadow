"""
Autostart Manager for Windows.
Manages automatic startup on Windows boot via the HKCU Run Registry key.
Requires no administrator privileges.
"""

import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import winreg

APP_NAME = "ShadowAssistant"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_launch_command() -> str:
    """Return the correct launch command whether running from source or frozen .exe."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller packaged executable
        exe_path = Path(sys.executable).resolve()
        return f'"{exe_path}"'
    else:
        # Running from Python source (client/main.py)
        python_exe = Path(sys.executable).resolve()
        main_script = Path(__file__).resolve().parents[1] / "main.py"
        # Use pythonw if available to avoid opening console window
        pythonw_exe = python_exe.parent / "pythonw.exe"
        runner = pythonw_exe if pythonw_exe.exists() else python_exe
        return f'"{runner}" "{main_script}"'


def is_autostart_enabled() -> bool:
    """Check if the application is currently registered to start with Windows."""
    if not IS_WINDOWS:
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except Exception as e:
        print(f"Error checking autostart registry: {e}")
        return False


def set_autostart(enable: bool = True) -> bool:
    """Enable or disable startup with Windows by updating the Registry."""
    if not IS_WINDOWS:
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                cmd = get_launch_command()
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                print(f"Autostart enabled in Registry: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    print("Autostart disabled in Registry.")
                except FileNotFoundError:
                    pass
            return True
    except Exception as e:
        print(f"Error setting autostart in Registry: {e}")
        return False
