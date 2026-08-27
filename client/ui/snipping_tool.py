"""
Interactive Snipping Tool Overlay for AI Desktop Assistant.
Allows users to drag and select a rectangular region across single or multi-monitor setups
with per-screen DPI awareness and sub-pixel precision.
"""

from typing import List, Optional
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal, QBuffer, QIODevice
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QGuiApplication, QScreen, QCursor
)
from PyQt6.QtWidgets import QWidget

from client.core.screenshot import ScreenshotCapture


class ScreenOverlayWidget(QWidget):
    """Transparent overlay dedicated to a single QScreen to guarantee 100% native DPI rendering."""

    def __init__(self, screen: QScreen, controller: "SnippingTool"):
        super().__init__()
        self.screen = screen
        self.controller = controller

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.controller.cancel_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.on_mouse_press(event.globalPosition().toPoint())
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.controller.cancel_selection()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.controller.is_selecting():
            self.controller.on_mouse_move(event.globalPosition().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.controller.is_selecting():
            self.controller.on_mouse_release(event.globalPosition().toPoint())
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        screen_geo = self.screen.geometry()
        local_rect = self.rect()
        dim_color = QColor(0, 0, 0, 115)

        global_sel_rect = self.controller.get_global_selection_rect()

        if not self.controller.is_selecting() or global_sel_rect.isNull() or global_sel_rect.width() == 0:
            painter.fillRect(local_rect, dim_color)
            # Show helper text on the primary screen or screen containing cursor
            cursor_pos = QCursor.pos()
            if screen_geo.contains(cursor_pos):
                painter.setPen(QColor(255, 255, 255, 210))
                painter.setFont(QFont("Segoe UI", 13, QFont.Weight.Medium))
                painter.drawText(
                    local_rect,
                    Qt.AlignmentFlag.AlignCenter,
                    "Drag to select an area  •  Press Esc or Right Click to cancel",
                )
            return

        # Calculate selection on this screen
        sel_in_screen = global_sel_rect.intersected(screen_geo)

        if sel_in_screen.isEmpty():
            painter.fillRect(local_rect, dim_color)
            return

        # Local coordinates within this screen
        local_sel = QRect(
            sel_in_screen.x() - screen_geo.x(),
            sel_in_screen.y() - screen_geo.y(),
            sel_in_screen.width(),
            sel_in_screen.height(),
        )

        # 1. Fill 4 punch-hole dark regions around selection
        # Top
        painter.fillRect(0, 0, local_rect.width(), local_sel.top(), dim_color)
        # Bottom
        painter.fillRect(
            0,
            local_sel.bottom() + 1,
            local_rect.width(),
            local_rect.height() - local_sel.bottom() - 1,
            dim_color,
        )
        # Left
        painter.fillRect(
            0,
            local_sel.top(),
            local_sel.left(),
            local_sel.height(),
            dim_color,
        )
        # Right
        painter.fillRect(
            local_sel.right() + 1,
            local_sel.top(),
            local_rect.width() - local_sel.right() - 1,
            local_sel.height(),
            dim_color,
        )

        # 2. Glowing Neon Blue Border
        border_pen = QPen(QColor(10, 132, 255), 2, Qt.PenStyle.SolidLine)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(local_sel)

        # 3. Corner Accent Handles
        corner_color = QColor(255, 255, 255)
        corner_len = 8
        c_pen = QPen(corner_color, 3)
        painter.setPen(c_pen)

        painter.drawLine(local_sel.topLeft(), local_sel.topLeft() + QPoint(corner_len, 0))
        painter.drawLine(local_sel.topLeft(), local_sel.topLeft() + QPoint(0, corner_len))

        painter.drawLine(local_sel.topRight(), local_sel.topRight() + QPoint(-corner_len, 0))
        painter.drawLine(local_sel.topRight(), local_sel.topRight() + QPoint(0, corner_len))

        painter.drawLine(local_sel.bottomLeft(), local_sel.bottomLeft() + QPoint(corner_len, 0))
        painter.drawLine(local_sel.bottomLeft(), local_sel.bottomLeft() + QPoint(0, -corner_len))

        painter.drawLine(local_sel.bottomRight(), local_sel.bottomRight() + QPoint(-corner_len, 0))
        painter.drawLine(local_sel.bottomRight(), local_sel.bottomRight() + QPoint(0, -corner_len))

        # 4. Dimension Badge (Draw on screen containing top-left of selection)
        if screen_geo.contains(global_sel_rect.topLeft()):
            dim_text = f"{global_sel_rect.width()} × {global_sel_rect.height()} px"
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            badge_w = 110
            badge_h = 24
            badge_x = local_sel.left()
            badge_y = (
                local_sel.top() - badge_h - 6
                if local_sel.top() >= badge_h + 10
                else local_sel.bottom() + 6
            )

            badge_rect = QRect(badge_x, badge_y, badge_w, badge_h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(28, 28, 30, 225)))
            painter.drawRoundedRect(badge_rect, 6, 6)

            painter.setPen(QColor(255, 255, 255, 235))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, dim_text)


