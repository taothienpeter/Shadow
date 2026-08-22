"""
Shared async event loop thread utility for the AI Desktop Assistant.

Provides a single background event loop that other modules can use to run
coroutines without creating their own one-shot event loops.
"""

import asyncio
import concurrent.futures
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

    def run_coro(self, coro: Coroutine) -> concurrent.futures.Future:
        """
        Submit a coroutine to run on the background event loop.

        Args:
            coro: The coroutine to execute

        Returns:
            concurrent.futures.Future: A future that will hold the result
        """
        if not self._started:
            raise RuntimeError("AsyncRunner must be started before submitting coroutines")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self):
        """
        Stop the background event loop, cancel tasks, and close loop cleanly.
        Call during application shutdown.
        """
        if not self._started:
            return

        def _cancel_all_tasks():
            for task in asyncio.all_tasks(self._loop):
                task.cancel()
            self._loop.stop()

        if self._loop.is_running():
            self._loop.call_soon_threadsafe(_cancel_all_tasks)

        self._thread.join(timeout=3.0)

        if not self._loop.is_closed():
            try:
                self._loop.close()
            except Exception:
                pass

        self._started = False