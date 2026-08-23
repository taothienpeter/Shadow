"""
Shadow Assistant - Settings Backup & Restore Utility.
Backups all user configurations (*.json, .env) from %APPDATA%/AI Desktop Assistant.
"""

import os
import sys
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

APPDATA_DIR = Path(os.getenv("APPDATA", "")) / "AI Desktop Assistant"
LOCAL_DATA_DIR = Path(__file__).resolve().parents[1] / "client" / "data"
ROOT_DIR = Path(__file__).resolve().parents[1]
BACKUP_ROOT = Path(__file__).resolve().parents[1] / "backups"


def backup_settings(destination: Path = None) -> Path:
    """Create a timestamped zip archive of all user settings."""
    source_dir = APPDATA_DIR if APPDATA_DIR.exists() else LOCAL_DATA_DIR

    if not source_dir.exists():
        print(f"⚠️  Data directory not found at: {source_dir}")
        print("   No active settings to backup.")
        return None

    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_zip = destination or (BACKUP_ROOT / f"shadow_backup_{timestamp}.zip")

    files_backed_up = []
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        # Backup JSON files
        for item in source_dir.glob("*.json"):
            if item.is_file():
                zf.write(item, arcname=item.name)
                files_backed_up.append(item.name)

        # Backup .env if present in source_dir or root
        env_candidates = [source_dir / ".env", ROOT_DIR / ".env"]
        for env_file in env_candidates:
            if env_file.exists() and ".env" not in files_backed_up:
                zf.write(env_file, arcname=".env")
                files_backed_up.append(".env")

    if files_backed_up:
        print("✅ Settings backed up successfully!")
        print(f"📦 Backup archive: {dest_zip}")
        print("📄 Included files:")
        for f in files_backed_up:
            print(f"   - {f}")
        return dest_zip
    else:
        print("ℹ️  No configuration files (*.json, .env) found to backup.")
        return None


def restore_settings(backup_zip_path: Path) -> bool:
    """Restore configuration files from a backup zip archive."""
    zip_path = Path(backup_zip_path)
    if not zip_path.exists():
        print(f"❌ Backup archive not found: {zip_path}")
        return False

    APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(APPDATA_DIR)

    print(f"✅ Settings restored successfully into: {APPDATA_DIR}")
    return True


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--restore":
        restore_settings(Path(sys.argv[2]))
    else:
        backup_settings()
