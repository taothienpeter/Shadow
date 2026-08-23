"""
Context collector module for gathering screenshot, app info, and sending to server for AI vision analysis.
Maintains a lightweight, deduplicated sliding buffer of the most recent active tasks (max 3-4 apps).
"""
import os
import base64
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import win32gui
    import win32process
    import win32api
    import win32con
    WIN32GUI_AVAILABLE = True
except ImportError:
    WIN32GUI_AVAILABLE = False


class ContextCollector(QObject):
    """
    Collects context information (screenshot, active app info) and sends to server for analysis.
    Maintains a deduplicated sliding window of recent active applications (max 4 apps)
    so memory/data stays minimal and real task history is cleanly passed in payloads.
    """

    # Max number of recent active tasks to retain (prevents data bloat)
    MAX_RECENT_APPS = 4

    # Signals
    context_ready = pyqtSignal(dict)      # Emitted with server response
    context_error = pyqtSignal(str)       # Emitted with error message
    analysis_started = pyqtSignal()       # Emitted when analysis starts

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

        # Deduplicated sliding window of recent active tasks: list of {"app_name": ..., "window_title": ...}
        self._recent_apps: List[Dict[str, str]] = []

        # Background timer to track foreground window changes in real-time (runs every 300ms)
        self._focus_tracker_timer = QTimer(self)
        self._focus_tracker_timer.setInterval(300)
        self._focus_tracker_timer.timeout.connect(self._track_foreground_window)
        self._focus_tracker_timer.start()

    def _track_foreground_window(self) -> None:
        """
        Periodically checks the foreground window. If it changed to a new external application,
        updates the deduplicated recent apps history (keeping at most MAX_RECENT_APPS).
        """
        if not WIN32GUI_AVAILABLE:
            return

        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd or not win32gui.IsWindowVisible(hwnd):
                return

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            # Skip Shadow's own process
            if pid == os.getpid():
                return

            title = win32gui.GetWindowText(hwnd).strip()
            if not title or title in ("Program Manager", "Task Switching", "Windows Shell Experience Host", ""):
                return

            app_name = "unknown"
            if PSUTIL_AVAILABLE:
                try:
                    proc = psutil.Process(pid)
                    pname = proc.name()
                    # Skip python assistant windows
                    if pname.lower() in ("python.exe", "pythonw.exe") and ("shadow" in title.lower() or "assistant" in title.lower()):
                        return
                    app_name = pname
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    return
            else:
                app_name = f"process_{pid}"

            # ── Deduplication & Sliding Window ──
            new_entry = {
                "app_name": app_name,
                "window_title": title,
            }

            # If identical to the most recent entry, ignore (no duplicate spam)
            if self._recent_apps and self._recent_apps[0]["app_name"] == app_name and self._recent_apps[0]["window_title"] == title:
                return

            # Remove previous occurrence if already in list to move to top
            self._recent_apps = [
                item for item in self._recent_apps
                if not (item["app_name"] == app_name and item["window_title"] == title)
            ]

            # Insert at head (most recent)
            self._recent_apps.insert(0, new_entry)

            # Strictly enforce max capacity (max 3-4 items)
            if len(self._recent_apps) > self.MAX_RECENT_APPS:
                self._recent_apps = self._recent_apps[:self.MAX_RECENT_APPS]

        except Exception:
            pass

    def capture_and_analyze(
        self,
        mode: str = "full",
        user_prompt: Optional[str] = None,
        pre_captured_bytes: Optional[bytes] = None,
    ) -> None:
        """
        Main pipeline: capture screenshot (or use pre-captured snippet), get previous app info,
        build payload with recent_apps, call API, and emit signal.

        Args:
            mode: "full" | "window" | "snippet"
            user_prompt: Optional custom question/instruction from user
            pre_captured_bytes: Pre-captured JPEG bytes from Snipping Tool (if mode=="snippet")
        """
        # Notify UI that analysis has started
        self.analysis_started.emit()
        # Run the actual work in a background thread to avoid blocking GUI
        thread = threading.Thread(
            target=self._capture_and_analyze_worker,
            args=(mode, user_prompt, pre_captured_bytes),
            daemon=True,
        )
        thread.start()

    def _capture_and_analyze_worker(
        self,
        mode: str,
        user_prompt: Optional[str],
        pre_captured_bytes: Optional[bytes],
    ) -> None:
        """
        Worker method that runs in a background thread to perform the capture and analysis.
        """
        try:
            # Step 1: Capture screenshot based on mode
            if pre_captured_bytes is not None:
                screenshot_bytes = pre_captured_bytes
            elif mode == "window":
                screenshot_bytes = self._screenshot.capture_active_window()
            else:
                screenshot_bytes = self._screenshot.capture_all()

            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            # Step 2: Get previous active application & recent tasks info
            app_info = self.get_active_app_info()

            # Step 3: Build payload
            payload = self.build_context_payload(
                screenshot_b64=screenshot_b64,
                capture_mode=mode,
                user_prompt=user_prompt,
                **app_info,
            )

            # Step 4: Call webhook (async)
            try:
                future = self._async_runner.run_coro(
                    self._api_client.ask_respond(payload, timeout=60.0)
                )
                result = future.result(timeout=60.0)

                # Emit success signal
                self.context_ready.emit(result)
            except Exception as e:
                self.context_error.emit(f"Webhook call failed: {str(e)}")

        except Exception as e:
            self.context_error.emit(f"Capture failed: {str(e)}")

    def get_active_app_info(self) -> Dict[str, Any]:
        """
        Get information about the user's current/previous active application window
        and recent tasks history (maximum 3-4 items).

        Returns:
            Dictionary with 'app_name', 'window_title', and 'recent_apps' keys
        """
        # If currently in another app, update tracker immediately
        self._track_foreground_window()

        if self._recent_apps:
            latest = self._recent_apps[0]
            return {
                "app_name": latest.get("app_name", "unknown"),
                "window_title": latest.get("window_title", "unknown"),
                "recent_apps": list(self._recent_apps),
            }

        # Fallback: Traverse Z-order (GW_HWNDNEXT) if recent apps list is empty
        if WIN32GUI_AVAILABLE:
            try:
                hwnd = win32gui.GetForegroundWindow()
                curr = hwnd
                while curr:
                    curr = win32gui.GetWindow(curr, win32con.GW_HWNDNEXT)
                    if not curr:
                        break
                    if not win32gui.IsWindowVisible(curr):
                        continue
                    rect = win32gui.GetWindowRect(curr)
                    if (rect[2] - rect[0] <= 0) or (rect[3] - rect[1] <= 0):
                        continue
                    title = win32gui.GetWindowText(curr).strip()
                    if not title or title in ("Program Manager", "Task Switching", "Windows Shell Experience Host", ""):
                        continue
                    _, w_pid = win32process.GetWindowThreadProcessId(curr)
                    if w_pid == os.getpid():
                        continue
                    if PSUTIL_AVAILABLE:
                        try:
                            proc = psutil.Process(w_pid)
                            pname = proc.name()
                            if pname.lower() in ("python.exe", "pythonw.exe") and ("shadow" in title.lower() or "assistant" in title.lower()):
                                continue
                            entry = {"app_name": pname, "window_title": title}
                            self._recent_apps = [entry]
                            return {
                                "app_name": pname,
                                "window_title": title,
                                "recent_apps": [entry],
                            }
                        except Exception:
                            continue
            except Exception:
                pass

        return {
            "app_name": "unknown",
            "window_title": "unknown",
            "recent_apps": [],
        }

    def _get_screen_resolution(self) -> str:
        """Dynamically detect screen resolution."""
        if WIN32GUI_AVAILABLE:
            try:
                w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
                if w > 0 and h > 0:
                    return f"{w}x{h}"
            except Exception:
                pass

        try:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.geometry()
                return f"{geo.width()}x{geo.height()}"
        except Exception:
            pass

        return "unknown"

    def build_context_payload(
        self,
        screenshot_b64: str,
        app_name: str,
        window_title: str,
        recent_apps: Optional[List[Dict[str, str]]] = None,
        capture_mode: str = "full",
        user_prompt: Optional[str] = None,
        include_screenshot: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Build the JSON payload to send to the server.

        Args:
            screenshot_b64: Base64-encoded screenshot JPEG
            app_name: Name of the previous active application
            window_title: Title of the previous active window
            recent_apps: List of up to 4 recent active applications
            capture_mode: "full" | "window" | "snippet"
            user_prompt: Optional question or instruction from user
            include_screenshot: Whether to include the screenshot in the payload

        Returns:
            Dictionary ready to be JSON-encoded and sent to the server
        """
        screen_res = self._get_screen_resolution()
        apps_list = recent_apps if recent_apps is not None else list(self._recent_apps)

        payload = {
            "action": "context_analysis",
            "capture_mode": capture_mode,
            "user_prompt": user_prompt,
            "screenshot_b64": screenshot_b64 if include_screenshot else None,
            "active_app": app_name,
            "window_title": window_title,
            "recent_apps": apps_list,
            "screen_resolution": screen_res,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "desktop_assistant",
        }

        return payload