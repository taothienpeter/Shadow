"""Floating Popup Window — True Apple Spotlight layout with borderless hero input, hairline divider, and dynamic result area."""

import sys
import os
import time
import ctypes
from datetime import datetime, timezone
from ctypes import wintypes
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QApplication, QWidget, QFrame, QScrollArea
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QEvent,
    pyqtSignal, QAbstractAnimation, QRectF
)
from PyQt6.QtGui import (
    QCursor, QPainter, QColor, QPen, QFont, QLinearGradient,
    QBrush
)

from client.core.api_client import ApiClient

# ── Win32 structures for focus forcing ──────────────────────────
ULONG_PTR = ctypes.c_size_t

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_MENU = 0x12
SPI_GETFOREGROUNDLOCKTIMEOUT = 0x2000
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
SPIF_SENDCHANGE = 0x02
SW_RESTORE = 9


# ── Main Widget ─────────────────────────────────────────────────

class FloatingPopup(QDialog):
    """True Apple Spotlight-style floating assistant window."""

    # Signals
    toggle_requested = pyqtSignal()
    voice_mode_requested = pyqtSignal()
    set_context_text_requested = pyqtSignal(str)
    set_input_text_requested = pyqtSignal(str)
    clear_input_requested = pyqtSignal()
    response_received = pyqtSignal(dict)

    BASE_WIDTH = 580
    IDLE_HEIGHT = 160
    EXPANDED_HEIGHT = 260
    BORDER_RADIUS = 20

    def __init__(self, parent=None, api_client=None, async_runner=None):
        super().__init__(parent)
        self.api_client = api_client
        self._async_runner = async_runner
        self._pinned = False
        self._voice_mode = False
        self._is_expanded = False
        self._drag_pos = None
        self._last_toggle_time = 0
        self._last_voice_mode_time = 0
        self._last_show_time = 0
        self._debounce_interval = 0.3
        self._is_initializing = False

        self._setup_ui()
        self._apply_styles()

        self.toggle_requested.connect(self.toggle)
        self.voice_mode_requested.connect(self.show_voice_mode)
        self.set_context_text_requested.connect(self.set_context_text)
        self.set_input_text_requested.connect(self.set_input_text)
        self.clear_input_requested.connect(self.clear_input)

    # ── Win32 Focus ─────────────────────────────────────────────

    def _force_focus(self):
        """Force window to foreground using Win32 SendInput technique."""
        hwnd = int(self.winId())
        if ctypes.windll.user32.GetForegroundWindow() == hwnd:
            return
        if ctypes.windll.user32.IsIconic(hwnd):
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)

        inp = (INPUT * 2)()
        inp[0].type = INPUT_KEYBOARD
        inp[0].union.ki = KEYBDINPUT(VK_MENU, 0, 0, 0, 0)
        inp[1].type = INPUT_KEYBOARD
        inp[1].union.ki = KEYBDINPUT(VK_MENU, 0, KEYEVENTF_KEYUP, 0, 0)
        ctypes.windll.user32.SendInput(2, ctypes.byref(inp), ctypes.sizeof(INPUT))

        if ctypes.windll.user32.SetForegroundWindow(hwnd):
            if ctypes.windll.user32.GetForegroundWindow() == hwnd:
                return

        timeout = ctypes.c_int(0)
        zero = ctypes.c_int(0)
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(timeout), 0)
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(zero), SPIF_SENDCHANGE)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(timeout), SPIF_SENDCHANGE)

    # ── Layout ──────────────────────────────────────────────────

    def _setup_ui(self):
        """Build the clean Spotlight layout with borderless input and hairline divider."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setFixedSize(self.BASE_WIDTH, self.IDLE_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(22, 16, 22, 14)
        self.root_layout.setSpacing(0)

        # ── 1. Spotlight Hero Input (Borderless) ──
        self.root_layout.addLayout(self._build_input_row())
        self.root_layout.addSpacing(12)

        # ── 2. Hairline Divider ──
        divider = QFrame()
        divider.setObjectName("hairlineDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setFixedHeight(1)
        self.root_layout.addWidget(divider)
        self.root_layout.addSpacing(12)

        # ── 3. Middle Context & Result Zone ──
        self.root_layout.addLayout(self._build_content_row())

        self.root_layout.addStretch()

        # ── 4. Footer Zone ──
        self.root_layout.addLayout(self._build_footer_row())

        self.installEventFilter(self)

    def _build_input_row(self) -> QHBoxLayout:
        """Top input row: completely borderless, large clean typography."""
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self.input_field = QLineEdit()
        self.input_field.setObjectName("spotlightInput")
        self.input_field.setPlaceholderText("Search or ask anything...")
        self.input_field.returnPressed.connect(self._on_send)
        lay.addWidget(self.input_field)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_send)
        lay.addWidget(self.send_btn)

        return lay

    def _build_content_row(self) -> QHBoxLayout:
        """Middle row: live status dot, context description, and action buttons."""
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.status_dot = QLabel()
        self.status_dot.setObjectName("statusDot")
        self.status_dot.setFixedSize(7, 7)
        lay.addWidget(self.status_dot)

        self.context_label = QLabel("Ready")
        self.context_label.setObjectName("contextLabel")
        self.context_label.setWordWrap(True)
        lay.addWidget(self.context_label, 1)

        lay.addSpacing(8)

        self.summarize_btn = QPushButton("Summarize")
        self.summarize_btn.setObjectName("pillBtn")
        self.summarize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.summarize_btn.clicked.connect(lambda: self._on_context_action("summarize"))
        lay.addWidget(self.summarize_btn)

        self.note_btn = QPushButton("Note")
        self.note_btn.setObjectName("pillBtn")
        self.note_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.note_btn.clicked.connect(lambda: self._on_context_action("note"))
        lay.addWidget(self.note_btn)

        return lay

    def _build_footer_row(self) -> QHBoxLayout:
        """Bottom row: subtle keyboard shortcut hints and pin."""
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        for key, label in [("Esc", "close"), ("Alt+C", "context"), ("Alt+X", "voice")]:
            k = QLabel(key)
            k.setObjectName("kbdKey")
            d = QLabel(label)
            d.setObjectName("kbdDesc")
            lay.addWidget(k)
            lay.addWidget(d)

        lay.addStretch()

        self.pin_btn = QPushButton("Pin")
        self.pin_btn.setObjectName("pinBtn")
        self.pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_btn.setCheckable(True)
        self.pin_btn.clicked.connect(self._toggle_pin)
        lay.addWidget(self.pin_btn)

        return lay

    # ── Styles ──────────────────────────────────────────────────

    def _apply_styles(self):
        """Load styles from styles.qss."""
        path = os.path.join(os.path.dirname(__file__), "styles.qss")
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            print(f"Style load error: {e}")

    # ── Dynamic Height Resize ───────────────────────────────────

    def _set_expanded(self, expanded: bool):
        """Smoothly expand/collapse the popup height."""
        if self._is_expanded == expanded:
            return
        self._is_expanded = expanded
        target_h = self.EXPANDED_HEIGHT if expanded else self.IDLE_HEIGHT
        self.setFixedHeight(target_h)

    # ── Positioning ─────────────────────────────────────────────

    def show_at_cursor(self):
        """Show popup near cursor, clamped to screen bounds."""
        now = time.time()
        if now - self._last_show_time < self._debounce_interval:
            return
        self._last_show_time = now

        pos = QCursor.pos()
        width = self.BASE_WIDTH
        height = self.height()

        x = pos.x() - width // 2
        y = pos.y() - height // 2 - 25

        screen = QApplication.screenAt(pos)
        if screen:
            g = screen.availableGeometry()
            x = max(g.left() + 16, min(x, g.right() - width - 16))
            y = max(g.top() + 16, min(y, g.bottom() - height - 16))

        self.move(x, y)
        self.fade_in()
        self.raise_()
        self.activateWindow()

        self._is_initializing = True
        QTimer.singleShot(400, lambda: setattr(self, '_is_initializing', False))
        QTimer.singleShot(50, self._force_focus)
        QTimer.singleShot(100, lambda: self.input_field.setFocus())

    # ── Show / Hide ─────────────────────────────────────────────

    def fade_in(self):
        if hasattr(self, '_anim') and self._anim and self._anim.state() == QAbstractAnimation.State.Running:
            return
        self.setWindowOpacity(0.0)
        self.show()
        self._force_focus()
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(160)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def fade_out(self):
        if hasattr(self, '_anim') and self._anim and self._anim.state() == QAbstractAnimation.State.Running:
            return
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(120)
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.finished.connect(self._on_fade_out_done)
        self._anim.start()

    def _on_fade_out_done(self):
        self.hide()
        self._voice_mode = False
        self._set_expanded(False)
        self.input_field.setPlaceholderText("Search or ask anything...")
        self.update()

    def toggle(self):
        now = time.time()
        if now - self._last_toggle_time < self._debounce_interval:
            return
        self._last_toggle_time = now
        self.fade_out() if self.isVisible() else self.show_at_cursor()

    def show_voice_mode(self):
        now = time.time()
        if now - self._last_voice_mode_time < self._debounce_interval:
            return
        self._last_voice_mode_time = now
        self._voice_mode = True
        self.input_field.setPlaceholderText("Listening...")
        self.show_at_cursor()
        self.update()

    # ── Actions ─────────────────────────────────────────────────

    def _on_send(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self._set_status("Thinking...", "working")

        if self.api_client and self._async_runner:
            try:
                future = self._async_runner.run_coro(self.api_client.send_message(text))
                future.add_done_callback(self._on_api_done)
            except Exception as e:
                self._set_status(f"Error: {e}", "error")
        else:
            self._set_status(f"Echo: {text}", "ready")

    def _on_context_action(self, action):
        ctx = self.context_label.toolTip() or self.context_label.text()
        self._set_status(f"{action.capitalize()}ing...", "working")

        if self.api_client and self._async_runner:
            payload = {
                "action": f"context_{action}",
                "context": ctx,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "desktop_assistant"
            }
            try:
                future = self._async_runner.run_coro(self.api_client.ask_respond(payload))
                future.add_done_callback(self._on_api_done)
            except Exception as e:
                self._set_status(f"Error: {e}", "error")
        else:
            self._set_status(f"Simulated: {action}", "ready")

    def _on_api_done(self, future):
        try:
            resp = future.result()
            if resp:
                self.response_received.emit(resp)
                text = ApiClient.extract_response_text(resp)
                self.set_context_text_requested.emit(text)
            else:
                self.set_context_text_requested.emit("No response")
        except Exception as e:
            self.set_context_text_requested.emit(f"Error: {e}")

    # ── State helpers ───────────────────────────────────────────

    def _set_status(self, text, state="ready"):
        """Update context label, dot colour, and expand height if multiline."""
        self.context_label.setText(text)
        self.context_label.setToolTip(text)

        # Expand if response text is long
        if len(text) > 80:
            self._set_expanded(True)

        colours = {"ready": "#30D158", "working": "#FF9F0A", "error": "#FF453A"}
        c = colours.get(state, "#30D158")
        self.status_dot.setStyleSheet(
            f"background: {c}; border-radius: 3px; border: none;"
        )

    def set_context_text(self, text: str):
        self._set_status(text, "ready")

    def set_input_text(self, text: str):
        self.input_field.setText(text)

    def clear_input(self):
        self.input_field.clear()

    def _toggle_pin(self):
        self._pinned = self.pin_btn.isChecked()
        self.pin_btn.setText("Unpin" if self._pinned else "Pin")

    # ── Events ──────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.WindowDeactivate:
            if not self._pinned and self.isVisible() and not self._is_initializing:
                QTimer.singleShot(150, self._maybe_hide)
        return super().eventFilter(obj, event)

    def _maybe_hide(self):
        if not self.isActiveWindow() and not self._pinned and self.isVisible():
            self.fade_out()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.fade_out()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.input_field.hasFocus():
                self._on_send()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    # ── Paint ───────────────────────────────────────────────────

    def paintEvent(self, event):
        """Apple frosted glass with rim light."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())

        # Ambient shadow (5 layers)
        for i in range(5):
            off = 2 + i * 2
            a = int(36 - i * 7)
            if a > 0:
                sr = QRectF(rect.adjusted(off, off + 1, -off, -off + 1))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, a))
                p.drawRoundedRect(sr, max(self.BORDER_RADIUS - off, 4), max(self.BORDER_RADIUS - off, 4))

        # Main body
        body = QRectF(rect.adjusted(2, 2, -2, -2))
        p.setBrush(QColor(20, 20, 24, 242))

        # Rim light (top-bright → bottom-dim gradient border)
        if self._voice_mode:
            grad = QLinearGradient(body.topLeft(), body.bottomRight())
            grad.setColorAt(0.0, QColor(0, 113, 227, 200))
            grad.setColorAt(0.35, QColor(175, 82, 222, 200))
            grad.setColorAt(0.65, QColor(255, 45, 85, 200))
            grad.setColorAt(1.0, QColor(50, 173, 230, 200))
            p.setPen(QPen(QBrush(grad), 1.5))
        else:
            grad = QLinearGradient(body.topLeft(), body.bottomLeft())
            grad.setColorAt(0.0, QColor(255, 255, 255, 42))
            grad.setColorAt(0.4, QColor(255, 255, 255, 16))
            grad.setColorAt(1.0, QColor(255, 255, 255, 8))
            p.setPen(QPen(QBrush(grad), 0.8))

        p.drawRoundedRect(body, self.BORDER_RADIUS, self.BORDER_RADIUS)


# Backward compatibility
BlankPopup = FloatingPopup