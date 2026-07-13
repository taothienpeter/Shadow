"""
Notification listener module for receiving HTTP POST notifications from n8n via Tailscale.
"""
import json
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any, Dict

from PyQt6.QtCore import QObject, pyqtSignal


class NotificationHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for receiving POST notifications from n8n."""

    def do_POST(self):
        """Handle POST request with JSON payload from n8n."""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self.send_error(400, "Empty payload")
            return

        # Verify auth token if configured
        if self.server.auth_token:
            auth_header = self.headers.get("Authorization", "")
            token = auth_header.removeprefix("Bearer ").strip()
            if token != self.server.auth_token:
                self.send_error(401, "Unauthorized")
                return

        # Only handle POST to /notification or root path
        if self.path not in ("/notification", "/"):
            self.send_error(404, "Not found")
            return

        try:
            payload_bytes = self.rfile.read(content_length)
            payload: Dict[str, Any] = json.loads(payload_bytes.decode('utf-8'))

            # Notify the Qt application via signal
            if hasattr(self.server, 'notification_callback'):
                self.server.notification_callback(payload)

            # Respond with success
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response_body = json.dumps({
                "status": "delivered",
                "received_at": datetime.now(timezone.utc).isoformat(),
            }).encode('utf-8')
            self.wfile.write(response_body)

        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            self.send_error(500, f"Internal server error: {e}")

    def do_GET(self):
        """Health check endpoint."""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))

    def log_message(self, format, *args):
        """Suppress default HTTP server log messages."""
        return  # Disable logging to keep console clean


class NotificationListener(QObject):
    """
    Listens for HTTP POST notifications from n8n on a specified port.
    Runs in a background thread to avoid blocking the Qt event loop.
    """

    # Signal emitted when a notification is received
    notification_received = pyqtSignal(dict)

    def __init__(self, host: str = "0.0.0.0", port: int = 8080, auth_token: str | None = None):
        """
        Initialize the notification listener.

        Args:
            host: Interface to bind to (use "0.0.0.0" for all interfaces)
            port: Port to listen on
            auth_token: Optional bearer token for authenticating incoming requests
        """
        super().__init__()
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.server: HTTPServer | None = None
        self.thread: Thread | None = None
        self._running = False

    def _server_thread(self):
        """Thread target that runs the HTTP server with restart logic."""
        while self._running:
            try:
                self.server = HTTPServer((self.host, self.port), NotificationHandler)
                # Provide callback and auth token to handler instances
                self.server.notification_callback = self._handle_notification
                self.server.auth_token = self.auth_token

                print(f"Notification listener started on http://{self.host}:{self.port}")
                self.server.serve_forever()
            except Exception as e:
                if self._running:  # Only log if we're still supposed to be running
                    print(f"Notification listener error: {e}. Restarting in 5 seconds...")
                    time.sleep(5)
                # If we're shutting down, break out of the loop
            finally:
                # Clean up server reference
                if hasattr(self, 'server') and self.server:
                    try:
                        self.server.shutdown()
                        self.server.server_close()
                    except:
                        pass
                    self.server = None

    def start(self):
        """Start the HTTP listener in a background thread."""
        if self._running:
            return

        self._running = True
        self.thread = Thread(target=self._server_thread, daemon=True)
        self.thread.start()
        print(f"Notification listener start process initiated on {self.host}:{self.port}")

    def stop(self):
        """Stop the HTTP listener and wait for thread to finish."""
        if not self._running:
            return

        self._running = False
        if self.thread:
            self.thread.join(timeout=10.0)  # Longer timeout to allow for restart delay
        print("Notification listener stopped.")

    def _handle_notification(self, payload: dict):
        """Internal callback to emit Qt signal when notification arrives."""
        self.notification_received.emit(payload)

    def is_running(self) -> bool:
        """Check if the listener is currently running."""
        return self._running