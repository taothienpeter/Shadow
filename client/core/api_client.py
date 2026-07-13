"""Async HTTP client for communication with n8n webhook.

Uses httpx.AsyncClient as a singleton with connection pooling.
Per-endpoint timeouts, 4-level error hierarchy, and inline retry
for 5xx errors.
"""

import asyncio
import functools
from datetime import datetime, timezone
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class ApiError(Exception):
    """Base exception for all API client errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ApiConnectionError(ApiError):
    """Raised when the server cannot be reached."""


class ApiTimeoutError(ApiError):
    """Raised when the server is too slow to respond."""


class ApiServerError(ApiError):
    """Raised on 5xx responses."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message, status_code)


class ApiClientError(ApiError):
    """Raised on 4xx responses (except 429)."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message, status_code)


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

def _retry_on_server_error(max_retries: int = 2, base_delay: float = 0.5):
    """Retry on 5xx and connection errors with exponential backoff."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc: ApiError | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except ApiServerError as e:
                    last_exc = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                    else:
                        raise
                except ApiConnectionError as e:
                    last_exc = e
                    if attempt < 1:
                        delay = base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                    else:
                        raise
            raise last_exc  # should not reach, but safety net

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# ApiClient
# ---------------------------------------------------------------------------

class ApiClient:
    """Async HTTP client with connection pooling for n8n webhook communication."""

    # Timeout profiles per endpoint family
    _DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

    def __init__(
        self,
        webhook_url: str,
        timeout: float = 30.0,
        api_key: str | None = None,
    ):
        self._webhook_url = webhook_url.rstrip("/")
        self._default_timeout = timeout
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    # -- lifecycle ---------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._webhook_url,
                timeout=self._default_timeout,
                headers=headers or None,
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                    keepalive_expiry=30.0,
                ),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "ApiClient":
        await self._get_client()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    # -- internal helpers --------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str = "",
        *,
        timeout: httpx.Timeout | float | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        client = await self._get_client()
        try:
            response = await client.request(
                method, path, timeout=timeout, **kwargs
            )
        except httpx.ConnectError as exc:
            raise ApiConnectionError(
                f"Cannot connect to webhook at {self._webhook_url}. Is it running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ApiTimeoutError(
                "Webhook is slow to respond. Please try again."
            ) from exc

        if response.is_server_error:
            raise ApiServerError(
                f"Webhook error ({response.status_code}). Please retry.",
                response.status_code,
            )
        if response.is_client_error:
            raise ApiClientError(
                f"Request error ({response.status_code}): {response.text}",
                response.status_code,
            )
        return response

    # -- public API: ask-respond ------------------------------------------

    @_retry_on_server_error(max_retries=2, base_delay=0.5)
    async def ask_respond(self, payload: dict, timeout: float = 60.0) -> dict:
        """POST to the n8n webhook URL, wait for response, return parsed JSON.

        Args:
            payload: JSON-serializable dict to send as request body
            timeout: Request timeout in seconds (default 60s for n8n workflows)

        Returns:
            Parsed JSON response dict

        Raises:
            ApiConnectionError: If the server cannot be reached.
            ApiTimeoutError: If the request times out.
            ApiServerError: On 5xx responses (after automatic retries).
            ApiClientError: On 4xx responses.
        """
        resp = await self._request(
            "POST",
            "",  # Empty path since base_url is the webhook URL
            json=payload,
            timeout=timeout,
        )
        return resp.json()

    @staticmethod
    def extract_response_text(response: dict) -> str:
        """Extract meaningful display text from an n8n response dict.

        Tries common response field names in priority order.
        Falls back to the string representation of the entire dict.

        Args:
            response: The JSON response dict from the n8n webhook.

        Returns:
            A human-readable string extracted from the response.
        """
        for key in ("response", "message", "text", "answer", "reply", "content", "error"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        # If the response wraps data in a nested structure, try common patterns
        if "data" in response and isinstance(response["data"], dict):
            nested = response["data"]
            for key in ("response", "message", "text", "answer", "reply", "content"):
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        # Fallback to string representation
        return str(response)

    async def send_message(
        self,
        text: str,
        timeout: float = 60.0,
    ) -> dict:
        """Send a chat message to the n8n webhook with structured metadata.

        Builds a payload with action, timestamp, message, and source fields,
        then POSTs it to the webhook and returns the parsed JSON response.

        Args:
            text: The message text to send.
            timeout: Request timeout in seconds (default 60s).

        Returns:
            Parsed JSON response dict from the webhook.

        Raises:
            ApiConnectionError: If the server cannot be reached.
            ApiTimeoutError: If the request times out.
            ApiServerError: On 5xx responses (after automatic retries).
            ApiClientError: On 4xx responses.
        """
        payload = {
            "action": "chat",
            "message": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "desktop_assistant",
        }

        return await self.ask_respond(payload, timeout=timeout)