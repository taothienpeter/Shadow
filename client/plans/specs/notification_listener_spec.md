# notification_listener.py Specification

**Path**: `client/core/notification_listener.py`

## Description
Background HTTP server receiving inbound JSON notifications from n8n over LAN/Tailscale.

## Classes

### `NotificationHandler(BaseHTTPRequestHandler)`
- `do_POST()`: Handles incoming notifications on `/notification` or `/`. Validates Bearer token in `Authorization` header if configured. Emits notification callback and responds with `{"status": "delivered", "received_at": "..."}`.
- `do_GET()`: Health check endpoint returning `{"status": "ok"}`.

### `ReusableHTTPServer(HTTPServer)`
- `allow_reuse_address = True` for instant socket reuse on restart.

### `NotificationListener(QObject)`
- `notification_received = pyqtSignal(dict)`: Emitted when an authorized notification payload arrives.
- `start()`: Launches HTTP server in a daemon thread.
- `stop()`: Shuts down server and wakes up waiting loop immediately via `threading.Event()` without delay.
- `is_running() -> bool`
