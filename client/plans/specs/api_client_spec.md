# api_client.py Specification

**Path**: `client/core/api_client.py`

## Description
Asynchronous HTTP API Client for n8n Webhook communication.
Features connection pooling, exponential backoff retries, and comprehensive error hierarchy.

## Classes

### `ApiClient`

#### Error Hierarchy
- `ApiClientError(Exception)`: Base API exception.
  - `ApiConnectionError`: Network / connectivity failures.
  - `ApiTimeoutError`: HTTP timeout.
  - `ApiServerError`: 5xx server-side response error.

#### Methods
- `__init__(webhook_url: str, api_key: str = "", timeout: float = 60.0)`
- `ask_respond(payload: dict) -> dict | None`: Sends asynchronous POST request to n8n webhook with automatic JSON serialization, retry on 5xx server errors (with exponential backoff), and returns response JSON.
- `close()`: Closes underlying `httpx.AsyncClient` connection pool gracefully.
