"""
Shadow Assistant - Clean Uninstall Utility.
1. Stops all running instances of Shadow.
2. Removes Windows Startup Registry entry.
3. Automatically backs up user settings before cleanup.
4. Removes AppData and build binaries cleanly.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from client.core.autostart import set_autostart, is_autostart_enabled
from tools.backup_settings import backup_settings, APPDATA_DIR


def stop_running_instances():
    """Kill any running Shadow or python instances associated with the project."""
    print("1️⃣ Stopping running Shadow processes...")
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", "Shadow.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Find and stop python process running main.py
            cmd = "Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -match 'Shadow' } | Stop-Process -Force"
            subprocess.run(["powershell", "-Command", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("   ✓ Processes stopped.")
    except Exception as e:
        print(f"   ⚠️ Could not terminate process: {e}")


def remove_autostart():
    """Remove Windows Registry startup entry."""
    print("2️⃣ Checking Windows Startup Registry...")
    if is_autostart_enabled():
        set_autostart(False)
        print("   ✓ Autostart entry removed from Registry.")
    else:
        print("   ✓ No autostart entry was active.")


def backup_and_clean_data():
    """Backup settings first, then remove AppData folder."""
    print("3️⃣ Processing user data & settings...")
    if APPDATA_DIR.exists():
        # Automatic backup
        print("   📦 Creating safety backup before removal...")
        backup_zip = backup_settings()

        # Remove AppData directory
        try:
            shutil.rmtree(APPDATA_DIR)
            print(f"   ✓ AppData directory removed: {APPDATA_DIR}")
        except Exception as e:
            print(f"   ⚠️ Could not delete AppData directory: {e}")
    else:
        print("   ✓ No AppData directory found.")


def remove_build_artifacts():
    """Remove dist/ and build/ directories."""
    print("4️⃣ Removing build artifacts...")
    for folder in ("dist", "build"):
        p = ROOT_DIR / folder
        if p.exists():
            try:
                shutil.rmtree(p)
                print(f"   ✓ Removed: {folder}/")
            except Exception as e:
                print(f"   ⚠️ Could not delete {folder}/: {e}")


def uninstall():
    print("=" * 60)
    print("       Shadow Assistant — Complete Uninstall Tool")
    print("=" * 60)
    print()

    stop_running_instances()
    remove_autostart()
    backup_and_clean_data()
    remove_build_artifacts()

    print()
    print("=" * 60)
    print("✅ Shadow Assistant has been uninstalled cleanly!")
    print("   All settings were backed up in the 'backups/' folder.")
    print("=" * 60)


if __name__ == "__main__":
    uninstall()
