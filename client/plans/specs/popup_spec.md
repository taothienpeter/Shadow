# popup.py Specification

**Path**: `client/ui/popup.py`

## Description
Ultra-sleek Apple-inspired Floating Command & Chat Bar with multimodal vision, note capture, and contextual AI workflows.

## Classes

### `FloatingPopup(QDialog)`
Main conversational and command interface.

#### Signals
- `toggle_requested = pyqtSignal()`
- `open_scripts_menu_requested = pyqtSignal()`
- `set_context_text_requested = pyqtSignal(str)`
- `set_input_text_requested = pyqtSignal(str)`
- `clear_input_requested = pyqtSignal()`
- `response_received = pyqtSignal(dict)`
- `script_executed = pyqtSignal(dict)`
- `scripts_changed = pyqtSignal(list)`
- `show_translation_requested = pyqtSignal(str, QPoint)`

#### Features
1. **Screen-Aware Multimodal Chat**:
   - Camera button toggle for switching between Full-screen capture and Privacy Snippet crop.
   - Thumbnail preview badge with ✕ clear button.
2. **Note Mode Toggle (`Note: [ ] / [✓]`)**:
   - Switches input mode to dedicated personal notes pipeline (`action: "note"`).
   - Prevents auto-sending screenshots unless camera snippet is explicitly attached.
3. **Quick Action Context Chips**:
   - `translate`: Triggers snippet crop and sends payload for translation, displaying result in `TranslationPopup` HUD.
   - `explain`: Explains on-screen context.
   - `action`: Extracts and executes action items from screen.
4. **Scripts Dropdown Menu (`Alt + A`)**:
   - Quick launcher for custom system scripts and webhooks.
5. **Win32 Focus Stealing Workaround**:
   - `_force_focus()` using `SendInput(VK_MENU)` and `SPI_SETFOREGROUNDLOCKTIMEOUT` to reliably focus popup on global hotkey trigger.
