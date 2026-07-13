"""
Shared async event loop thread utility for the AI Desktop Assistant.

Provides a single background event loop that other modules can use to run
coroutines without creating their own one-shot event loops.
"""

import asyncio
import threading
from typing import Coroutine, Any


class AsyncRunner:
    """
    Dedicated event loop running on a background daemon thread.

    Other modules submit async tasks here instead of creating their own
    one-shot event loops, eliminating the fragile pattern of:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(coro)
    loop.close()
    """

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._started = False

    def _run_loop(self):
        """Run the event loop in the background thread."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start(self):
        """
        Start the background event loop thread.
        Call once during application startup.
        """
        if self._started:
            return
        self._thread.start()
        self._started = True

    def run_coro(self, coro: Coroutine) -> asyncio.Future:
        """
        Submit a coroutine to run on the background event loop.

        Args:
            coro: The coroutine to execute

        Returns:
            asyncio.Future: A future that will hold the result
        """
        if not self._started:
            raise RuntimeError("AsyncRunner must be started before submitting coroutines")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self):
        """
        Stop the background event loop and wait for thread to finish.
        Call during application shutdown.
        """
        if not self._started:
            return

        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5.0)
        self._started = False