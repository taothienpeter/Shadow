"""Stub Chat Widget for Module 3.2 - placeholder chat area."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt


class ChatWidget(QWidget):
    """Stub for Module 3.2 — placeholder chat area."""
    def __init__(self, api_client=None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.label = QLabel("Chat area — ChatWidget placeholder\n(Module 3.2)")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

    def add_user_message(self, text: str) -> None:
        """Add a user message to the chat area."""
        self.label.setText(f"User: {text}")

    def add_ai_message(self, text: str) -> None:
        """Add an AI message to the chat area."""
        self.label.setText(f"AI: {text}")

    def clear(self) -> None:
        """Clear all messages from the chat area."""
        self.label.setText("")