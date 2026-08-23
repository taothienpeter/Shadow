# context_collector.py Specification

**Path**: `client/core/context_collector.py`

## Description
Context collector module for Shadow Assistant.
Tracks user focus across active desktop applications and gathers context (active window title, process name, recent apps history, and full screen snapshot) for multimodal AI analysis.

## Classes

### `ContextCollector(QObject)`

#### Signals
- `context_ready = pyqtSignal(dict)`: Emitted when context collection and API response complete.
- `context_error = pyqtSignal(str)`: Emitted if context analysis fails.
- `analysis_started = pyqtSignal()`: Emitted when context gathering begins.

#### Features
- **Active Window Tracker**: 300ms polling timer tracking foreground HWND via `win32gui` and `psutil`.
- **Self-Window Filtering**: Automatically filters out Shadow Assistant's own PID (`os.getpid()`) and window titles to prevent feedback loops.
- **Recent Apps History**: Maintains an in-memory chronological list of recently focused applications.
- **`collect_context_now()`**: Captures full-screen snapshot and active app metadata, sending to n8n via `ApiClient.ask_respond()`.
