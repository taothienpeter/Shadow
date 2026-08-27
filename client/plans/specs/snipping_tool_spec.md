# snipping_tool.py Specification

**Path**: `client/ui/snipping_tool.py`

## Description
High-precision multi-monitor Screen Snipping Overlay tool with per-screen DPI awareness, native sub-pixel scaling, glowing neon blue border, and corner accent handles.

## Classes

### `ScreenOverlayWidget(QWidget)`
Transparent overlay dedicated to a single `QScreen` to guarantee 100% native DPI rendering and zero cursor offset.

#### Methods
- `__init__(screen: QScreen, controller: SnippingTool)`
- `paintEvent(event)`: Draws punch-hole cutout, glowing neon border (`#0A84FF`), corner accent handles, and dimension badge.
- Delegates mouse/key events to parent `SnippingTool`.

### `SnippingTool(QWidget)`
Multi-monitor Snipping Tool Controller. Creates and orchestrates per-screen overlays.

#### Signals
- `snippet_captured = pyqtSignal(bytes, dict)`: Emitted when selection completes, sending JPEG bytes and selection metadata.
- `snippet_cancelled = pyqtSignal()`: Emitted when user cancels via `Escape` or right-click.

#### Methods
- `__init__(screenshot_capture: ScreenshotCapture = None, parent=None)`
- `start_selection()`: Spawns a `ScreenOverlayWidget` on each connected screen in `QGuiApplication.screens()`.
- `on_mouse_press(global_pos)`, `on_mouse_move(global_pos)`, `on_mouse_release(global_pos)`: Synchronizes selection state across all screen overlays.
- `_process_selection(rect: QRect)`: Crops target screen using native `target_screen.grabWindow(0, local_x, local_y, w, h)`, compresses to JPEG bytes, and emits `snippet_captured`.
