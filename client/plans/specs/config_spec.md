# config.py Specification

**Path**: `client/config.py`

## Description
Central configuration module using `pydantic-settings`.
Manages path resolutions, environment variables, hotkeys, network endpoints, and APPDATA directory initialization for both source and packaged `.exe` environments.

## Functions

### `get_default_data_dir() -> Path`
Resolves and creates the persistent configuration data directory:
- When frozen (`Shadow.exe`): `%APPDATA%\AI Desktop Assistant`
- When in development: `client/data`
- Automatically copies default JSON config files on first packaged run if absent in APPDATA.

### `get_env_file_path() -> str`
Determines the priority order for locating `.env`:
1. Next to executable (`dist/Shadow/.env`)
2. In user APPDATA (`%APPDATA%/AI Desktop Assistant/.env`)
3. Root development workspace (`c:/shadow/.env`)

## Classes

### `ClientConfig(BaseSettings)`
Pydantic settings model loading environment variables and defaults:
- `screenshot_quality: int = 70`
- `theme: str = "dark"`
- `hotkey_popup: str = "<alt>+q"`
- `hotkey_scripts: str = "<alt>+a"`
- `notification_port: int = 8080`
- `tailscale_ip: str = "0.0.0.0"`
- `n8n_webhook_url: str = ""`
- `n8n_notification_url: str = ""`
- `n8n_api_key: str = ""`
- `n8n_auth_token: str = ""`
- `scripts_config_path: str`
- `notification_queue_path: str`
- `hotkeys_config_path: str`
