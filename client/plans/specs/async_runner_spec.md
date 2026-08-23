# async_runner.py Specification

**Path**: `client/core/async_runner.py`

## Description
Thread-safe Asynchronous Runner module for executing Python `asyncio` coroutines alongside the synchronous Qt main event loop.

## Classes

### `AsyncRunner`
- Runs a dedicated background `threading.Thread` with its own `asyncio.new_event_loop()`.
- `run_coro(coro: Coroutine) -> concurrent.futures.Future`: Dispatches coroutine to the background loop without blocking Qt GUI, returning a `Future` for result querying.
- `stop()`: Cancels all pending tasks, stops the event loop, and joins the worker thread cleanly.
