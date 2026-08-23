"""
Ultra-minimalist Translation Floating Card with Cursor Tracking for AI Desktop Assistant.
Follows the mouse cursor seamlessly. No clutter, no buttons — only the translated content.
Controlled via shortcuts:
- Ctrl + C : Copy translation to clipboard
- Ctrl + X : Copy to clipboard & close popup
- Escape   : Close popup
"""

import sys
from PyQt6.QtCore import Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve, QRectF, QEvent
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QLinearGradient, QBrush, QPen, QCursor,
    QKeySequence, QShortcut
)
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QApplication, QLabel

IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    import ctypes


class TranslationPopup(QDialog):
    """Minimalist floating translation HUD that tracks mouse cursor."""

    MAX_WIDTH = 440
    MIN_WIDTH = 260
    MAX_HEIGHT = 280
    MIN_HEIGHT = 70
    BORDER_RADIUS = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim = None
        self._last_text = ""
        self._copied_feedback = False

        # Frameless, on-top, tool window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._setup_ui()
        self._apply_styles()
        self._setup_shortcuts()

        # Timer to track mouse cursor in real-time
        self._tracking_timer = QTimer(self)
        self._tracking_timer.setInterval(20)  # 50 fps smooth tracking
        self._tracking_timer.timeout.connect(self._follow_cursor)

    def _setup_ui(self):
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(14, 12, 14, 12)
        self.root_layout.setSpacing(4)

        # ── Translated Text Display (Pure Content Only) ──
        self.content_edit = QTextEdit()
        self.content_edit.setObjectName("transContent")
        self.content_edit.setReadOnly(True)
        self.content_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_edit.setFont(QFont("Segoe UI", 11))
        self.content_edit.installEventFilter(self)
        self.root_layout.addWidget(self.content_edit)

        # Subtle bottom hint: "Ctrl+C copy & close • Ctrl+X / Esc close"
        self.hint_lbl = QLabel("Ctrl+C copy & close • Ctrl+X / Esc close")
        self.hint_lbl.setObjectName("transHint")
        self.hint_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.root_layout.addWidget(self.hint_lbl)

    def _setup_shortcuts(self):
        """Setup application-wide shortcuts on the dialog."""
        self.shortcut_copy = QShortcut(QKeySequence("Ctrl+C"), self)
        self.shortcut_copy.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_copy.activated.connect(self._copy_and_close)

        self.shortcut_close = QShortcut(QKeySequence("Ctrl+X"), self)
        self.shortcut_close.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_close.activated.connect(self.fade_out)

        self.shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        self.shortcut_esc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_esc.activated.connect(self.fade_out)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: transparent;
            }
            QTextEdit#transContent {
                background: transparent;
                color: #FFFFFF;
                border: none;
                padding: 0px;
                font-size: 13px;
                font-weight: 400;
                line-height: 1.45;
                selection-background-color: rgba(10, 132, 255, 0.50);
            }
            QLabel#transHint {
                color: rgba(255, 255, 255, 0.35);
                font-size: 9px;
                font-weight: 500;
                padding-top: 2px;
            }
        """)

    def show_translation(self, text: str, pos: QPoint = None):
        """Display translated text and start tracking mouse cursor."""
        self._last_text = text.strip()
        self.content_edit.setPlainText(self._last_text)
        self._copied_feedback = False
        self.hint_lbl.setText("Ctrl+C copy & close • Ctrl+X / Esc close")
        self.hint_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.35);")

        # Dynamic size calculation based on text volume
        lines = self._last_text.count("\n") + 1
        char_len = len(self._last_text)

        w = min(self.MAX_WIDTH, max(self.MIN_WIDTH, int(char_len * 6.0 + 70)))
        h = min(self.MAX_HEIGHT, max(self.MIN_HEIGHT, lines * 22 + 65))
        self.setFixedSize(w, h)

        self._follow_cursor()
        self.fade_in()
        self._tracking_timer.start()

        # Force focus to capture shortcuts
        self.content_edit.setFocus()
        if IS_WINDOWS:
            try:
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            except Exception:
                pass

    def _follow_cursor(self):
        """Reposition the popup smoothly beside the cursor, bounded by screen geometry."""
        cursor_pos = QCursor.pos()
        w = self.width()
        h = self.height()

        x = cursor_pos.x() + 18
        y = cursor_pos.y() + 18

        screen = QApplication.screenAt(cursor_pos)
        if screen:
            geo = screen.availableGeometry()
            if x + w > geo.right() - 10:
                x = cursor_pos.x() - w - 18
            if y + h > geo.bottom() - 10:
                y = cursor_pos.y() - h - 18
            x = max(geo.left() + 8, min(x, geo.right() - w - 8))
            y = max(geo.top() + 8, min(y, geo.bottom() - h - 8))

        self.move(x, y)

    def fade_in(self):
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()

        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(140)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def fade_out(self):
        self._tracking_timer.stop()
        if self._anim and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()

        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(120)
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.finished.connect(self.hide)
        self._anim.start()

    def _copy_and_close(self):
        """Copy translated content to clipboard, show neon green feedback, then smoothly fade out."""
        if self._last_text:
            QApplication.clipboard().setText(self._last_text)
            self._copied_feedback = True
            self.hint_lbl.setText("✓ Copied to clipboard!")
            self.hint_lbl.setStyleSheet("color: #30D158; font-weight: 600;")
            self.update()
            # 300ms satisfying delay for the user to see the green glowing frame
            QTimer.singleShot(300, self.fade_out)
        else:
            self.fade_out()

    def eventFilter(self, obj, event):
        """Intercept key events from child QTextEdit directly."""
        if event.type() == QEvent.Type.KeyPress:
            # Ctrl + C -> Copy to clipboard & close
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C:
                self._copy_and_close()
                return True
            # Ctrl + X -> Close without copying
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_X:
                self.fade_out()
                return True
            # Escape -> Close
            if event.key() == Qt.Key.Key_Escape:
                self.fade_out()
                return True

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        # Ctrl + C -> Copy to clipboard & close
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C:
            self._copy_and_close()
            event.accept()
            return

        # Ctrl + X -> Close without copying
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_X:
            self.fade_out()
            event.accept()
            return

        # Escape -> Close
        if event.key() == Qt.Key.Key_Escape:
            self.fade_out()
            event.accept()
            return

        super().keyPressEvent(event)

    def paintEvent(self, event):
        """Apple dark frosted glass background with subtle neon rim."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())

        # Ambient Shadow layers
        for i in range(4):
            off = 2 + i * 2
            a = int(32 - i * 7)
            if a > 0:
                sr = QRectF(rect.adjusted(off, off + 1, -off, -off + 1))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, a))
                p.drawRoundedRect(sr, max(self.BORDER_RADIUS - off, 4), max(self.BORDER_RADIUS - off, 4))

        # Main Body
        body = QRectF(rect.adjusted(2, 2, -2, -2))
        p.setBrush(QColor(20, 20, 24, 245))

        # Rim Gradient (vibrant neon green glowing rim when copied)
        grad = QLinearGradient(body.topLeft(), body.bottomLeft())
        if self._copied_feedback:
            grad.setColorAt(0.0, QColor(48, 209, 88, 220))
            grad.setColorAt(0.5, QColor(48, 209, 88, 140))
            grad.setColorAt(1.0, QColor(48, 209, 88, 60))
            p.setPen(QPen(QBrush(grad), 1.6))
        else:
            grad.setColorAt(0.0, QColor(10, 132, 255, 80))
            grad.setColorAt(0.4, QColor(255, 255, 255, 22))
            grad.setColorAt(1.0, QColor(255, 255, 255, 8))
            p.setPen(QPen(QBrush(grad), 0.9))

        p.drawRoundedRect(body, self.BORDER_RADIUS, self.BORDER_RADIUS)
