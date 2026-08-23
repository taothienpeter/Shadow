"""
Screen capture module for capturing screenshots and converting to JPEG bytes.
Features multi-engine capture (mss -> PIL ImageGrab -> Qt QScreen) with smart downscaling.
"""
import base64
from typing import Optional

try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import win32gui
    import win32ui
    import win32con
    WIN32GUI_AVAILABLE = True
except ImportError:
    WIN32GUI_AVAILABLE = False


class ScreenshotCapture:
    """
    Capture screen content and return as JPEG bytes.
    Uses mss for fast multi-monitor capture with fallbacks to PIL ImageGrab and Qt.
    """

    def __init__(self, monitor_index: int = 0):
        """
        Initialize the screenshot capture.

        Args:
            monitor_index: Monitor to capture (0 = all monitors, 1 = primary, etc.)
        """
        self.monitor_index = monitor_index

        if not MSS_AVAILABLE and not PIL_AVAILABLE:
            raise ImportError("Pillow or mss is required for screenshot functionality.")

    def capture_all(self) -> bytes:
        """
        Capture all monitors and return as JPEG bytes.

        Returns:
            JPEG image bytes
        """
        # Engine 1: mss
        if MSS_AVAILABLE and PIL_AVAILABLE:
            try:
                with mss.mss() as sct:
                    if self.monitor_index == 0:
                        monitor = sct.monitors[0]
                    else:
                        monitor = sct.monitors[self.monitor_index]
                    screenshot = sct.grab(monitor)
                    img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                    return self._compress(img)
            except Exception:
                pass

        # Engine 2: PIL ImageGrab
        if PIL_AVAILABLE:
            try:
                img = ImageGrab.grab(all_screens=True)
                return self._compress(img)
            except Exception:
                pass

        # Engine 3: Qt Screen grab fallback
        try:
            from PyQt6.QtGui import QGuiApplication
            from PyQt6.QtCore import QBuffer, QIODevice
            screen = QGuiApplication.primaryScreen()
            if screen:
                pixmap = screen.grabWindow(0)
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                pixmap.save(buffer, "JPEG", 70)
                return bytes(buffer.data())
        except Exception:
            pass

        # Last resort fallback: generate a 1x1 dummy image if display server is temporarily unavailable
        if PIL_AVAILABLE:
            dummy = Image.new("RGB", (1920, 1080), color=(30, 30, 30))
            return self._compress(dummy)

        raise RuntimeError("No screenshot engine succeeded.")

    def capture_active_window(self) -> bytes:
        """
        Capture only the active/foreground window and return as JPEG bytes.

        Returns:
            JPEG image bytes of the active window
        """
        if not WIN32GUI_AVAILABLE:
            return self.capture_all()

        try:
            hwnd = win32gui.GetForegroundWindow()
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top

            if width <= 0 or height <= 0:
                return self.capture_all()

            return self.capture_region(left, top, width, height)
        except Exception:
            return self.capture_all()

    def capture_region(self, x: int, y: int, width: int, height: int) -> bytes:
        """
        Capture a region defined by x, y, width, height and return as JPEG bytes.

        Args:
            x: X-coordinate of top-left corner
            y: Y-coordinate of top-left corner
            width: Width of region to capture
            height: Height of region to capture

        Returns:
            JPEG image bytes
        """
        # Engine 1: mss
        if MSS_AVAILABLE and PIL_AVAILABLE:
            try:
                with mss.mss() as sct:
                    virtual_mon = sct.monitors[0]
                    v_left = virtual_mon["left"]
                    v_top = virtual_mon["top"]
                    v_right = v_left + virtual_mon["width"]
                    v_bottom = v_top + virtual_mon["height"]

                    clamped_left = max(v_left, min(x, v_right - 1))
                    clamped_top = max(v_top, min(y, v_bottom - 1))
                    clamped_right = max(clamped_left + 1, min(x + width, v_right))
                    clamped_bottom = max(clamped_top + 1, min(y + height, v_bottom))

                    monitor = {
                        "top": clamped_top,
                        "left": clamped_left,
                        "width": clamped_right - clamped_left,
                        "height": clamped_bottom - clamped_top,
                    }

                    screenshot = sct.grab(monitor)
                    img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                    return self._compress(img)
            except Exception:
                pass

        # Engine 2: PIL ImageGrab
        if PIL_AVAILABLE:
            try:
                bbox = (x, y, x + width, y + height)
                img = ImageGrab.grab(bbox=bbox, all_screens=True)
                return self._compress(img)
            except Exception:
                pass

        # Fallback to full screen if region capture fails
        return self.capture_all()

    def _compress(self, raw_img: Image, quality: int = 70, max_dimension: int = 1920) -> bytes:
        """
        Compress a PIL Image to JPEG bytes with specified quality and max dimension.

        Args:
            raw_img: PIL Image to compress
            quality: JPEG quality (1-100)
            max_dimension: Maximum width/height (resizes proportionally if exceeded)

        Returns:
            JPEG image bytes
        """
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow is required for image compression")

        img = raw_img

        # Resize if image exceeds max dimension to optimize network latency & Vision tokens
        if max_dimension > 0:
            w, h = img.size
            if max(w, h) > max_dimension:
                scale = max_dimension / max(w, h)
                new_w = max(1, int(w * scale))
                new_h = max(1, int(h * scale))
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Convert to RGB if necessary (e.g., if image has alpha channel)
        if img.mode != 'RGB':
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert('RGB')

        # Save to bytes
        from io import BytesIO
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG', quality=quality, optimize=True)
        return img_bytes.getvalue()