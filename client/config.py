import os
import sys
import shutil
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_default_data_dir() -> Path:
    """Return the data directory for the application, ensuring it exists."""
    if getattr(sys, "frozen", False):
        data_dir = Path(os.getenv("APPDATA", "")) / "AI Desktop Assistant"
    else:
        data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # If running packaged (.exe) and files don't exist in APPDATA yet, copy defaults
    if getattr(sys, "frozen", False):
        bundle_data = Path(sys._MEIPASS if hasattr(sys, "_MEIPASS") else sys.executable).parent / "client" / "data"
        if bundle_data.exists():
            for f in bundle_data.glob("*.json"):
                target = data_dir / f.name
                if not target.exists():
                    try:
                        shutil.copy2(f, target)
                    except Exception:
                        pass

    return data_dir


def get_env_file_path() -> str:
    """Locate the .env file across packaged, APPDATA, and local development environments."""
    if getattr(sys, "frozen", False):
        # 1. Check next to .exe
        exe_env = Path(sys.executable).parent / ".env"
        if exe_env.exists():
            return str(exe_env)
        # 2. Check APPDATA directory
        appdata_env = get_default_data_dir() / ".env"
        if appdata_env.exists():
            return str(appdata_env)

    # 3. Development local .env
    local_env = Path(__file__).resolve().parents[1] / ".env"
    if local_env.exists():
        return str(local_env)

    return ".env"


class ClientConfig(BaseSettings):
    screenshot_quality: int = 70
    theme: str = "dark"  # "dark" | "light"
    hotkey_popup: str = "<alt>+q"
    hotkey_scripts: str = "<alt>+a"
    # Notification listener settings
    notification_port: int = 8080
    tailscale_ip: str = "0.0.0.0"  # Bind address for listener (set to Tailscale IP in .env)
    # N8N webhook URL for all API interactions (chat, context analysis, notes, scripts)
    n8n_webhook_url: str = ""  # Full webhook URL
    # URL n8n uses to reach this laptop for notifications (set in .env)
    n8n_notification_url: str = ""
    # n8n API key for authenticated requests
    n8n_api_key: str = ""
    # Shared secret for authenticating incoming notifications from n8n
    n8n_auth_token: str = ""
    # Scripts configuration
    scripts_config_path: str = str(get_default_data_dir() / "scripts_config.json")
    # Notification queue configuration
    notification_queue_path: str = str(get_default_data_dir() / "notification_queue.json")
    # Hotkeys configuration
    hotkeys_config_path: str = str(get_default_data_dir() / "hotkeys_config.json")

    model_config = SettingsConfigDict(env_file=get_env_file_path(), extra="ignore")