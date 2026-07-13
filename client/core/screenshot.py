"""
Screen capture module for capturing screenshots and converting to JPEG bytes.
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
    from PIL import Image
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

    Uses mss for fast, cross-platform screenshot capture.
    Falls back gracefully if dependencies are not available.
    """

    def __init__(self, monitor_index: int = 0):
        """
        Initialize the screenshot capture.

        Args:
            monitor_index: Monitor to capture (0 = all monitors, 1 = primary, etc.)
        """
        self.monitor_index = monitor_index

        if not MSS_AVAILABLE:
            raise ImportError("mss is required for screenshot functionality. Install with: pip install mss")

        if not PIL_AVAILABLE:
            raise ImportError("Pillow is required for image processing. Install with: pip install Pillow")

        self._sct = mss.mss()

    def capture_all(self) -> bytes:
        """
        Capture all monitors and return as JPEG bytes.

        Returns:
            JPEG image bytes
        """
        if not MSS_AVAILABLE or not PIL_AVAILABLE:
            raise RuntimeError("Required dependencies not available")

        # Get the monitor to capture
        if self.monitor_index == 0:
            # Capture all monitors
            monitor = self._sct.monitors[0]  # Monitors[0] is the virtual encompassing all monitors
        else:
            # Capture specific monitor
            monitor = self._sct.monitors[self.monitor_index]

        # Capture the screen
        screenshot = self._sct.grab(monitor)

        # Convert to PIL Image
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

        # Compress to JPEG
        return self._compress(img)

    def capture_active_window(self) -> bytes:
        """
        Capture only the active/foreground window and return as JPEG bytes.

        Returns:
            JPEG image bytes of the active window
        """
        if not WIN32GUI_AVAILABLE:
            # Fallback to capturing all screens if win32gui is not available
            return self.capture_all()

        # Get the foreground window
        hwnd = win32gui.GetForegroundWindow()

        # Get window dimensions
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top

        # Ensure we have valid dimensions
        if width <= 0 or height <= 0:
            # Fallback to full screen if we have invalid window dimensions
            return self.capture_all()

        # Capture the region
        return self.capture_region(left, top, width, height)

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
        if not MSS_AVAILABLE or not PIL_AVAILABLE:
            raise RuntimeError("Required dependencies not available")

        # Define the region to capture
        monitor = {"top": y, "left": x, "width": width, "height": height}

        # Capture the screen
        screenshot = self._sct.grab(monitor)

        # Convert to PIL Image
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

        # Compress to JPEG
        return self._compress(img)

    def _compress(self, raw_img: Image, quality: int = 70) -> bytes:
        """
        Compress a PIL Image to JPEG bytes with specified quality.

        Args:
            raw_img: PIL Image to compress
            quality: JPEG quality (1-100)

        Returns:
            JPEG image bytes
        """
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow is required for image compression")

        img = raw_img

        # Convert to RGB if necessary (e.g., if image has alpha channel)
        if img.mode != 'RGB':
            if img.mode == 'RGBA':
                # Create a white background for transparent images
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])  # Paste using alpha channel as mask
                img = background
            else:
                img = img.convert('RGB')

        # Save to bytes
        from io import BytesIO
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG', quality=quality, optimize=True)
        return img_bytes.getvalue()