"""
Helper script to package dist/Shadow into a clean release zip archive:
dist/Shadow-v1.0.0-windows.zip
"""

import os
import sys
import shutil
import zipfile
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[1]
DIST_SHADOW = ROOT_DIR / "dist" / "Shadow"
ZIP_PATH = ROOT_DIR / "dist" / "Shadow-v1.0.0-windows.zip"

if not DIST_SHADOW.exists():
    print(f"Error: {DIST_SHADOW} not found. Please run build.bat first.")
    exit(1)

# Ensure .env.example is copied
env_example = ROOT_DIR / ".env.example"
if env_example.exists():
    shutil.copy2(env_example, DIST_SHADOW / ".env.example")

if ZIP_PATH.exists():
    ZIP_PATH.unlink()

print(f"📦 Compressing {DIST_SHADOW} into {ZIP_PATH} ...")
with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(DIST_SHADOW):
        for file in files:
            file_path = Path(root) / file
            # Store inside 'Shadow/' root folder
            arcname = Path("Shadow") / file_path.relative_to(DIST_SHADOW)
            zf.write(file_path, arcname=str(arcname))

size_mb = ZIP_PATH.stat().st_size / (1024 * 1024)
print(f"✅ Archive created successfully: {ZIP_PATH} ({size_mb:.2f} MB)")
