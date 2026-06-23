"""Stub API Client for Module 4.1 - will be replaced with real httpx-based client."""

class ApiClient:
    """Stub for Module 4.1 — will be replaced with real httpx-based client."""
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def chat(self, message: str, context: dict = None) -> str:
        return f"[Stub] Echo: {message}"

    def health_check(self) -> bool:
        return False  # No server yet