# screenshot.py Specification

**Path**: `client/core/screenshot.py`

## Description
Multi-engine screen capture and compression module.
Supports full-screen multi-monitor capture and precise region cropping with dynamic downscaling.

## Classes

### `ScreenshotCapture`

#### Engines (Fallbacks in Priority Order)
1. **`mss`**: Hardware-accelerated multi-monitor capture (Primary).
2. **`PIL.ImageGrab`**: Cross-platform fallback.
3. **`PyQt6.QtGui.QScreen`**: Qt display engine fallback.
4. **Dummy placeholder**: Safe fallback if display server is temporarily unavailable.

#### Methods
- `capture_all() -> bytes`: Captures all monitors (or selected monitor) as JPEG bytes.
- `capture_active_window() -> bytes`: Captures foreground window rectangle.
- `capture_region(x, y, width, height) -> bytes`: Captures explicit bounding box across multi-monitor virtual geometry.
- `_compress(raw_img, quality=None, max_dimension=None) -> bytes`: Resizes images exceeding `max_dimension` (LANCZOS) to optimize Vision token usage, converts RGBA to RGB, and compresses to JPEG bytes.
