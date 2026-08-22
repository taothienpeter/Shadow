"""
Script Management and Creation Dialogs for AI Desktop Assistant.
Premium Apple macOS / Raycast inspired dark theme UI with interactive cards,
preset templates, inline action controls, file browsing, test runner, and instant execution.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QMimeData
from PyQt6.QtGui import QFont, QCursor, QColor, QPainter, QPainterPath, QDrag
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QWidget, QFrame, QMessageBox, QScrollArea,
    QFileDialog, QButtonGroup, QApplication, QSizePolicy
)

from client.core.script_runner import run_script
from client.core.hotkey import pause_hotkeys, resume_hotkeys
from client.ui.hotkey_dialog import HotkeyInput


class ScriptCardWidget(QFrame):
    """Interactive card representing a single script with inline actions and drag-and-drop reordering."""

    run_requested = pyqtSignal(dict)
    edit_requested = pyqtSignal(dict)
    delete_requested = pyqtSignal(dict)
    reorder_requested = pyqtSignal(int, int)  # (source_index, target_index)

    def __init__(self, script: dict, index: int, parent=None):
        super().__init__(parent)
        self.script = script
        self.index = index
        self._drag_start_pos = None
        self.setObjectName("scriptCard")
        self.setAcceptDrops(True)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 12, 10)
        layout.setSpacing(10)

        # Drag grip handle
        self.grip_lbl = QLabel("⠿")
        self.grip_lbl.setObjectName("cardGrip")
        self.grip_lbl.setCursor(Qt.CursorShape.SizeAllCursor)
        self.grip_lbl.setToolTip("Drag up or down to reorder")
        layout.addWidget(self.grip_lbl)

        # Left: Indicator badge + Text details
        left_layout = QVBoxLayout()
        left_layout.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        # Badge tag
        cmd = self.script.get("command", "").strip().lower()
        badge_text = "SCRIPT"
        if cmd.startswith("http://") or cmd.startswith("https://"):
            badge_text = "WEB"
        elif cmd.endswith(".py") or "python" in cmd:
            badge_text = "PY"
        elif cmd.endswith(".ps1") or "powershell" in cmd:
            badge_text = "PS"
        elif cmd.endswith(".bat") or cmd.endswith(".cmd"):
            badge_text = "BAT"
        elif cmd.endswith(".exe"):
            badge_text = "APP"

        badge = QLabel(badge_text)
        badge.setObjectName("scriptBadge")
        title_row.addWidget(badge)

        # Script Name
        name_lbl = QLabel(self.script.get("name", "Untitled Script"))
        name_lbl.setObjectName("scriptTitle")
        title_row.addWidget(name_lbl)

        # Hotkey badge ONLY if explicitly assigned
        hotkey_str = self.script.get("hotkey", "").strip()
        if hotkey_str:
            clean_hk = " + ".join([p.strip("<>").strip().upper() for p in hotkey_str.split("+") if p.strip()])
            hk_badge = QLabel(clean_hk)
            hk_badge.setObjectName("scriptHotkeyBadge")
            title_row.addWidget(hk_badge)

        title_row.addStretch()

        left_layout.addLayout(title_row)

        # Command / Path subtitle (use Ignored horizontal policy to prevent pushing layout)
        cmd_text = self.script.get("command", "")
        cmd_lbl = QLabel(cmd_text)
        cmd_lbl.setObjectName("scriptCommand")
        cmd_lbl.setToolTip(cmd_text)
        cmd_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        left_layout.addWidget(cmd_lbl)

        if self.script.get("cwd"):
            cwd_lbl = QLabel(f"in {self.script['cwd']}")
            cwd_lbl.setObjectName("scriptCwd")
            cwd_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            left_layout.addWidget(cwd_lbl)

        layout.addLayout(left_layout, 1)

        # Right: Action buttons (Fixed width to guarantee visibility)
        action_layout = QHBoxLayout()
        action_layout.setSpacing(6)

        self.run_btn = QPushButton("▶ Run")
        self.run_btn.setObjectName("cardRunBtn")
        self.run_btn.setFixedWidth(66)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(lambda: self.run_requested.emit(self.script))
        action_layout.addWidget(self.run_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setObjectName("cardEditBtn")
        self.edit_btn.setFixedWidth(52)
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.script))
        action_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("cardDeleteBtn")
        self.delete_btn.setFixedWidth(60)
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.script))
        action_layout.addWidget(self.delete_btn)

        layout.addLayout(action_layout)

    # ── Drag and Drop Reordering Events ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self._drag_start_pos:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"script_reorder:{self.index}")
        drag.setMimeData(mime_data)

        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())

        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start_pos = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("script_reorder:"):
            event.acceptProposedAction()
            self.setProperty("dragOver", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event):
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        text = event.mimeData().text()
        if text.startswith("script_reorder:"):
            try:
                src_idx = int(text.split(":")[1])
                tgt_idx = self.index
                if src_idx != tgt_idx:
                    self.reorder_requested.emit(src_idx, tgt_idx)
                event.acceptProposedAction()
            except Exception:
                pass


class ScriptEditDialog(QDialog):
    """Refined Apple/Raycast-style dialog to create or edit an automation script."""

    def __init__(self, script: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.script = script or {}
        self._is_editing = bool(script)

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self):
        self.setWindowTitle("Edit Script" if self._is_editing else "Add Automation Script")
        self.setFixedSize(520, 440)
        # Ensure dialog stays in foreground on Windows
        self.setWindowFlags(
            (self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
            | Qt.WindowType.WindowStaysOnTopHint
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(12)

        # ── Header ──
        header_box = QVBoxLayout()
        header_box.setSpacing(3)
        title = QLabel("Edit Automation Script" if self._is_editing else "Add New Automation Script")
        title.setObjectName("dialogHeader")
        subtitle = QLabel("Create a quick launch action with global hotkeys (e.g. Alt+1, Alt+2).")
        subtitle.setObjectName("dialogSubheader")
        header_box.addWidget(title)
        header_box.addWidget(subtitle)
        root.addLayout(header_box)

        # ── Quick Type Presets ──
        preset_box = QHBoxLayout()
        preset_box.setSpacing(6)
        preset_lbl = QLabel("Type:")
        preset_lbl.setObjectName("presetLabel")
        preset_box.addWidget(preset_lbl)

        self.btn_app = QPushButton("Executable / App")
        self.btn_app.setObjectName("presetChip")
        self.btn_app.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_app.clicked.connect(lambda: self._on_preset_selected("app"))
        preset_box.addWidget(self.btn_app)

        self.btn_py = QPushButton("Python")
        self.btn_py.setObjectName("presetChip")
        self.btn_py.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_py.clicked.connect(lambda: self._on_preset_selected("py"))
        preset_box.addWidget(self.btn_py)

        self.btn_bat = QPushButton("Batch / PS")
        self.btn_bat.setObjectName("presetChip")
        self.btn_bat.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bat.clicked.connect(lambda: self._on_preset_selected("bat"))
        preset_box.addWidget(self.btn_bat)

        self.btn_url = QPushButton("Web URL")
        self.btn_url.setObjectName("presetChip")
        self.btn_url.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_url.clicked.connect(lambda: self._on_preset_selected("url"))
        preset_box.addWidget(self.btn_url)

        preset_box.addStretch()
        root.addLayout(preset_box)

        # ── Form Frame ──
        form_frame = QFrame()
        form_frame.setObjectName("editFormFrame")
        form_layout = QVBoxLayout(form_frame)
        form_layout.setContentsMargins(16, 12, 16, 12)
        form_layout.setSpacing(10)

        # 1. Script Name
        name_box = QVBoxLayout()
        name_box.setSpacing(3)
        name_lbl = QLabel("Display Name")
        name_lbl.setObjectName("formFieldTitle")
        self.name_input = QLineEdit(self.script.get("name", ""))
        self.name_input.setPlaceholderText("e.g. Open Notion, Restart Docker, Open Gmail")
        self.name_input.setObjectName("modernInput")
        name_box.addWidget(name_lbl)
        name_box.addWidget(self.name_input)
        form_layout.addLayout(name_box)

        # 2. Command / Executable Path / URL
        cmd_box = QVBoxLayout()
        cmd_box.setSpacing(3)
        cmd_lbl = QLabel("Command / File Path / URL")
        cmd_lbl.setObjectName("formFieldTitle")

        cmd_input_row = QHBoxLayout()
        cmd_input_row.setSpacing(6)
        self.cmd_input = QLineEdit(self.script.get("command", ""))
        self.cmd_input.setPlaceholderText("e.g. taskmgr.exe, python script.py, or https://chatgpt.com")
        self.cmd_input.setObjectName("modernInput")

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setObjectName("secondaryBtn")
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.clicked.connect(self._on_browse_file)

        cmd_input_row.addWidget(self.cmd_input, 1)
        cmd_input_row.addWidget(self.browse_btn)

        cmd_box.addWidget(cmd_lbl)
        cmd_box.addLayout(cmd_input_row)
        form_layout.addLayout(cmd_box)

        # 3. Working Directory (Optional)
        cwd_box = QVBoxLayout()
        cwd_box.setSpacing(3)
        cwd_lbl = QLabel("Working Directory (Optional)")
        cwd_lbl.setObjectName("formFieldTitle")

        cwd_input_row = QHBoxLayout()
        cwd_input_row.setSpacing(6)
        self.cwd_input = QLineEdit(self.script.get("cwd", ""))
        self.cwd_input.setPlaceholderText("Defaults to current folder or file directory")
        self.cwd_input.setObjectName("modernInput")

        self.browse_dir_btn = QPushButton("Folder...")
        self.browse_dir_btn.setObjectName("secondaryBtn")
        self.browse_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_dir_btn.clicked.connect(self._on_browse_dir)

        cwd_input_row.addWidget(self.cwd_input, 1)
        cwd_input_row.addWidget(self.browse_dir_btn)

        cwd_box.addWidget(cwd_lbl)
        cwd_box.addLayout(cwd_input_row)
        form_layout.addLayout(cwd_box)

        # 4. Shortcut Hotkey (Optional)
        hk_box = QVBoxLayout()
        hk_box.setSpacing(3)
        hk_lbl = QLabel("Global Shortcut Hotkey (Optional)")
        hk_lbl.setObjectName("formFieldTitle")

        hk_input_row = QHBoxLayout()
        hk_input_row.setSpacing(6)

        current_hk = self.script.get("hotkey", "")
        self.hotkey_input = HotkeyInput(current_hk, parent=self)
        self.hotkey_input.setObjectName("modernInput")
        self.hotkey_input.setPlaceholderText("Click and press shortcut (e.g. Alt+1)...")

        self.clear_hk_btn = QPushButton("Clear")
        self.clear_hk_btn.setObjectName("secondaryBtn")
        self.clear_hk_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_hk_btn.clicked.connect(lambda: self.hotkey_input.set_hotkey_string(""))

        hk_input_row.addWidget(self.hotkey_input, 1)
        hk_input_row.addWidget(self.clear_hk_btn)

        hk_box.addWidget(hk_lbl)
        hk_box.addLayout(hk_input_row)
        form_layout.addLayout(hk_box)

        root.addWidget(form_frame)

        # ── Footer Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.test_btn = QPushButton("⚡ Test Run")
        self.test_btn.setObjectName("testBtn")
        self.test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_btn.clicked.connect(self._on_test_run)
        btn_row.addWidget(self.test_btn)

        btn_row.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save Changes" if self._is_editing else "Add Script")
        self.save_btn.setObjectName("primaryBtn")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)

        root.addLayout(btn_row)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: #1C1C1E;
                color: #FFFFFF;
                font-family: 'Segoe UI Variable Display', 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel#dialogHeader {
                color: #FFFFFF;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#dialogSubheader {
                color: #8E8E93;
                font-size: 12px;
            }
            QLabel#presetLabel {
                color: #8E8E93;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#presetChip {
                background: rgba(255, 255, 255, 0.06);
                color: #A1A1A6;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton#presetChip:hover {
                background: rgba(0, 113, 227, 0.20);
                color: #0A84FF;
                border: 1px solid rgba(10, 132, 255, 0.35);
            }
            QFrame#editFormFrame {
                background: #252528;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QLabel#formFieldTitle {
                color: #A1A1A6;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QLineEdit#modernInput {
                background: #1C1C1E;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 7px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit#modernInput:focus {
                border: 1px solid #0071E3;
                background: #202023;
            }
            QPushButton#secondaryBtn {
                background: rgba(255, 255, 255, 0.08);
                color: #E5E5EA;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 7px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton#secondaryBtn:hover {
                background: rgba(255, 255, 255, 0.15);
                color: #FFFFFF;
            }
            QPushButton#testBtn {
                background: rgba(48, 209, 88, 0.12);
                color: #30D158;
                border: 1px solid rgba(48, 209, 88, 0.25);
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#testBtn:hover {
                background: rgba(48, 209, 88, 0.22);
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
                color: #FFFFFF;
            }
            QPushButton#primaryBtn {
                background: #0071E3;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#primaryBtn:hover {
                background: #0077ED;
            }
            QPushButton#primaryBtn:pressed {
                background: #005BB5;
            }
        """)

    def _on_preset_selected(self, preset: str):
        if preset == "app":
            self._on_browse_file("Executable Files (*.exe *.com *.bat *.cmd);;All Files (*.*)")
        elif preset == "py":
            self._on_browse_file("Python Files (*.py *.pyw);;All Files (*.*)")
        elif preset == "bat":
            self._on_browse_file("Scripts (*.ps1 *.bat *.cmd *.vbs *.ahk);;All Files (*.*)")
        elif preset == "url":
            if not self.cmd_input.text().strip():
                self.cmd_input.setText("https://")
                self.cmd_input.setFocus()
            if not self.name_input.text().strip():
                self.name_input.setText("Open Website")

    def _on_browse_file(self, filter_pattern: str = "Executable / Scripts (*.exe *.bat *.cmd *.ps1 *.py *.pyw *.ahk *.vbs *.lnk);;All Files (*.*)"):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Executable or Script",
            "",
            filter_pattern
        )
        if file_path:
            p = Path(file_path)
            # Wrap Python files with python interpreter if appropriate
            if p.suffix.lower() in (".py", ".pyw"):
                self.cmd_input.setText(f'python "{file_path}"')
            else:
                self.cmd_input.setText(f'"{file_path}"' if " " in file_path else file_path)

            if not self.name_input.text().strip():
                base_name = p.stem.replace("_", " ").replace("-", " ").title()
                self.name_input.setText(base_name)
            if not self.cwd_input.text().strip():
                self.cwd_input.setText(str(p.parent))

    def _on_browse_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Working Directory")
        if dir_path:
            self.cwd_input.setText(dir_path)

    def _on_test_run(self):
        cmd = self.cmd_input.text().strip()
        name = self.name_input.text().strip() or "Test Script"
        cwd = self.cwd_input.text().strip()
        if not cmd:
            QMessageBox.warning(self, "Test Run", "Please enter a command or path first.")
            return

        success, msg = run_script({"name": name, "command": cmd, "cwd": cwd})
        if success:
            QMessageBox.information(self, "Test Run", f"Command executed successfully!\n{msg}")
        else:
            QMessageBox.critical(self, "Test Run Error", msg)

    def _on_save(self):
        name = self.name_input.text().strip()
        command = self.cmd_input.text().strip()
        cwd = self.cwd_input.text().strip()

        if not name:
            QMessageBox.warning(self, "Required Field", "Please provide a display name for this script.")
            self.name_input.setFocus()
            return
        if not command:
            QMessageBox.warning(self, "Required Field", "Please specify a command, file path, or URL.")
            self.cmd_input.setFocus()
            return

        hotkey = self.hotkey_input.get_hotkey_string()

        self.script_data = {
            "name": name,
            "command": command,
            "cwd": cwd,
            "hotkey": hotkey
        }
        self.accept()

    def get_data(self) -> dict:
        return getattr(self, "script_data", self.script)

    def showEvent(self, event):
        pause_hotkeys()
        super().showEvent(event)

    def closeEvent(self, event):
        resume_hotkeys()
        super().closeEvent(event)

    def reject(self):
        resume_hotkeys()
        super().reject()


