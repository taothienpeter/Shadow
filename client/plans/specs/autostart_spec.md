# autostart.py Specification

**Path**: `client/core/autostart.py`

## Description
Windows Autostart Manager for Shadow Assistant.
Manages automatic startup on Windows boot via the HKCU Run Registry key (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
Does not require administrative privileges and works across source execution (`pythonw.exe`) and frozen binary (`Shadow.exe`).

## Functions

### `get_launch_command() -> str`
Returns the appropriate execution command line string:
- In frozen `.exe` mode: `"{sys.executable}"` (points directly to `dist\Shadow\Shadow.exe`).
- In Python source mode: `"{pythonw_exe}" "{main_script}"` (runs without opening a command prompt).

### `is_autostart_enabled() -> bool`
Checks if `ShadowAssistant` is currently registered in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

### `set_autostart(enable: bool = True) -> bool`
Adds or removes `ShadowAssistant` in the Windows Registry Run key.
- If `enable=True`: writes the `get_launch_command()` string.
- If `enable=False`: deletes the `ShadowAssistant` value from the key.
