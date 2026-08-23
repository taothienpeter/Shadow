"""
Interactive Snipping Tool Overlay for AI Desktop Assistant.
Allows users to drag and select a rectangular region of the screen for AI vision analysis.
"""

from typing import Optional
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QGuiApplication
from PyQt6.QtWidgets import QWidget, QApplication

from client.core.screenshot import ScreenshotCapture


class SnippingTool(QWidget):
    """
    Transparent fullscreen overlay that allows dragging to select a screen region.
    Emits `snippet_captured(bytes, dict)` when an area is selected.
    """

    snippet_captured = pyqtSignal(bytes, dict)  # (jpeg_bytes, metadata)
    snippet_cancelled = pyqtSignal()

    def __init__(self, screenshot_capture: Optional[ScreenshotCapture] = None, parent=None):
        super().__init__(parent)
        self._screenshot = screenshot_capture or ScreenshotCapture()
        self._begin_pos = QPoint()
        self._end_pos = QPoint()
        self._is_selecting = False
        self._virtual_geometry = QRect()

        # Frameless, on-top, tool window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def start_selection(self):
        """Show fullscreen across all combined monitors and start selection."""
        # Calculate bounding box of all connected screens
        screens = QGuiApplication.screens()
        if not screens:
            self.snippet_cancelled.emit()
            return

        combined_rect = screens[0].geometry()
        for s in screens[1:]:
            combined_rect = combined_rect.united(s.geometry())

        self._virtual_geometry = combined_rect
        self.setGeometry(combined_rect)
        self._begin_pos = QPoint()
        self._end_pos = QPoint()
        self._is_selecting = False

        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event):
        """Cancel selection if Escape is pressed."""
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """Start rectangular selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._begin_pos = event.globalPosition().toPoint()
            self._end_pos = self._begin_pos
            self._is_selecting = True
            self.update()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._cancel()
            event.accept()

    def mouseMoveEvent(self, event):
        """Update selection rectangle while dragging."""
        if self._is_selecting:
            self._end_pos = event.globalPosition().toPoint()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event):
        """Finish selection and crop area."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_selecting:
            self._is_selecting = False
            self._end_pos = event.globalPosition().toPoint()
            self.hide()

            rect = self._get_normalized_rect(self._begin_pos, self._end_pos)
            # Check for minimal valid dimension (at least 10x10 px)
            if rect.width() >= 10 and rect.height() >= 10:
                self._process_selection(rect)
            else:
                self.snippet_cancelled.emit()
            event.accept()

    def _cancel(self):
        self._is_selecting = False
        self.hide()
        self.snippet_cancelled.emit()

    def _get_normalized_rect(self, p1: QPoint, p2: QPoint) -> QRect:
        """Return a normalized QRect from two arbitrary points."""
        left = min(p1.x(), p2.x())
        top = min(p1.y(), p2.y())
        width = abs(p1.x() - p2.x())
        height = abs(p1.y() - p2.y())
        return QRect(left, top, width, height)

    def _process_selection(self, rect: QRect):
        """Capture the selected screen region and emit signal."""
        try:
            x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
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
            print(f"Error capturing snippet region: {e}")
            self.snippet_cancelled.emit()

    def paintEvent(self, event):
        """Draw dimmed background, clear cutout, neon selection border, and dimension tag."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Global overlay rect in widget local coordinates
        local_rect = self.rect()

        # Dimmed backdrop
        dim_color = QColor(0, 0, 0, 110)

        if not self._is_selecting or self._begin_pos == self._end_pos:
            painter.fillRect(local_rect, dim_color)
            # Helper text at center
            painter.setPen(QColor(255, 255, 255, 200))
            painter.setFont(QFont("Segoe UI", 13, QFont.Weight.Medium))
            painter.drawText(
                local_rect,
                Qt.AlignmentFlag.AlignCenter,
                "Drag to select an area to analyze  •  Press Esc or Right Click to cancel",
            )
            return

        # Calculate local selection rect
        global_sel_rect = self._get_normalized_rect(self._begin_pos, self._end_pos)
        # Map global coordinate to local widget coordinate
        local_top_left = self.mapFromGlobal(global_sel_rect.topLeft())
        local_sel_rect = QRect(local_top_left, global_sel_rect.size())

        # 1. Fill 4 dark regions around the selection (punch-hole cutout)
        # Top
        painter.fillRect(0, 0, local_rect.width(), local_sel_rect.top(), dim_color)
        # Bottom
        painter.fillRect(
            0,
            local_sel_rect.bottom() + 1,
            local_rect.width(),
            local_rect.height() - local_sel_rect.bottom() - 1,
            dim_color,
        )
        # Left
        painter.fillRect(
            0,
            local_sel_rect.top(),
            local_sel_rect.left(),
            local_sel_rect.height(),
            dim_color,
        )
        # Right
        painter.fillRect(
            local_sel_rect.right() + 1,
            local_sel_rect.top(),
            local_rect.width() - local_sel_rect.right() - 1,
            local_sel_rect.height(),
            dim_color,
        )

        # 2. Glowing Neon Border
        border_pen = QPen(QColor(10, 132, 255), 2, Qt.PenStyle.SolidLine)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(local_sel_rect)

        # 3. Corner Accent Handles
        corner_color = QColor(255, 255, 255)
        corner_len = 8
        c_pen = QPen(corner_color, 3)
        painter.setPen(c_pen)
        # Top-Left
        painter.drawLine(local_sel_rect.topLeft(), local_sel_rect.topLeft() + QPoint(corner_len, 0))
        painter.drawLine(local_sel_rect.topLeft(), local_sel_rect.topLeft() + QPoint(0, corner_len))
        # Top-Right
        painter.drawLine(local_sel_rect.topRight(), local_sel_rect.topRight() + QPoint(-corner_len, 0))
        painter.drawLine(local_sel_rect.topRight(), local_sel_rect.topRight() + QPoint(0, corner_len))
        # Bottom-Left
        painter.drawLine(local_sel_rect.bottomLeft(), local_sel_rect.bottomLeft() + QPoint(corner_len, 0))
        painter.drawLine(local_sel_rect.bottomLeft(), local_sel_rect.bottomLeft() + QPoint(0, -corner_len))
        # Bottom-Right
        painter.drawLine(local_sel_rect.bottomRight(), local_sel_rect.bottomRight() + QPoint(-corner_len, 0))
        painter.drawLine(local_sel_rect.bottomRight(), local_sel_rect.bottomRight() + QPoint(0, -corner_len))

        # 4. Dimension Badge (e.g. "640 × 360 px")
        dim_text = f"{global_sel_rect.width()} × {global_sel_rect.height()} px"
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        badge_w = 110
        badge_h = 24
        badge_x = local_sel_rect.left()
        badge_y = (
            local_sel_rect.top() - badge_h - 6
            if local_sel_rect.top() >= badge_h + 10
            else local_sel_rect.bottom() + 6
        )

        badge_rect = QRect(badge_x, badge_y, badge_w, badge_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(28, 28, 30, 220)))
        painter.drawRoundedRect(badge_rect, 6, 6)

        painter.setPen(QColor(255, 255, 255, 230))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, dim_text)
