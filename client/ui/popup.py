"""Floating Popup Window - Module 3.1: Apple-inspired floating window for AI Assistant."""

import sys
import os
import time
import ctypes
import asyncio
from ctypes import wintypes
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QApplication,
    QWidget
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QEvent, QPoint, pyqtSignal, QObject, QAbstractAnimation
from PyQt6.QtGui import QCursor, QPainter, QColor, QPen, QFont

from client.core.api_client import ApiClient

# Win32 structures for focus forcing
ULONG_PTR = ctypes.c_size_t

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_MENU = 0x12  # ALT key
SPI_GETFOREGROUNDLOCKTIMEOUT = 0x2000
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
SPIF_SENDCHANGE = 0x02
SW_RESTORE = 9


class FloatingPopup(QDialog):
    """Apple-inspired floating window that appears near cursor."""

    # Signals for thread-safe communication from hotkey thread
    toggle_requested = pyqtSignal()
    voice_mode_requested = pyqtSignal()
    set_context_text_requested = pyqtSignal(str)
    set_input_text_requested = pyqtSignal(str)
    clear_input_requested = pyqtSignal()
    response_received = pyqtSignal(dict)  # For ask-respond responses

    def __init__(self, parent=None, api_client=None, async_runner=None):
        super().__init__(parent)
        self.api_client = api_client
        self._async_runner = async_runner
        self._pinned = False
        self._voice_mode = False
        self._drag_pos = None
        # Debounce timing to prevent rapid re-triggering
        self._last_toggle_time = 0
        self._last_voice_mode_time = 0
        self._last_show_time = 0
        self._debounce_interval = 0.3  # 300ms minimum between actions
        # Flag to prevent auto-hide during initial show/focus window
        self._is_initializing = False
        self._setup_ui()
        self._apply_styles()

        # Connect signals to slots
        self.toggle_requested.connect(self.toggle)
        self.voice_mode_requested.connect(self.show_voice_mode)
        self.set_context_text_requested.connect(self.set_context_text)
        self.set_input_text_requested.connect(self.set_input_text)
        self.clear_input_requested.connect(self.clear_input)

    def _force_focus(self):
        """Force window to foreground using multiple Win32 techniques."""
        hwnd = int(self.winId())

        if ctypes.windll.user32.GetForegroundWindow() == hwnd:
            return

        if ctypes.windll.user32.IsIconic(hwnd):
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)

        # Technique 1: SendInput ALT trick — makes Windows think our process
        # received the last input event, satisfying SetForegroundWindow rules.
        inp = (INPUT * 2)()
        inp[0].type = INPUT_KEYBOARD
        inp[0].union.ki = KEYBDINPUT(VK_MENU, 0, 0, 0, 0)
        inp[1].type = INPUT_KEYBOARD
        inp[1].union.ki = KEYBDINPUT(VK_MENU, 0, KEYEVENTF_KEYUP, 0, 0)
        ctypes.windll.user32.SendInput(2, ctypes.byref(inp),
                                         ctypes.sizeof(INPUT))

        if ctypes.windll.user32.SetForegroundWindow(hwnd):
            if ctypes.windll.user32.GetForegroundWindow() == hwnd:
                return

        # Technique 2: Temporarily disable foreground lock timeout
        # (this is how GLFW handles the same problem)
        timeout = ctypes.c_int(0)
        zero = ctypes.c_int(0)
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(timeout), 0)
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(zero),
            SPIF_SENDCHANGE)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        # Restore original timeout immediately
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(timeout),
            SPIF_SENDCHANGE)

    def _setup_ui(self):
        """Initialize the UI components and layout."""
        # Window properties
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool  # Allows window to receive focus when activated from other apps
        )
        self.setFixedSize(480, 200)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(8)

        # Build the 3 rows (removed chat area)
        main_layout.addLayout(self._create_header_row())
        main_layout.addLayout(self._create_context_chip())
        main_layout.addLayout(self._create_input_row())

        # Install event filter for focus loss detection
        self.installEventFilter(self)

    def _create_header_row(self):
        """Create Row 1: Search/Compose toggle and pin button."""
        layout = QHBoxLayout()

        self.mode_button = QPushButton("🔍 Search")
        self.mode_button.setObjectName("modeButton")
        self.mode_button.setCheckable(True)
        self.mode_button.setChecked(False)  # Start in search mode
        self.mode_button.clicked.connect(self._toggle_mode)
        layout.addWidget(self.mode_button)

        layout.addStretch()

        self.pin_button = QPushButton("📌")
        self.pin_button.setObjectName("pinButton")
        self.pin_button.setToolTip("Pin/unpin window")
        self.pin_button.clicked.connect(self.toggle_pin)
        layout.addWidget(self.pin_button)

        return layout

    def _create_context_chip(self):
        """Create Row 2: Context label and action buttons."""
        layout = QHBoxLayout()

        self.context_label = QLabel("No context")
        self.context_label.setObjectName("contextLabel")
        self.context_label.setWordWrap(True)
        self.context_label.setMaximumWidth(280)
        layout.addWidget(self.context_label)

        layout.addStretch()

        self.summarize_button = QPushButton("Summarize")
        self.summarize_button.setObjectName("contextAction")
        self.summarize_button.clicked.connect(lambda: self._on_context_action("summarize"))
        layout.addWidget(self.summarize_button)

        self.note_button = QPushButton("Take Note")
        self.note_button.setObjectName("contextAction")
        self.note_button.clicked.connect(lambda: self._on_context_action("note"))
        layout.addWidget(self.note_button)

        return layout

    def _create_input_row(self):
        """Create Row 3: Input field and send button."""
        layout = QHBoxLayout()

        self.input_field = QLineEdit()
        self.input_field.setObjectName("inputField")
        self.input_field.setPlaceholderText("Type a message...")
        self.input_field.returnPressed.connect(self._on_send_clicked)
        layout.addWidget(self.input_field)

        self.send_button = QPushButton("↑")
        self.send_button.setObjectName("sendButton")
        self.send_button.setFixedSize(40, 40)
        self.send_button.clicked.connect(self._on_send_clicked)
        layout.addWidget(self.send_button)

        return layout

    def _apply_styles(self):
        """Load and apply the stylesheet."""
        style_path = os.path.join(os.path.dirname(__file__), "styles.qss")
        try:
            with open(style_path, "r") as f:
                stylesheet = f.read()
                self.setStyleSheet(stylesheet)
        except FileNotFoundError:
            # Fallback to basic styling if file not found
            self.setStyleSheet("""
                QDialog { background: transparent; }
                QPushButton#modeButton {
                    background: rgba(255, 255, 255, 0.1);
                    color: #E5E5EA;
                    border: none;
                    border-radius: 8px;
                    padding: 6px 12px;
                }
                QPushButton#pinButton {
                    background: transparent;
                    color: #8E8E93;
                    border: none;
                    border-radius: 8px;
                    padding: 4px 8px;
                }
                QScrollArea {
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 12px;
                }
                QLabel#contextLabel {
                    color: #8E8E93;
                    font-size: 12px;
                    padding: 4px 8px;
                }
                QPushButton#contextAction {
                    background: rgba(0, 122, 255, 0.2);
                    color: #007AFF;
                    border: none;
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-size: 11px;
                }
                QLineEdit#inputField {
                    background: rgba(255, 255, 255, 0.1);
                    color: #FFFFFF;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 10px;
                    padding: 8px 12px;
                    font-size: 14px;
                }
                QLineEdit#inputField:focus {
                    border: 1px solid #007AFF;
                }
                QPushButton#sendButton {
                    background: #007AFF;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 10px;
                    padding: 8px 14px;
                    font-size: 16px;
                    font-weight: bold;
                }
                QPushButton#sendButton:hover {
                    background: #0056CC;
                }
            """)

    def show_at_cursor(self):
        """Show popup positioned to center on input field relative to cursor."""
        # Debounce to prevent rapid re-triggering
        current_time = time.time()
        if current_time - self._last_show_time < self._debounce_interval:
            return
        self._last_show_time = current_time

        cursor_pos = QCursor.pos()
        # Use our fixed dimensions instead of adjustSize() to avoid sizing conflicts
        width = 480
        height = 200  # Fixed height since we use setFixedSize

        # Position so that the input field (in bottom third) is under the cursor
        # Input field is approximately in the bottom 30% of the popup
        # Offset 24px right from widget center to center input field (input field center is 24px left of widget center)
        x = cursor_pos.x() - (width // 2) + 24  # Center input field under cursor
        # Position so input field center is under cursor (input field center is at 5/6 height - 8 from top)
        y = cursor_pos.y() - int((5 * height) / 6) + 8  # Center input field vertically under cursor

        # Adjust if it would go off screen
        screen = QApplication.screenAt(cursor_pos)
        if screen:
            geom = screen.availableGeometry()
            if x < geom.left():
                x = geom.left()
            elif x + width > geom.right():
                x = geom.right() - width
            if y < geom.top():
                y = geom.top()
            elif y + height > geom.bottom():
                y = geom.bottom() - height

        self.move(x, y)
        self.fade_in()
        self.raise_()
        self.activateWindow()

        # Mark as initializing to prevent auto-hide during focus establishment
        self._is_initializing = True
        QTimer.singleShot(500, lambda: setattr(self, '_is_initializing', False))

        # Focus the window after a short delay to let window manager settle
        QTimer.singleShot(50, self._force_focus)
        QTimer.singleShot(150, self._force_focus)
        # Auto-focus the input field after showing
        QTimer.singleShot(100, lambda: self.input_field.setFocus())

    def show_voice_mode(self):
        """Show popup with voice input active (mic icon pulsing)."""
        # Debounce to prevent rapid re-triggering
        current_time = time.time()
        if current_time - self._last_voice_mode_time < self._debounce_interval:
            return
        self._last_voice_mode_time = current_time

        self._voice_mode = True
        self.mode_button.setText("🎤 Listening")
        # Stop previous timer if it exists
        if hasattr(self, '_pulse_timer') and self._pulse_timer is not None:
            self._pulse_timer.stop()
        # Start pulsing animation for mic icon
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_mic_icon)
        self._pulse_timer.start(500)  # Pulse every 500ms
        self.show_at_cursor()  # Use same positioning as regular show

    def _pulse_mic_icon(self):
        """Pulse the mic icon during voice mode."""
        if self._voice_mode:
            current_text = self.mode_button.text()
            if "🎤" in current_text:
                self.mode_button.setText("🎤 Listening●")
            else:
                self.mode_button.setText("🎤 Listening")

    def fade_in(self):
        """Fade in animation: 200ms opacity 0->1."""
        # Prevent restarting fade-in animation if already running
        if hasattr(self, 'anim') and self.anim is not None and self.anim.state() == QAbstractAnimation.State.Running:
            return
        self.setWindowOpacity(0.0)
        self.resize(480, 200)
        self.show()
        self._force_focus()

        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(200)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

    def fade_out(self):
        """Fade out animation: 200ms opacity -> 0, then close."""
        # Prevent restarting fade-out animation if already running
        if hasattr(self, 'anim') and self.anim is not None and self.anim.state() == QAbstractAnimation.State.Running:
            return
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(200)
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.anim.finished.connect(self._after_fade_out)
        self.anim.start()

    def _after_fade_out(self):
        """Clean up after fade out animation completes."""
        self.hide()
        self._voice_mode = False
        if hasattr(self, '_pulse_timer'):
            self._pulse_timer.stop()
        self.mode_button.setText("🔍 Search")

    def toggle(self):
        """Toggle visibility: show if hidden, hide if visible."""
        # Debounce to prevent rapid re-triggering
        current_time = time.time()
        if current_time - self._last_toggle_time < self._debounce_interval:
            return
        self._last_toggle_time = current_time

        if self.isVisible():
            self.fade_out()
        else:
            self.show_at_cursor()

    def toggle_pin(self):
        """Toggle pinned state (prevents auto-hide on focus loss)."""
        self._pinned = not self._pinned
        if self._pinned:
            self.pin_button.setText("📍")  # Pushpin when pinned
            self.pin_button.setToolTip("Unpin window")
        else:
            self.pin_button.setText("📌")  # Regular pin when unpinned
            self.pin_button.setToolTip("Pin/unpin window")

    def _toggle_mode(self):
        """Toggle between search and compose modes."""
        if self.mode_button.isChecked():
            self.mode_button.setText("✏️ Compose")
        else:
            self.mode_button.setText("🔍 Search")

    def _on_send_clicked(self):
        """Handle send button click."""
        text = self.input_field.text().strip()
        if text:
            # Clear input (we removed chat area display for now)
            self.input_field.clear()
            self.context_label.setText("Sending...")

            # Send request via send_message (webhook) and emit response
            if self.api_client:
                # Use the shared async runner instead of creating a new event loop
                try:
                    future = self._async_runner.run_coro(
                        self.api_client.send_message(text)
                    )
                    future.add_done_callback(self._on_response_future_done)
                except Exception as e:
                    self.context_label.setText(f"Error: {str(e)}")
            else:
                # Fallback response when no API client
                self.context_label.setText(f"Echo: {text}")

    def _on_context_action(self, action):
        """Handle context chip button clicks."""
        if action == "summarize":
            self.context_label.setText("Summary: [Feature not implemented yet]")
        elif action == "note":
            self.context_label.setText("Note saved: [Feature not implemented yet]")

    def set_context_text(self, text: str):
        """Set the context text displayed in the context chip."""
        self.context_label.setToolTip(text)
        display_text = text if len(text) <= 100 else text[:97] + "..."
        self.context_label.setText(display_text)

    def set_input_text(self, text: str):
        """Set the text in the input field."""
        self.input_field.setText(text)

    def clear_input(self):
        """Clear the input field."""
        self.input_field.clear()

    def _on_response_future_done(self, future):
        """Called from background thread when the async response arrives."""
        try:
            response = future.result()
            if response is not None:
                self.response_received.emit(response)
                display_text = ApiClient.extract_response_text(response)
                self.set_context_text_requested.emit(f"Response: {display_text}")
            else:
                self.set_context_text_requested.emit("Error: No response received")
        except Exception as e:
            self.set_context_text_requested.emit(f"Error: {str(e)}")

    def eventFilter(self, obj, event):
        """Handle focus loss for auto-hide (unless pinned)."""
        if event.type() == QEvent.Type.WindowDeactivate:
            if not self._pinned and self.isVisible() and not self._is_initializing:
                # Delay slightly to avoid hiding on click interactions
                QTimer.singleShot(150, self._check_hide_on_deactivate)
        return super().eventFilter(obj, event)

    def _check_hide_on_deactivate(self):
        """Check if we should hide after deactivation."""
        if not self.isActiveWindow() and not self._pinned and self.isVisible():
            self.fade_out()

    def keyPressEvent(self, event):
        """Handle key presses: Escape to close, Enter to send."""
        if event.key() == Qt.Key.Key_Escape:
            self.fade_out()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if self.input_field.hasFocus():
                self._on_send_clicked()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse press for window dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging."""
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def paintEvent(self, event):
        """Custom paint event with shadow drawn inside widget bounds."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw shadow as layered rounded rects with decreasing alpha (inside bounds)
        # This creates a shadow effect with properly rounded corners
        shadow_color = QColor(0, 0, 0, 80)  # Shadow color with alpha
        for i in range(5):
            offset = 2 + i * 2  # Increasing offset for each layer
            alpha = 40 - i * 8  # Decreasing alpha for each layer
            if alpha > 0:
                painter.setBrush(QColor(0, 0, 0, alpha))
                painter.setPen(Qt.PenStyle.NoPen)
                # Draw shadow rounded rect with offset
                # Decrease corner radius proportionally to offset to maintain visual roundness
                shadow_radius = max(20 - offset, 2)  # Minimum radius of 2 to prevent disappearing
                shadow_rect = self.rect().adjusted(offset, offset, -offset, -offset)
                painter.drawRoundedRect(shadow_rect, shadow_radius, shadow_radius)

        # Semi-transparent dark background (main window)
        painter.setBrush(QColor(30, 30, 30, 220))  # Very dark gray, 86% opacity
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))  # Nearly white, 12% opacity
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 20, 20)


# Backward compatibility alias
BlankPopup = FloatingPopup