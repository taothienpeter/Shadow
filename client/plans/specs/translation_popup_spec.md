# translation_popup.py Specification

**Path**: `client/ui/translation_popup.py`

## Description
Ultra-minimalist floating translation HUD with dynamic mouse cursor tracking for Shadow Assistant.
Displays translated text seamlessly with dynamic document-layout auto-sizing, native scrollbar support for long responses, and neon green copied feedback.

## Classes

### `TranslationPopup(QDialog)`
Frameless, semi-translucent, floating tool window that tracks mouse cursor position with Apple dark glassmorphism styling.

#### Properties & Constants
- `MAX_WIDTH = 540`, `MIN_WIDTH = 260`
- `MAX_HEIGHT = 440`, `MIN_HEIGHT = 65`
- `BORDER_RADIUS = 12`

#### Methods
- `__init__(parent=None)`: Configures frameless window flags (`FramelessWindowHint`, `WindowStaysOnTopHint`, `Tool`, `WA_TranslucentBackground`).
- `_setup_ui()`: Creates root layout, read-only `QTextEdit` with `ScrollBarAsNeeded` and subtle hint label.
- `_setup_shortcuts()`: Sets application-wide shortcuts for `Ctrl+C`, `Ctrl+X`, and `Escape`.
- `show_translation(text: str, pos: QPoint = None)`: Computes optimal dimensions via `doc.setTextWidth()` & `doc.size().height()`, positions beside cursor, and starts 50 FPS cursor-tracking timer.
- `_copy_and_close()`: Copies text to clipboard, turns border into vibrant neon green (`#30D158`), sets hint to *"✓ Copied to clipboard!"*, and fades out after a 250ms feedback delay.
- `fade_out()`: Smooth 120ms opacity fade out and hides window.
- `_follow_cursor()`: Smoothly tracks `QCursor.pos()` with offset `(+18, +18)` clamped within screen boundaries.
- `eventFilter(obj, event)` & `keyPressEvent(event)`: Intercepts `Ctrl+C` (copy & close), `Ctrl+X` (close only), and `Escape` (close).
- `paintEvent(event)`: Draws multi-layer ambient shadow and dark glass body with dynamic neon green rim glow.
