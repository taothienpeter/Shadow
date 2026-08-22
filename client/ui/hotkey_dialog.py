"""
Hotkey Configuration Dialog for AI Desktop Assistant.
Allows users to customize global hotkeys with key recording and persistence.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict

from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QKeyEvent, QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QWidget, QFrame, QMessageBox, QGroupBox
)

from client.core.hotkey import pause_hotkeys, resume_hotkeys


class HotkeyInput(QLineEdit):
    """Custom QLineEdit that records key combinations when focused."""

    hotkey_recorded = pyqtSignal(str)

    def __init__(self, current_hotkey: str = "", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setPlaceholderText("Click and press shortcut...")
        self._current_hotkey = current_hotkey
        self.setText(self._format_display(current_hotkey))
        self._recording = False

    def _format_display(self, hotkey_str: str) -> str:
        """Format '<alt>+q' to 'Alt + Q' for clean UI display."""
        if not hotkey_str:
            return ""
        parts = [p.strip("<>").strip().upper() for p in hotkey_str.split("+") if p.strip()]
        return " + ".join(parts)

    def get_hotkey_string(self) -> str:
        """Return standardized hotkey string like '<alt>+q'."""
        return self._current_hotkey

    def set_hotkey_string(self, hotkey_str: str):
        self._current_hotkey = hotkey_str.lower().strip()
        self.setText(self._format_display(self._current_hotkey))

    def focusInEvent(self, event):
        pause_hotkeys()
        self.setPlaceholderText("Press key combination now...")
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.setPlaceholderText("Click and press shortcut...")
        resume_hotkeys()
        super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()

        # Allow clearing shortcut with Backspace or Delete
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self.set_hotkey_string("")
            self.hotkey_recorded.emit("")
            event.accept()
            return

        # Ignore standalone modifier presses
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
            return

        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("<ctrl>")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("<alt>")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("<shift>")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("<win>")

        # Key conversion
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            key_name = chr(key).lower()
        elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            key_name = chr(key)
        elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
            key_name = f"f{key - Qt.Key.Key_F1 + 1}"
        elif key == Qt.Key.Key_Space:
            key_name = "space"
        elif key == Qt.Key.Key_Escape:
            key_name = "esc"
        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            key_name = "enter"
        elif key == Qt.Key.Key_Tab:
            key_name = "tab"
        else:
            return

        parts.append(key_name)
        new_hotkey = "+".join(parts)
        self.set_hotkey_string(new_hotkey)
        self.hotkey_recorded.emit(new_hotkey)
        event.accept()


class HotkeySettingsDialog(QDialog):
    """Modern Apple-style Hotkey Configuration Dialog."""

    hotkeys_updated = pyqtSignal(dict)

    DEFAULT_HOTKEYS = {
        "hotkey_popup": "<alt>+q",
        "hotkey_context": "<alt>+c"
    }

    def __init__(self, config_path: Path, current_hotkeys: dict = None, parent=None):
        super().__init__(parent)
        self.config_path = config_path
        self._current_hotkeys = dict(self.DEFAULT_HOTKEYS)
        if current_hotkeys:
            self._current_hotkeys.update(current_hotkeys)

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self):
        self.setWindowTitle("Configure Global Hotkeys")
        self.setFixedSize(480, 320)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Title / Description
        title = QLabel("Keyboard Shortcuts")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        desc = QLabel("Click on any shortcut box and press your desired key combination.")
        desc.setObjectName("dialogSubtitle")
        desc.setWordWrap(True)
        root.addWidget(desc)

        # Form container
        form_frame = QFrame()
        form_frame.setObjectName("formFrame")
        form_layout = QVBoxLayout(form_frame)
        form_layout.setContentsMargins(16, 14, 16, 14)
        form_layout.setSpacing(12)

        # 1. Toggle Popup
        self.popup_input = self._create_row(
            form_layout,
            "Toggle Assistant Popup",
            self._current_hotkeys.get("hotkey_popup", "<alt>+q")
        )

        # 2. Context Analysis
        self.context_input = self._create_row(
            form_layout,
            "Analyze Screen Context",
            self._current_hotkeys.get("hotkey_context", "<alt>+c")
        )

        root.addWidget(form_frame)

        # Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.reset_btn = QPushButton("Reset Defaults")
        self.reset_btn.setObjectName("resetBtn")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.clicked.connect(self._on_reset_defaults)
        btn_row.addWidget(self.reset_btn)

        btn_row.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save & Apply")
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)

        root.addLayout(btn_row)

    def _create_row(self, layout: QVBoxLayout, label_text: str, current_value: str) -> HotkeyInput:
        row = QHBoxLayout()
        row.setSpacing(12)

        lbl = QLabel(label_text)
        lbl.setObjectName("fieldLabel")
        row.addWidget(lbl, 1)

        input_field = HotkeyInput(current_value)
        input_field.setObjectName("hotkeyInputBox")
        input_field.setFixedWidth(160)
        row.addWidget(input_field)

        layout.addLayout(row)
        return input_field

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: #1C1C1E;
                color: #FFFFFF;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel#dialogTitle {
                color: #FFFFFF;
                font-size: 16px;
                font-weight: 600;
            }
            QLabel#dialogSubtitle {
                color: #8E8E93;
                font-size: 12px;
            }
            QFrame#formFrame {
                background: #2C2C2E;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QLabel#fieldLabel {
                color: #F2F2F7;
                font-size: 13px;
                font-weight: 500;
            }
            QLineEdit#hotkeyInputBox {
                background: #1C1C1E;
                color: #0A84FF;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QLineEdit#hotkeyInputBox:focus {
                border: 1px solid #0A84FF;
                background: #242426;
            }
            QPushButton#resetBtn {
                background: transparent;
                color: #8E8E93;
                border: none;
                font-size: 12px;
                padding: 6px 10px;
            }
            QPushButton#resetBtn:hover {
                color: #FF453A;
            }
            QPushButton#cancelBtn {
                background: #2C2C2E;
                color: #E5E5EA;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton#cancelBtn:hover {
                background: #3A3A3C;
            }
            QPushButton#saveBtn {
                background: #0071E3;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#saveBtn:hover {
                background: #0077ED;
            }
            QPushButton#saveBtn:pressed {
                background: #005BB5;
            }
        """)

    def _on_reset_defaults(self):
        self.popup_input.set_hotkey_string(self.DEFAULT_HOTKEYS["hotkey_popup"])
        self.context_input.set_hotkey_string(self.DEFAULT_HOTKEYS["hotkey_context"])

    def _on_save(self):
        p = self.popup_input.get_hotkey_string()
        c = self.context_input.get_hotkey_string()

        # Validation: check for duplicates
        keys = [k for k in (p, c) if k]
        if len(keys) != len(set(keys)):
            QMessageBox.warning(
                self,
                "Duplicate Hotkeys",
                "Each action must have a unique shortcut key. Please assign different shortcuts."
            )
            return

        new_config = {
            "hotkey_popup": p or self.DEFAULT_HOTKEYS["hotkey_popup"],
            "hotkey_context": c or self.DEFAULT_HOTKEYS["hotkey_context"],
        }

        # Save to JSON
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(new_config, f, indent=2)
        except Exception as e:
            print(f"Error saving hotkeys to file: {e}")

        self.hotkeys_updated.emit(new_config)
        self.accept()

    def showEvent(self, event):
        pause_hotkeys()
        super().showEvent(event)

    def closeEvent(self, event):
        resume_hotkeys()
        super().closeEvent(event)

    def reject(self):
        resume_hotkeys()
        super().reject()
