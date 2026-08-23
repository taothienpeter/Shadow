"""
Screenshot Settings Dialog for AI Desktop Assistant.
Allows users to configure screen capture quality, max resolution, monitor targets, and recent tasks history.
"""

import json
from pathlib import Path
from typing import Dict, Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QSpinBox, QFrame
)


class ScreenshotSettingsDialog(QDialog):
    """Modern dark-themed dialog for screen capture configuration."""

    settings_updated = pyqtSignal(dict)

    DEFAULT_SETTINGS: Dict[str, Any] = {
        "quality": 70,
        "max_dimension": 1920,
        "monitor_index": 0,
        "recent_apps_limit": 4,
    }

    def __init__(self, config_path: Path, current_settings: Dict[str, Any] = None, parent=None):
        super().__init__(parent)
        self._config_path = config_path
        self._settings = dict(self.DEFAULT_SETTINGS)
        if current_settings:
            self._settings.update(current_settings)

        self.setWindowTitle("Screen Capture Settings")
        self.setFixedSize(460, 420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._setup_ui()
        self._apply_styles()
        self._load_values()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header_lbl = QLabel("Screen Capture Settings")
        header_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        header_lbl.setObjectName("dialogHeader")
        layout.addWidget(header_lbl)

        sub_lbl = QLabel("Customize capture resolution, compression quality, and task tracking.")
        sub_lbl.setFont(QFont("Segoe UI", 10))
        sub_lbl.setObjectName("dialogSubHeader")
        layout.addWidget(sub_lbl)

        # Container Frame
        form_frame = QFrame()
        form_frame.setObjectName("formFrame")
        form_layout = QVBoxLayout(form_frame)
        form_layout.setSpacing(14)
        form_layout.setContentsMargins(16, 16, 16, 16)

        # 1. Quality Slider
        q_row = QHBoxLayout()
        q_label = QLabel("Image Quality (JPEG):")
        q_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self.q_val_label = QLabel("70% (Balanced)")
        self.q_val_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.q_val_label.setStyleSheet("color: #0A84FF;")
        q_row.addWidget(q_label)
        q_row.addStretch()
        q_row.addWidget(self.q_val_label)
        form_layout.addLayout(q_row)

        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(30, 95)
        self.quality_slider.setSingleStep(5)
        self.quality_slider.valueChanged.connect(self._on_quality_slider_changed)
        form_layout.addWidget(self.quality_slider)

        # 2. Max Dimension Dropdown
        dim_row = QHBoxLayout()
        dim_label = QLabel("Max Image Dimension:")
        dim_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        dim_row.addWidget(dim_label)
        dim_row.addStretch()

        self.dim_combo = QComboBox()
        self.dim_combo.addItem("Full HD — 1080p (1920 px) [Recommended]", 1920)
        self.dim_combo.addItem("2K QHD (2560 px)", 2560)
        self.dim_combo.addItem("4K UHD (3840 px)", 3840)
        self.dim_combo.addItem("720p HD — Fast (1280 px)", 1280)
        self.dim_combo.addItem("Original Resolution (No Resize)", 0)
        self.dim_combo.setFixedWidth(240)
        dim_row.addWidget(self.dim_combo)
        form_layout.addLayout(dim_row)

        # 3. Monitor Selection
        mon_row = QHBoxLayout()
        mon_label = QLabel("Capture Display Target:")
        mon_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        mon_row.addWidget(mon_label)
        mon_row.addStretch()

        self.mon_combo = QComboBox()
        self.mon_combo.addItem("All Monitors (Virtual Desktop)", 0)
        screens = QGuiApplication.screens()
        for idx, s in enumerate(screens):
            name = s.name() or f"Screen {idx + 1}"
            geo = s.geometry()
            self.mon_combo.addItem(f"{name} ({geo.width()}x{geo.height()})", idx + 1)
        self.mon_combo.setFixedWidth(240)
        mon_row.addWidget(self.mon_combo)
        form_layout.addLayout(mon_row)

        # 4. Recent Apps Limit
        apps_row = QHBoxLayout()
        apps_label = QLabel("Recent Tasks History Buffer:")
        apps_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        apps_row.addWidget(apps_label)
        apps_row.addStretch()

        self.apps_spin = QSpinBox()
        self.apps_spin.setRange(1, 8)
        self.apps_spin.setSuffix(" apps")
        self.apps_spin.setFixedWidth(100)
        apps_row.addWidget(self.apps_spin)
        form_layout.addLayout(apps_row)

        layout.addWidget(form_frame)
        layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.reset_btn = QPushButton("Reset Defaults")
        self.reset_btn.setObjectName("secondaryBtn")
        self.reset_btn.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(self.reset_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setObjectName("primaryBtn")
        self.save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def _on_quality_slider_changed(self, val: int):
        if val >= 85:
            tag = "High Quality"
        elif val >= 65:
            tag = "Balanced"
        else:
            tag = "Performance"
        self.q_val_label.setText(f"{val}% ({tag})")

    def _load_values(self):
        # Quality
        q = int(self._settings.get("quality", 70))
        self.quality_slider.setValue(q)
        self._on_quality_slider_changed(q)

        # Dimension
        dim = int(self._settings.get("max_dimension", 1920))
        idx = self.dim_combo.findData(dim)
        if idx >= 0:
            self.dim_combo.setCurrentIndex(idx)

        # Monitor
        mon = int(self._settings.get("monitor_index", 0))
        mon_idx = self.mon_combo.findData(mon)
        if mon_idx >= 0:
            self.mon_combo.setCurrentIndex(mon_idx)

        # Recent Apps Limit
        limit = int(self._settings.get("recent_apps_limit", 4))
        self.apps_spin.setValue(limit)

    def _reset_defaults(self):
        self._settings = dict(self.DEFAULT_SETTINGS)
        self._load_values()

    def _save_settings(self):
        new_settings = {
            "quality": self.quality_slider.value(),
            "max_dimension": self.dim_combo.currentData(),
            "monitor_index": self.mon_combo.currentData(),
            "recent_apps_limit": self.apps_spin.value(),
        }

        self._settings = new_settings
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(new_settings, f, indent=2)
        except Exception as e:
            print(f"Error saving screenshot settings: {e}")

        self.settings_updated.emit(new_settings)
        self.accept()

    def get_settings(self) -> Dict[str, Any]:
        return dict(self._settings)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: #1C1C1E;
                color: #FFFFFF;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel#dialogHeader {
                color: #FFFFFF;
            }
            QLabel#dialogSubHeader {
                color: #8E8E93;
            }
            QFrame#formFrame {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QLabel {
                color: #E5E5EA;
            }
            QComboBox, QSpinBox {
                background: rgba(255, 255, 255, 0.08);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QComboBox:hover, QSpinBox:hover {
                border-color: rgba(10, 132, 255, 0.50);
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background: #2C2C2E;
                color: #FFFFFF;
                selection-background-color: #0A84FF;
                border-radius: 6px;
                padding: 4px;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: rgba(255, 255, 255, 0.15);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #0A84FF;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: none;
                width: 16px;
                margin-top: -6px;
                margin-bottom: -6px;
                border-radius: 8px;
            }
            QPushButton#primaryBtn {
                background: #0A84FF;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 7px 16px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#primaryBtn:hover {
                background: #0071E3;
            }
            QPushButton#secondaryBtn {
                background: rgba(255, 255, 255, 0.08);
                color: #E5E5EA;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                padding: 7px 14px;
                font-size: 12px;
            }
            QPushButton#secondaryBtn:hover {
                background: rgba(255, 255, 255, 0.14);
            }
        """)
