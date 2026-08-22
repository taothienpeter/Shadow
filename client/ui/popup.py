"""Floating Popup Window — Ultra-sleek Conversational AI Assistant input bar (Apple Dark Theme)."""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QApplication, QWidget, QFrame, QMenu
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QEvent,
    pyqtSignal, QAbstractAnimation, QRectF, QProcess
)
from PyQt6.QtGui import (
    QCursor, QPainter, QColor, QPen, QFont, QLinearGradient,
    QBrush
)

from client.core.api_client import ApiClient
from client.core.script_runner import run_script

IS_WINDOWS = sys.platform == "win32"

# ── Win32 structures for focus forcing ──────────────────────────
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
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
    """Ultra-sleek conversational assistant floating bar."""

    # Signals
    toggle_requested = pyqtSignal()
    set_context_text_requested = pyqtSignal(str)
    set_input_text_requested = pyqtSignal(str)
    clear_input_requested = pyqtSignal()
    response_received = pyqtSignal(dict)
    script_executed = pyqtSignal(dict)
    scripts_changed = pyqtSignal(list)

    BASE_WIDTH = 560
    BAR_HEIGHT = 96
    BORDER_RADIUS = 18

    def __init__(self, parent=None, api_client=None, async_runner=None):
        super().__init__(parent)
        self.api_client = api_client
        self._async_runner = async_runner
        self._pinned = False
        self._drag_pos = None
        self._last_toggle_time = 0
        self._last_show_time = 0
        self._debounce_interval = 0.3
        self._is_initializing = False
        self._current_context = ""
        self._scripts: list = []
        self._scripts_config_path = None
        self._anim = None

        self._setup_ui()
        self._apply_styles()

        self.toggle_requested.connect(self.toggle)
        self.set_context_text_requested.connect(self.set_context_text)
        self.set_input_text_requested.connect(self.set_input_text)
        self.clear_input_requested.connect(self.clear_input)

    # ── Win32 Focus ─────────────────────────────────────────────

    def _force_focus(self):
        """Force window to foreground using Win32 SendInput technique."""
        if not IS_WINDOWS:
            self.raise_()
            self.activateWindow()
            return

        try:
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
            try:
                ctypes.windll.user32.SystemParametersInfoW(
                    SPI_SETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(zero), SPIF_SENDCHANGE)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            finally:
                ctypes.windll.user32.SystemParametersInfoW(
                    SPI_SETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(timeout), SPIF_SENDCHANGE)
        except Exception as e:
            self.raise_()
            self.activateWindow()

    # ── Layout ──────────────────────────────────────────────────

    def _setup_ui(self):
        """Build compact conversational bar: Top Context Tags -> Bottom Chat Input Capsule."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setFixedSize(self.BASE_WIDTH, self.BAR_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(16, 12, 16, 12)
        self.root_layout.setSpacing(6)

        # ── 1. Context Tag Row ──
        self.context_bar = QWidget()
        ctx_layout = QHBoxLayout(self.context_bar)
        ctx_layout.setContentsMargins(4, 0, 4, 0)
        ctx_layout.setSpacing(6)

        self.status_dot = QLabel()
        self.status_dot.setObjectName("statusDot")
        self.status_dot.setFixedSize(6, 6)
        ctx_layout.addWidget(self.status_dot)

        self.context_label = QLabel("Ready")
        self.context_label.setObjectName("contextLabel")
        ctx_layout.addWidget(self.context_label)

        ctx_layout.addStretch()

        # Quick action: Summarize (text-only minimal tag)
        self.summarize_btn = QPushButton("Summarize")
        self.summarize_btn.setObjectName("actionTag")
        self.summarize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.summarize_btn.clicked.connect(lambda: self._on_context_action("summarize"))
        ctx_layout.addWidget(self.summarize_btn)

        # Quick action: Note (text-only minimal tag)
        self.note_btn = QPushButton("Note")
        self.note_btn.setObjectName("actionTag")
        self.note_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.note_btn.clicked.connect(lambda: self._on_context_action("note"))
        ctx_layout.addWidget(self.note_btn)

        # Quick action: Scripts
        self.scripts_btn = QPushButton("Scripts")
        self.scripts_btn.setObjectName("actionTag")
        self.scripts_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scripts_btn.clicked.connect(self._show_scripts_menu)
        ctx_layout.addWidget(self.scripts_btn)

        self.pin_btn = QPushButton("Pin")
        self.pin_btn.setObjectName("pinTag")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_btn.clicked.connect(self._toggle_pin)
        ctx_layout.addWidget(self.pin_btn)

        self.root_layout.addWidget(self.context_bar)

        # ── 2. Bottom Chat Input Capsule ──
        self.input_frame = QFrame()
        self.input_frame.setObjectName("chatInputFrame")
        input_layout = QHBoxLayout(self.input_frame)
        input_layout.setContentsMargins(14, 2, 8, 2)
        input_layout.setSpacing(8)

        self.input_field = QLineEdit()
        self.input_field.setObjectName("chatInput")
        self.input_field.setPlaceholderText("Ask Shadow or type a message...")
        self.input_field.returnPressed.connect(self._on_send)
        input_layout.addWidget(self.input_field)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("chatSendBtn")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(self.send_btn)

        self.root_layout.addWidget(self.input_frame)

        self.input_field.installEventFilter(self)
        self.installEventFilter(self)

    # ── Styles ──────────────────────────────────────────────────

    def _apply_styles(self):
        """Load QSS from styles.qss."""
        path = os.path.join(os.path.dirname(__file__), "styles.qss")
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            print(f"Style load error: {e}")

    # ── Positioning ─────────────────────────────────────────────

    def show_at_cursor(self):
        """Show popup centered at cursor, bounded by screen geometry."""
        now = time.time()
        if now - self._last_show_time < self._debounce_interval:
            return
        self._last_show_time = now

        pos = QCursor.pos()
        width = self.BASE_WIDTH
        height = self.BAR_HEIGHT

        x = pos.x() - width // 2
        y = pos.y() - height // 2 - 20

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

    def fade_in(self):
        if self._anim and self._anim.state() == QAbstractAnimation.State.Running:
            self._anim.stop()
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
        if self._anim and self._anim.state() == QAbstractAnimation.State.Running:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(120)
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.finished.connect(self._on_fade_out_done)
        self._anim.start()

    def _on_fade_out_done(self):
        self.hide()
        self.input_field.clear()
        self.input_field.setPlaceholderText("Ask Shadow or type a message...")
        self.update()

    def toggle(self):
        now = time.time()
        if now - self._last_toggle_time < self._debounce_interval:
            return
        self._last_toggle_time = now
        self.fade_out() if self.isVisible() else self.show_at_cursor()

    # ── Actions ─────────────────────────────────────────────────

    def set_scripts(self, scripts: list, config_path=None):
        """Update popup's scripts list and config path."""
        self._scripts = list(scripts or [])
        if config_path:
            self._scripts_config_path = config_path

    def _show_scripts_menu(self):
        """Open quick scripts menu from the Scripts button."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1C1C1E;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
                padding: 6px;
                font-family: 'Segoe UI', -apple-system, sans-serif;
                font-size: 12px;
            }
            QMenu::item {
                padding: 7px 18px 7px 12px;
                border-radius: 6px;
                margin: 2px 0px;
            }
            QMenu::item:selected {
                background: rgba(0, 113, 227, 0.60);
                color: #FFFFFF;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.08);
                margin: 4px 6px;
            }
        """)

        if not self._scripts:
            empty_action = menu.addAction("No scripts configured")
            empty_action.setEnabled(False)
        else:
            for idx, script in enumerate(self._scripts):
                name = script.get("name", f"Script {idx+1}")
                hk = script.get("hotkey", "").strip()
                if hk:
                    clean_hk = " + ".join([p.strip("<>").upper() for p in hk.split("+") if p.strip()])
                    label = f"▶  {name}   [{clean_hk}]"
                else:
                    label = f"▶  {name}"
                action = menu.addAction(label)
                action.triggered.connect(lambda checked, s=script: self._run_script_by_data(s))

        menu.addSeparator()
        add_action = menu.addAction("+  Add New Script...")
        add_action.triggered.connect(self._open_add_script_dialog)

        manage_action = menu.addAction("⚙  Manage Scripts...")
        manage_action.triggered.connect(self._open_script_manager)

        # Popup directly under the scripts button
        btn_pos = self.scripts_btn.mapToGlobal(self.scripts_btn.rect().bottomLeft())
        menu.exec(btn_pos)

    def _open_add_script_dialog(self):
        """Open the Add Script dialog directly from popup."""
        try:
            from client.ui.script_dialog import ScriptEditDialog
            dlg = ScriptEditDialog(parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                new_data = dlg.get_data()
                self._scripts.append(new_data)
                cfg_path = self._scripts_config_path or Path("client/data/scripts_config.json")
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump({"scripts": self._scripts}, f, indent=2)
                self.scripts_changed.emit(self._scripts)
                self._set_status(f"Added script: {new_data['name']}", "ready")
        except Exception as e:
            print(f"Error opening add script dialog from popup: {e}")

    def _open_script_manager(self):
        """Open the full ScriptManagerDialog."""
        try:
            from client.ui.script_dialog import ScriptManagerDialog
            cfg_path = self._scripts_config_path or Path("client/data/scripts_config.json")
            dlg = ScriptManagerDialog(cfg_path, self._scripts, parent=self)
            dlg.scripts_updated.connect(self._on_scripts_updated_from_dialog)
            dlg.exec()
        except Exception as e:
            print(f"Error opening script manager from popup: {e}")

    def _on_scripts_updated_from_dialog(self, new_scripts: list):
        self._scripts = new_scripts
        self.scripts_changed.emit(new_scripts)

    def _run_script_by_data(self, script: dict):
        """Execute a script command, application, or URL and update status."""
        name = script.get("name", "script")
        self._set_status(f"Running {name}...", "working")
        success, msg = run_script(script)
        if success:
            self._set_status(f"Executed: {name}", "ready")
            self.script_executed.emit(script)
        else:
            self._set_status(f"Error: {msg}", "error")

    def _on_send(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()

        # Quick restart command
        if text.lower() in ("/restart", "/r", "restart"):
            self._set_status("Restarting...", "working")
            QTimer.singleShot(150, lambda: (QProcess.startDetached(sys.executable, sys.argv), QApplication.quit()))
            return

        # Quick script menu trigger: /s, /scripts, /script, /run, /open
        if text.lower() in ("/s", "/scripts", "/script", "/run", "/open"):
            self._show_scripts_menu()
            return

        # Direct numeric index execution (e.g. typing "1", "2", "/1", "/2")
        cleaned_num = text.lstrip("/")
        if cleaned_num.isdigit():
            idx = int(cleaned_num) - 1
            if 0 <= idx < len(self._scripts):
                self._run_script_by_data(self._scripts[idx])
                return

        # Script prefix execution: /s <name>, /run <name>, /open <name>, /script <name>
        script_prefixes = ("/s ", "/script ", "/scripts ", "/run ", "/open ")
        for pfx in script_prefixes:
            if text.lower().startswith(pfx):
                query = text[len(pfx):].strip().lower()
                matched = [s for s in self._scripts if query in s.get("name", "").lower() or query in s.get("command", "").lower()]
                if matched:
                    self._run_script_by_data(matched[0])
                else:
                    self._set_status(f"No script matched '{query}'", "error")
                return

        # Direct exact match with existing script name (e.g. typing "n8n", "Task Manager")
        direct_match = [s for s in self._scripts if s.get("name", "").strip().lower() == text.lower()]
        if direct_match:
            self._run_script_by_data(direct_match[0])
            return

        self._set_status("Thinking...", "working")

        if self.api_client and self._async_runner:
            try:
                future = self._async_runner.run_coro(self.api_client.send_message(text))
                future.add_done_callback(self._on_api_done)
            except Exception as e:
                self._set_status(f"Error: {e}", "error")
        else:
            self._set_status("Ready", "ready")

    def _on_context_action(self, action):
        ctx = self._current_context or self.context_label.text()
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
            self._set_status("Ready", "ready")

    def _on_api_done(self, future):
        try:
            resp = future.result()
            if resp:
                self.response_received.emit(resp)
                text = ApiClient.extract_response_text(resp)
                self.set_context_text_requested.emit(text)
            else:
                self.set_context_text_requested.emit("No response from server")
        except Exception as e:
            self.set_context_text_requested.emit(f"Error: {e}")

    # ── State helpers ───────────────────────────────────────────

    def _set_status(self, text, state="ready"):
        """Update context label and dot colour."""
        short = text if len(text) <= 50 else text[:47] + "..."
        self.context_label.setText(short)
        self.context_label.setToolTip(text)

        colours = {"ready": "#30D158", "working": "#FF9F0A", "error": "#FF453A"}
        c = colours.get(state, "#30D158")
        self.status_dot.setStyleSheet(
            f"background: {c}; border-radius: 3px; border: none;"
        )

    def set_context_text(self, text: str):
        self._current_context = text
        self._set_status(text, "ready")

    def set_input_text(self, text: str):
        self.input_field.setText(text)

    def clear_input(self):
        self.input_field.clear()

    def _toggle_pin(self):
        self._pinned = self.pin_btn.isChecked()
        self.pin_btn.setText("Pinned" if self._pinned else "Pin")

    # ── Events ──────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj == self.input_field and event.type() == QEvent.Type.KeyPress:
            # Prevent Alt+Q from being typed into the input field
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                if event.key() == Qt.Key.Key_Q:
                    self.fade_out()
                    return True
            elif event.key() == Qt.Key.Key_Escape:
                self.fade_out()
                return True

        if event.type() == QEvent.Type.WindowDeactivate:
            if not self._pinned and self.isVisible() and not self._is_initializing:
                QTimer.singleShot(150, self._maybe_hide)
            return super().eventFilter(obj, event)
        return super().eventFilter(obj, event)

    def _maybe_hide(self):
        if not self.isActiveWindow() and not self._pinned and self.isVisible():
            self.fade_out()

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.AltModifier and event.key() == Qt.Key.Key_Q:
            self.fade_out()
            event.accept()
            return
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
        p.setBrush(QColor(22, 22, 26, 245))

        # Rim light
        grad = QLinearGradient(body.topLeft(), body.bottomLeft())
        grad.setColorAt(0.0, QColor(255, 255, 255, 45))
        grad.setColorAt(0.4, QColor(255, 255, 255, 18))
        grad.setColorAt(1.0, QColor(255, 255, 255, 8))
        p.setPen(QPen(QBrush(grad), 0.8))

        p.drawRoundedRect(body, self.BORDER_RADIUS, self.BORDER_RADIUS)


# Backward compatibility
BlankPopup = FloatingPopup