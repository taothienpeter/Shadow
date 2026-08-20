"""
Context collector module for gathering screenshot, app info, and sending to server for analysis.
"""
import base64
import threading
from typing import Dict, Optional
from PyQt6.QtCore import QObject, pyqtSignal

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import win32gui
    import win32process
    WIN32GUI_AVAILABLE = True
except ImportError:
    WIN32GUI_AVAILABLE = False


class ContextCollector(QObject):
    """
    Collects context information (screenshot, active app info) and sends to server for analysis.

    Uses Qt signals for thread-safe communication with the GUI.
    """

    # Signals
    context_ready = pyqtSignal(dict)      # Emitted with server response
    context_error = pyqtSignal(str)       # Emitted with error message

    def __init__(self, screenshot, api_client, async_runner):
        """
        Initialize the context collector.

        Args:
            screenshot: ScreenshotCapture instance
            api_client: ApiClient instance
            async_runner: AsyncRunner instance for executing async operations
        """
        super().__init__()
        self._screenshot = screenshot
        self._api_client = api_client
        self._async_runner = async_runner

    def capture_and_analyze(self) -> None:
        """
        Main pipeline: capture screenshot, get app info, build payload, call API, emit signal.
        This method is designed to be called from the pynput hotkey thread.
        """
        # Run the actual work in a background thread to avoid blocking the hotkey thread
        thread = threading.Thread(target=self._capture_and_analyze_worker, daemon=True)
        thread.start()

    def _capture_and_analyze_worker(self) -> None:
        """
        Worker method that runs in a background thread to perform the capture and analysis.
        """
        try:
            # Step 1: Capture screenshot
            screenshot_bytes = self._screenshot.capture_all()
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

            # Step 2: Get active app info
            app_info = self.get_active_app_info()

            # Step 3: Build payload
            payload = self.build_context_payload(
                screenshot_b64=screenshot_b64,
                **app_info
            )

            # Step 4: Call webhook (async)
            try:
                # Submit coroutine to the shared async runner
                future = self._async_runner.run_coro(
                    self._api_client.ask_respond(payload)
                )
                result = future.result(timeout=60)  # Wait for result with timeout

                # Emit success signal
                self.context_ready.emit(result)
            except Exception as e:
                self.context_error.emit(f"Webhook call failed: {str(e)}")

        except Exception as e:
            self.context_error.emit(f"Capture failed: {str(e)}")

    def get_active_app_info(self) -> Dict[str, str]:
        """
        Get information about the currently active application window.

        Returns:
            Dictionary with 'app_name' and 'window_title' keys
        """
        # Default values
        app_name = "unknown"
        window_title = "unknown"

        if WIN32GUI_AVAILABLE:
            try:
                # Get the foreground window handle
                hwnd = win32gui.GetForegroundWindow()

                # Get the window title
                window_title = win32gui.GetWindowText(hwnd)

                # Get the process ID
                _, pid = win32process.GetWindowThreadProcessId(hwnd)

                # Get the process name
                if PSUTIL_AVAILABLE:
                    try:
                        process = psutil.Process(pid)
                        app_name = process.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        app_name = "unknown"
                else:
                    # Fallback without psutil
                    app_name = f"process_{pid}"
            except Exception:
                # If anything goes wrong, keep the default values
                pass

        return {
            "app_name": app_name,
            "window_title": window_title
        }

    def build_context_payload(self, screenshot_b64: str, app_name: str, window_title: str,
                            include_screenshot: bool = True) -> Dict[str, Optional[str]]:
        """
        Build the JSON payload to send to the server.

        Args:
            screenshot_b64: Base64-encoded screenshot JPEG
            app_name: Name of the active application
            window_title: Title of the active window
            include_screenshot: Whether to include the screenshot in the payload

        Returns:
            Dictionary ready to be JSON-encoded and sent to the server
        """
        from datetime import datetime, timezone

        screen_res = "1920x1080"
        try:
            if WIN32GUI_AVAILABLE:
                import win32api
                import win32con
                w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
                screen_res = f"{w}x{h}"
        except Exception:
            pass

        payload = {
            "action": "context_analysis",
            "screenshot_b64": screenshot_b64 if include_screenshot else None,
            "active_app": app_name,
            "window_title": window_title,
            "screen_resolution": screen_res,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "desktop_assistant",
            "voice_text": None  # Voice input not implemented yet
        }

        return payload