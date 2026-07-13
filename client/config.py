from pydantic_settings import BaseSettings, SettingsConfigDict


class ClientConfig(BaseSettings):
    screenshot_quality: int = 70
    voice_sample_rate: int = 16000
    theme: str = "dark"  # "dark" | "light"
    hotkey_popup: str = "<alt>+q"
    hotkey_voice: str = "<alt>+x"
    hotkey_context: str = "<alt>+c"
    # Notification listener settings
    notification_port: int = 8080
    tailscale_ip: str = "0.0.0.0"  # Bind address for listener (set to Tailscale IP in .env)
    # N8N webhook URL for all API interactions (chat, context analysis, notes, scripts)
    n8n_webhook_url: str = "https://n8n.taothienpeter.io.vn/webhook/assistant"  # Full webhook URL
    # URL n8n uses to reach this laptop for notifications (set in .env)
    n8n_notification_url: str = ""
    # n8n API key for authenticated requests
    n8n_api_key: str = ""
    # Shared secret for authenticating incoming notifications from n8n
    n8n_auth_token: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")