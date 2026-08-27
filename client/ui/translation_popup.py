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

    MAX_WIDTH = 540
    MIN_WIDTH = 260
    MAX_HEIGHT = 440
    MIN_HEIGHT = 65
    BORDER_RADIUS = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim = None
        self._last_text = ""
        self._copied_feedback = False

        # Frameless, on-top window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._setup_ui()
        self._apply_styles()
        self._setup_shortcuts()

        # Timer to track mouse cursor and listen for shortcuts via GetAsyncKeyState
        self._last_cursor_pos = QPoint(-1, -1)
        self._tracking_timer = QTimer(self)
        self._tracking_timer.setInterval(20)  # 50 fps smooth tracking & instant shortcut response
        self._tracking_timer.timeout.connect(self._on_tick)

    def _setup_ui(self):
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(14, 12, 14, 12)
        self.root_layout.setSpacing(6)

        # ── Translated Text Display (Pure Content Only) ──
        self.content_edit = QTextEdit()
        self.content_edit.setObjectName("transContent")
        self.content_edit.setReadOnly(True)
        self.content_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.content_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_edit.setFont(QFont("Segoe UI", 11))
        self.content_edit.installEventFilter(self)
        self.root_layout.addWidget(self.content_edit)

        # Subtle bottom hint
        self.hint_lbl = QLabel("Ctrl+C / Enter / Click to copy • Esc to close")
        self.hint_lbl.setObjectName("transHint")
        self.hint_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.root_layout.addWidget(self.hint_lbl)

        self.installEventFilter(self)

    def _setup_shortcuts(self):
        """Setup application-wide shortcuts on the dialog."""
        self.shortcut_copy = QShortcut(QKeySequence("Ctrl+C"), self)
        self.shortcut_copy.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.shortcut_copy.activated.connect(self._copy_and_close)

        self.shortcut_close = QShortcut(QKeySequence("Ctrl+X"), self)
        self.shortcut_close.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.shortcut_close.activated.connect(self.fade_out)

        self.shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        self.shortcut_esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.shortcut_esc.activated.connect(self.fade_out)

        self.shortcut_enter = QShortcut(QKeySequence("Return"), self)
        self.shortcut_enter.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.shortcut_enter.activated.connect(self._copy_and_close)

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
                color: rgba(255, 255, 255, 0.38);
                font-size: 9px;
                font-weight: 500;
                padding-top: 2px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 2px 0px 2px 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.25);
                min-height: 18px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.45);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

    def _force_focus(self):
        """Force window into foreground to ensure keyboard shortcuts function immediately."""
        self.raise_()
        self.activateWindow()
        self.content_edit.setFocus()

        if not IS_WINDOWS:
            return

        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            cur_fg = user32.GetForegroundWindow()
            if cur_fg != hwnd:
                cur_thread = user32.GetWindowThreadProcessId(cur_fg, None)
                our_thread = kernel32.GetCurrentThreadId()

                if cur_thread != our_thread:
                    user32.AttachThreadInput(cur_thread, our_thread, True)
                    user32.SetForegroundWindow(hwnd)
                    user32.SetActiveWindow(hwnd)
                    user32.SetFocus(hwnd)
                    user32.AttachThreadInput(cur_thread, our_thread, False)
                else:
                    user32.SetForegroundWindow(hwnd)
                    user32.SetActiveWindow(hwnd)
        except Exception:
            pass

    def show_translation(self, text: str, pos: QPoint = None):
        """Display translated text and start tracking mouse cursor."""
        self._last_text = text.strip()
        self.content_edit.setPlainText(self._last_text)
        self._copied_feedback = False
        self.hint_lbl.setText("Ctrl+C / Enter / Click to copy • Esc to close")
        self.hint_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.38);")

        # Dynamic size calculation based on actual wrapped text layout
        char_len = len(self._last_text)
        if char_len < 40:
            target_w = max(self.MIN_WIDTH, int(char_len * 9.5 + 80))
        elif char_len < 120:
            target_w = 340
        elif char_len < 300:
            target_w = 420
        elif char_len < 600:
            target_w = 480
        else:
            target_w = self.MAX_WIDTH

        content_margin_w = 32  # left + right margins + frame padding
        text_w = target_w - content_margin_w
        doc = self.content_edit.document()
        doc.setTextWidth(text_w)
        doc_h = doc.size().height()

        target_h = int(doc_h + 46)  # doc height + hint label + margins
        target_h = min(self.MAX_HEIGHT, max(self.MIN_HEIGHT, target_h))

        self.setFixedSize(target_w, target_h)

        self._last_cursor_pos = QPoint(-1, -1)
        self._follow_cursor()
        self.fade_in()
        self._tracking_timer.start()

        # Force focus to capture shortcuts
        QTimer.singleShot(40, self._force_focus)
        QTimer.singleShot(100, lambda: self.content_edit.setFocus())

    def _on_tick(self):
        """Timer callback: monitors global key states via GetAsyncKeyState and follows cursor."""
        if not self.isVisible():
            return

        # 1. Asynchronous key detection (works 100% reliably even if focus is on another app)
        if IS_WINDOWS and not self._copied_feedback:
            try:
                user32 = ctypes.windll.user32
                ctrl_down = bool(user32.GetAsyncKeyState(0x11) & 0x8000)
                c_down = bool(user32.GetAsyncKeyState(0x43) & 0x8000)
                x_down = bool(user32.GetAsyncKeyState(0x58) & 0x8000)
                esc_down = bool(user32.GetAsyncKeyState(0x1B) & 0x8000)
                enter_down = bool(user32.GetAsyncKeyState(0x0D) & 0x8000)

                if (ctrl_down and c_down) or enter_down:
                    self._copy_and_close()
                    return
                elif (ctrl_down and x_down) or esc_down:
                    self.fade_out()
                    return
            except Exception:
                pass

        # 2. Update position beside cursor
        self._follow_cursor()

    def _follow_cursor(self):
        """Reposition the popup smoothly beside the cursor, bounded by screen geometry."""
        cursor_pos = QCursor.pos()
        if cursor_pos == self._last_cursor_pos:
            return
        self._last_cursor_pos = cursor_pos

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
            # 250ms satisfying delay for the user to see the green glowing frame
            QTimer.singleShot(250, self.fade_out)
        else:
            self.fade_out()

    def mousePressEvent(self, event):
        """Clicking on the card copies and closes."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._copy_and_close()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.fade_out()
            event.accept()
        else:
            super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        """Intercept key and mouse events from child widgets directly."""
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._copy_and_close()
                return True
            elif event.button() == Qt.MouseButton.RightButton:
                self.fade_out()
                return True

        if event.type() == QEvent.Type.KeyPress:
            # Ctrl + C -> Copy to clipboard & close
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C:
                self._copy_and_close()
                return True
            # Ctrl + X -> Close without copying
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_X:
                self.fade_out()
                return True
            # Enter / Return -> Copy to clipboard & close
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._copy_and_close()
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

        # Enter / Return -> Copy & close
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._copy_and_close()
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