class SnippingTool(QWidget):
    """
    Multi-monitor Snipping Tool Controller.
    Creates and orchestrates per-screen overlays for zero-offset, multi-DPI capture.
    """

    snippet_captured = pyqtSignal(bytes, dict)  # (jpeg_bytes, metadata)
    snippet_cancelled = pyqtSignal()

    def __init__(self, screenshot_capture: Optional[ScreenshotCapture] = None, parent=None):
        super().__init__(parent)
        self._screenshot = screenshot_capture or ScreenshotCapture()
        self._begin_pos = QPoint()
        self._end_pos = QPoint()
        self._is_selecting = False
        self._overlays: List[ScreenOverlayWidget] = []

        # Hidden root widget
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(0, 0)

    def start_selection(self):
        """Initialize overlays for all screens and start selection."""
        screens = QGuiApplication.screens()
        if not screens:
            self.snippet_cancelled.emit()
            return

        self._cleanup_overlays()
        self._begin_pos = QPoint()
        self._end_pos = QPoint()
        self._is_selecting = False

        for s in screens:
            overlay = ScreenOverlayWidget(s, self)
            overlay.show()
            overlay.raise_()
            overlay.activateWindow()
            self._overlays.append(overlay)

    def is_selecting(self) -> bool:
        return self._is_selecting

    def get_global_selection_rect(self) -> QRect:
        if not self._is_selecting or self._begin_pos == self._end_pos:
            return QRect()
        return self._get_normalized_rect(self._begin_pos, self._end_pos)

    def on_mouse_press(self, global_pos: QPoint):
        self._begin_pos = global_pos
        self._end_pos = global_pos
        self._is_selecting = True
        self._update_all_overlays()

    def on_mouse_move(self, global_pos: QPoint):
        self._end_pos = global_pos
        self._update_all_overlays()

    def on_mouse_release(self, global_pos: QPoint):
        self._is_selecting = False
        self._end_pos = global_pos
        rect = self._get_normalized_rect(self._begin_pos, self._end_pos)

        self._cleanup_overlays()

        if rect.width() >= 10 and rect.height() >= 10:
            self._process_selection(rect)
        else:
            self.snippet_cancelled.emit()

    def cancel_selection(self):
        self._is_selecting = False
        self._cleanup_overlays()
        self.snippet_cancelled.emit()

    def _cleanup_overlays(self):
        for o in self._overlays:
            try:
                o.hide()
                o.close()
                o.deleteLater()
            except Exception:
                pass
        self._overlays.clear()

    def _update_all_overlays(self):
        for o in self._overlays:
            o.update()

    def _get_normalized_rect(self, p1: QPoint, p2: QPoint) -> QRect:
        left = min(p1.x(), p2.x())
        top = min(p1.y(), p2.y())
        width = abs(p1.x() - p2.x())
        height = abs(p1.y() - p2.y())
        return QRect(left, top, width, height)

    def _process_selection(self, rect: QRect):
        """Capture the selected screen region accurately via native QScreen grab."""
        try:
            x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()

            # Target screen containing center of selection
            target_screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()

            if target_screen:
                geo = target_screen.geometry()
                local_x = max(0, x - geo.x())
                local_y = max(0, y - geo.y())
                local_w = min(w, geo.width() - local_x)
                local_h = min(h, geo.height() - local_y)

                pixmap = target_screen.grabWindow(0, local_x, local_y, local_w, local_h)
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                pixmap.save(buffer, "JPEG", self._screenshot.quality)
                jpeg_bytes = bytes(buffer.data())
            else:
                jpeg_bytes = self._screenshot.capture_region(x, y, w, h)

            metadata = {
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "dimension": f"{w}x{h}",
                "mode": "snippet",
            }
            self.snippet_captured.emit(jpeg_bytes, metadata)
        except Exception as e:
            print(f"Error processing snippet: {e}")
            self.snippet_cancelled.emit()