class ScriptManagerDialog(QDialog):
    """Refined Apple/Raycast style Script Management Dialog with interactive cards."""

    scripts_updated = pyqtSignal(list)

    def __init__(self, config_path: Path, scripts: List[dict] = None, parent=None):
        super().__init__(parent)
        self.config_path = config_path
        self._scripts: List[dict] = list(scripts or [])

        self._setup_ui()
        self._apply_styles()
        self._populate_cards()

    def _setup_ui(self):
        self.setWindowTitle("Script Manager")
        self.setFixedSize(650, 520)
        self.setWindowFlags(
            (self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
            | Qt.WindowType.WindowStaysOnTopHint
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(14)

        # ── Header Row ──
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Scripts & Automations")
        title.setObjectName("dialogHeader")
        self.count_lbl = QLabel(f"{len(self._scripts)} scripts configured")
        self.count_lbl.setObjectName("dialogSubheader")
        title_box.addWidget(title)
        title_box.addWidget(self.count_lbl)
        header_row.addLayout(title_box)

        header_row.addStretch()

        self.add_btn = QPushButton("+ New Script")
        self.add_btn.setObjectName("primaryBtn")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self._on_add)
        header_row.addWidget(self.add_btn)

        root.addLayout(header_row)

        # ── Filter Search Bar ──
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchBar")
        self.search_input.setPlaceholderText("Filter scripts by name or command...")
        self.search_input.textChanged.connect(self._on_filter_changed)
        root.addWidget(self.search_input)

        # ── Scrollable Card Area ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("cardScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.card_container = QWidget()
        self.card_container.setObjectName("cardContainer")
        self.card_layout = QVBoxLayout(self.card_container)
        self.card_layout.setContentsMargins(0, 4, 4, 4)
        self.card_layout.setSpacing(8)

        self.scroll_area.setWidget(self.card_container)
        root.addWidget(self.scroll_area, 1)

        # ── Footer ──
        footer_row = QHBoxLayout()
        footer_row.addStretch()

        self.close_btn = QPushButton("Done")
        self.close_btn.setObjectName("cancelBtn")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.accept)
        footer_row.addWidget(self.close_btn)

        root.addLayout(footer_row)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: #1C1C1E;
                color: #FFFFFF;
                font-family: 'Segoe UI Variable Display', 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel#dialogHeader {
                color: #FFFFFF;
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#dialogSubheader {
                color: #8E8E93;
                font-size: 12px;
            }
            QLineEdit#searchBar {
                background: #252528;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 7px 12px;
                font-size: 12px;
            }
            QLineEdit#searchBar:focus {
                border: 1px solid #0071E3;
                background: #28282C;
            }
            QScrollArea#cardScrollArea {
                background: transparent;
                border: none;
            }
            QWidget#cardContainer {
                background: transparent;
            }
            QFrame#scriptCard {
                background: #252528;
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 10px;
            }
            QFrame#scriptCard:hover {
                background: #2A2A2E;
                border: 1px solid rgba(255, 255, 255, 0.14);
            }
            QLabel#scriptBadge {
                background: rgba(0, 113, 227, 0.18);
                color: #0A84FF;
                border: 1px solid rgba(10, 132, 255, 0.30);
                border-radius: 4px;
                font-size: 9px;
                font-weight: 700;
                padding: 1px 5px;
            }
            QLabel#scriptHotkeyBadge {
                background: rgba(255, 159, 10, 0.15);
                color: #FF9F0A;
                border: 1px solid rgba(255, 159, 10, 0.30);
                border-radius: 4px;
                font-size: 9px;
                font-weight: 700;
                padding: 1px 5px;
            }
            QLabel#scriptTitle {
                color: #F5F5F7;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#scriptCommand {
                color: #8E8E93;
                font-size: 11px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
            QLabel#cardGrip {
                color: #636366;
                font-size: 16px;
                font-weight: bold;
                padding-right: 2px;
            }
            QLabel#cardGrip:hover {
                color: #0A84FF;
            }
            QFrame#scriptCard[dragOver="true"] {
                background: rgba(0, 113, 227, 0.20);
                border: 2px dashed #0A84FF;
            }
            QPushButton#cardRunBtn {
                background: rgba(0, 113, 227, 0.85);
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#cardRunBtn:hover {
                background: #0077ED;
            }
            QPushButton#cardEditBtn {
                background: rgba(255, 255, 255, 0.07);
                color: #E5E5EA;
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton#cardEditBtn:hover {
                background: rgba(255, 255, 255, 0.14);
                color: #FFFFFF;
            }
            QPushButton#cardDeleteBtn {
                background: rgba(255, 69, 58, 0.12);
                color: #FF453A;
                border: 1px solid rgba(255, 69, 58, 0.25);
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton#cardDeleteBtn:hover {
                background: rgba(255, 69, 58, 0.25);
                border: 1px solid rgba(255, 69, 58, 0.45);
            }
            QPushButton#primaryBtn {
                background: #0071E3;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#primaryBtn:hover {
                background: #0077ED;
            }
            QPushButton#cancelBtn {
                background: #2C2C2E;
                color: #E5E5EA;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton#cancelBtn:hover {
                background: #3A3A3C;
                color: #FFFFFF;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

    def _populate_cards(self, filter_text: str = ""):
        while self.card_layout.count():
            item = self.card_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        filter_lower = filter_text.strip().lower()
        matched = 0

        for idx, script in enumerate(self._scripts):
            name = script.get("name", "")
            cmd = script.get("command", "")
            if filter_lower and (filter_lower not in name.lower() and filter_lower not in cmd.lower()):
                continue

            card = ScriptCardWidget(script, index=idx, parent=self.card_container)
            card.reorder_requested.connect(self._on_reorder_cards)
            card.run_requested.connect(self._on_run_card)
            card.edit_requested.connect(lambda s, i=idx: self._on_edit_card(i))
            card.delete_requested.connect(lambda s, i=idx: self._on_delete_card(i))
            self.card_layout.addWidget(card)
            matched += 1

        if matched == 0:
            empty_box = QFrame()
            empty_box.setObjectName("emptyBox")
            empty_lay = QVBoxLayout(empty_box)
            empty_lay.setContentsMargins(20, 30, 20, 30)
            empty_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

            msg = QLabel("No scripts match your search." if filter_text else "No custom scripts configured yet.")
            msg.setStyleSheet("color: #8E8E93; font-size: 13px; font-weight: 500;")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lay.addWidget(msg)

            submsg = QLabel("Click '+ New Script' above to create an automation command.")
            submsg.setStyleSheet("color: #636366; font-size: 11px;")
            submsg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lay.addWidget(submsg)

            self.card_layout.addWidget(empty_box)

        self.card_layout.addStretch()
        count_text = f"{len(self._scripts)} script{'s' if len(self._scripts) != 1 else ''} configured"
        if len(self._scripts) > 1 and not filter_text:
            count_text += " • Drag cards to reorder"
        self.count_lbl.setText(count_text)

    def _on_reorder_cards(self, source_idx: int, target_idx: int):
        if 0 <= source_idx < len(self._scripts) and 0 <= target_idx < len(self._scripts):
            item = self._scripts.pop(source_idx)
            self._scripts.insert(target_idx, item)
            self._save_and_emit()
            self._populate_cards(self.search_input.text())

    def _on_filter_changed(self, text: str):
        self._populate_cards(text)

    def _save_and_emit(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"scripts": self._scripts}, f, indent=2)
        except Exception as e:
            print(f"Error saving scripts: {e}")

        self.scripts_updated.emit(self._scripts)

    def _on_add(self):
        dlg = ScriptEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_data = dlg.get_data()
            self._scripts.append(new_data)
            self._save_and_emit()
            self._populate_cards(self.search_input.text())

    def _on_edit_card(self, index: int):
        if 0 <= index < len(self._scripts):
            dlg = ScriptEditDialog(script=self._scripts[index], parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._scripts[index] = dlg.get_data()
                self._save_and_emit()
                self._populate_cards(self.search_input.text())

    def _on_delete_card(self, index: int):
        if 0 <= index < len(self._scripts):
            name = self._scripts[index].get("name", "this script")
            reply = QMessageBox.question(
                self,
                "Delete Script",
                f"Are you sure you want to delete '{name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._scripts.pop(index)
                self._save_and_emit()
                self._populate_cards(self.search_input.text())

    def _on_run_card(self, script: dict):
        success, msg = run_script(script)
        if success:
            QMessageBox.information(
                self,
                "Script Launched",
                f"Successfully launched '{script.get('name', 'Script')}'"
            )
        else:
            QMessageBox.critical(
                self,
                "Launch Error",
                f"Failed to execute '{script.get('name', 'Script')}':\n{msg}"
            )

    def showEvent(self, event):
        pause_hotkeys()
        super().showEvent(event)

    def closeEvent(self, event):
        resume_hotkeys()
        super().closeEvent(event)

    def reject(self):
        resume_hotkeys()
        super().reject()
