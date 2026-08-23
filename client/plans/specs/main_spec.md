# main.py Specification

**Path**: `client/main.py`

## Description
Main entrypoint and lifecycle orchestrator for the Shadow Desktop Assistant.

## Orchestration Flow

1. **Single-Instance Mutex Guard**:
   - Creates a Windows named mutex `Local\ShadowAssistantSingleInstanceMutex` via `kernel32.CreateMutexW`.
   - Exits immediately if an existing instance is already running to avoid hotkey registration conflicts (Win32 Error 1409).
2. **Application Initialization**:
   - Configures high-DPI scaling and initializes `QApplication`.
   - Loads central `ClientConfig` with APPDATA and `.env` fallback.
3. **Component Instantiation**:
   - `AsyncRunner`: Dedicated asyncio background event loop.
   - `ApiClient`: Connection-pooled HTTP client.
   - `FloatingPopup` & `TranslationPopup`: User interface overlays.
   - `TrayApp`: System tray icon with full menus.
   - `NotificationListener`: Inbound HTTP server (:8080).
   - `ContextCollector`: Focus tracking service.
   - `Win32HotkeyManager`: Global hotkeys (`Alt+Q`, `Alt+A`, `Alt+1..N`).
4. **Signal Wiring**:
   - `hotkeys_changed` & `scripts_changed` $\rightarrow$ dynamic hotkey updates.
   - `open_scripts_menu_requested` $\rightarrow$ thread-safe popup script menu trigger.
   - `show_translation_requested` $\rightarrow$ cursor-tracking HUD display.
5. **Clean Shutdown Handling**:
   - Hooks `app.aboutToQuit` and `SIGINT` to gracefully stop hotkeys, close listener sockets, drain async tasks, and terminate runners.
