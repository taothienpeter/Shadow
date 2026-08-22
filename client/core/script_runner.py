"""
Centralized script and automation runner for AI Desktop Assistant.

Handles launching:
- Web URLs (via default browser)
- Executables (.exe, .com)
- Python scripts (.py, .pyw)
- Shell commands and scripts (.bat, .cmd, .ps1, .sh)
"""

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Dict, Optional, Tuple


def run_script(script: Dict[str, str]) -> Tuple[bool, str]:
    """
    Execute a script dictionary.

    Args:
        script: Dict containing at least 'command', and optionally 'name', 'cwd'.

    Returns:
        Tuple of (success: bool, message: str)
    """
    name = script.get("name", "Script")
    cmd = script.get("command", "").strip()
    cwd = script.get("cwd", "").strip() or None

    if not cmd:
        return False, "Command is empty"

    if cwd and not Path(cwd).exists():
        cwd = None

    try:
        # Check if command is a web URL
        if cmd.startswith("http://") or cmd.startswith("https://"):
            if sys.platform == "win32":
                try:
                    os.startfile(cmd)
                except Exception:
                    webbrowser.open(cmd)
            else:
                try:
                    subprocess.Popen(["xdg-open", cmd])
                except Exception:
                    webbrowser.open(cmd)
            return True, f"Opened URL: {cmd}"

        # Otherwise execute as local process / shell command
        if sys.platform == "win32":
            subprocess.Popen(
                cmd,
                cwd=cwd,
                shell=True,
            )
        else:
            subprocess.Popen(
                cmd,
                cwd=cwd,
                shell=True,
                executable="/bin/bash",
            )
        return True, f"Launched '{name}'"

    except Exception as e:
        return False, f"Failed to run '{name}': {str(e)}"
