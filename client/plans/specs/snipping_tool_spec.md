# snipping_tool.py Specification

**Path**: `client/ui/snipping_tool.py`

## Description
High-precision Screen Snipping Overlay tool with real-time magnifier HUD, crosshair guides, and multi-monitor support.

## Classes

### `SnippingTool(QWidget)`
Full-screen translucent overlay widget that allows users to drag-select an exact bounding box on screen.

#### Signals
- `snippet_captured = pyqtSignal(bytes, QPoint)`: Emitted when selection completes, sending JPEG bytes and global screen coordinates of the selection.
- `cancelled = pyqtSignal()`: Emitted when user cancels via `Escape` or right-click.

#### Methods
- `__init__(parent=None, quality=85)`: Takes a full-screen desktop snapshot before displaying overlay.
- `start_snip()`: Shows the overlay covering the virtual multi-monitor desktop geometry.
- `mousePressEvent(event)`: Records the selection origin on left mouse press.
- `mouseMoveEvent(event)`: Updates current selection rectangle and magnifier HUD position.
- `mouseReleaseEvent(event)`: Crops the selected region from the pre-captured pixmap, compresses to JPEG bytes, and emits `snippet_captured`.
- `keyPressEvent(event)`: Cancels on `Escape`.
- `paintEvent(event)`: Draws darkened background mask, highlighted selection cutout with border, dimension label, and magnifying loupe HUD.
