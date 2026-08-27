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

    if not cwd:
        cwd = os.path.expanduser("~")

    try:
        # 1. Check if command is a web URL
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

        # 2. Local executable / file / script
        if sys.platform == "win32":
            clean_cmd = cmd.strip('"').strip("'")
            cmd_path = Path(clean_cmd)
            if not cmd_path.is_absolute() and cwd:
                rel_path = Path(cwd) / clean_cmd
                if rel_path.exists():
                    cmd_path = rel_path

            if cmd_path.exists():
                ext = cmd_path.suffix.lower()
                if ext == ".ps1":
                    subprocess.Popen(
                        ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(cmd_path)],
                        cwd=cwd,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                elif ext in (".py", ".pyw"):
                    python_exe = sys.executable
                    subprocess.Popen(
                        [python_exe, str(cmd_path)],
                        cwd=cwd,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                else:
                    # .exe, .lnk, documents, etc.
                    try:
                        os.startfile(str(cmd_path))
                    except Exception:
                        subprocess.Popen(
                            f'"{cmd_path}"',
                            cwd=cwd,
                            shell=True,
                        )
            else:
                # Try os.startfile for system commands (e.g. taskmgr.exe, notepad, calc) or fallback to shell
                try:
                    os.startfile(cmd)
                except Exception:
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
