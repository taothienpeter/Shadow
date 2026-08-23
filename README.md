# Shadow — AI Desktop Assistant

A sleek, macOS / Apple-inspired AI-powered desktop assistant for Windows with screen context awareness, global hotkeys, automation script management, and n8n webhook integration.

## Features

- **Floating Conversational Bar**: Apple frosted glass UI that appears smoothly at your cursor (`Alt+Q`)
- **Global Hotkey Manager**: Fully customizable global keyboard shortcuts with key recording UI
- **Screen & App Context Awareness**: Instant multi-monitor screenshot capture + active window inspection sent to n8n (`Alt+A`)
- **Script & Automation Manager**: Quick launch cards for applications (`.exe`), Python scripts (`.py`), batch files (`.bat`/`.ps1`), and web URLs (`https://`)
- **Inbound Notification Listener**: Built-in HTTP server listening on Tailscale/LAN to receive real-time POST notifications from n8n workflows
- **System Tray Integration**: Background tray menu with server status, hotkey settings, notification muting & queue replay, script launcher, and restart controls

---

## Installation

1. **Prerequisites**:
   - Windows 10/11 (or Linux/macOS with X11)
   - Python 3.10+

2. **Setup**:
   ```bash
   # Clone the repository
   git clone <repository-url>
   cd shadow

   # Install dependencies
   pip install -r requirements.txt

   # Copy environment template
   copy .env.example .env    # Windows
   # or
   cp .env.example .env      # Linux/macOS
   ```

3. **Configure `.env`**:
   Edit `.env` and set your n8n webhook URL:
   ```ini
   N8N_WEBHOOK_URL=https://webhook.your-domain.com/webhook/assistant
   NOTIFICATION_PORT=8080
   TAILSCALE_IP=0.0.0.0
   ```

---

## Usage

1. **Run the Assistant**:
   ```bash
   python client/main.py
   ```

2. **Default Shortcuts**:
   - **`Alt+Q`**: Show / hide the floating assistant bar
   - **`Alt+A`**: Capture screen + active window context and send to n8n for analysis

   *(Hotkeys can be customized via the Tray Menu → Hotkeys → Change Hotkeys...)*

3. **Floating Bar Commands**:
   - Type any question or message and press **Enter** to chat with your n8n workflow
   - Type `/s <name>`, `/run <name>`, or `/open <name>` to quickly run an automation script
   - Type `/restart` or `/r` to immediately restart the application
   - Click **Summarize** or **Note** to run contextual actions

4. **System Tray Menu**:
   Right-click the Shadow tray icon to:
   - Toggle Server and test connectivity
   - Run, edit, and add automation scripts
   - View and customize global hotkeys
   - Mute/unmute notifications with automatic queue replay
   - Restart or quit the assistant

---

## Architecture & Integration

```text
               ┌────────────────────────────────────────────────────────┐
               │                     Shadow Client                      │
               │                                                        │
┌───────────┐  │  ┌──────────────┐     ┌──────────────┐                 │
│ User Keys │─┼─►│ HotkeyManager│────►│FloatingPopup │ (Qt UI)         │
└───────────┘  │  └──────────────┘     └──────┬───────┘                 │
               │                              │                         │
               │  ┌──────────────────────┐    │                         │
               │  │  ContextCollector    │◄───┘                         │
               │  │ (mss screen capture) │                              │
               │  └──────────┬───────────┘                              │
               │             │                                          │
               │  ┌──────────▼───────────┐     ┌─────────────────────┐  │
               │  │       ApiClient      │────►│  n8n Webhook / AI   │  │
               │  │ (httpx connection)   │     │ (Self-hosted flow)  │  │
               │  └──────────────────────┘     └──────────┬──────────┘  │
               │                                          │             │
               │  ┌──────────────────────┐                │ (HTTP POST) │
               │  │ NotificationListener │◄───────────────┘             │
               │  │   (HTTPServer)       │                              │
               │  └──────────┬───────────┘                              │
               │             ▼                                          │
               │  ┌──────────────────────┐                              │
               │  │       TrayApp        │ (System notifications)       │
               │  └──────────────────────┘                              │
               └────────────────────────────────────────────────────────┘
```