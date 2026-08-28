#!/usr/bin/env python3
"""
Comprehensive test script for AI Desktop Assistant connectivity.
Tests both webhook API (client -> n8n) and notification listener (n8n -> client)
with diagnostic information to help debug Tailscale connectivity issues.
"""

import asyncio
import sys
import os
import json
import time
import socket
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from client.core.api_client import ApiClient
from client.core.notification_listener import NotificationListener
from client.config import ClientConfig
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
import threading


def get_local_ips():
    """Get all local IP addresses for debugging."""
    ips = []
    try:
        # Get hostname
        hostname = socket.gethostname()
        ips.append(f"Hostname: {hostname}")

        # Get all IP addresses
        addr_info = socket.getaddrinfo(hostname, None)
        for info in addr_info:
            ip = info[4][0]
            if ip not in ips and not ip.startswith('fe80'):  # Skip link-local IPv6
                ips.append(f"IP: {ip}")
    except Exception as e:
        ips.append(f"Error getting IPs: {e}")

    return ips


def print_diagnostics(config):
    """Print diagnostic information for troubleshooting."""
    print("🔍 Connection Diagnostics")
    print("=" * 60)
    print("📋 Configuration:")
    print(f"  Tailscale IP from .env: {config.tailscale_ip}")
    print(f"  Notification Port: {config.notification_port}")
    print(f"  N8N Webhook URL: {config.n8n_webhook_url}")
    print(f"  N8N Auth Token Set: {'Yes' if config.n8n_auth_token and config.n8n_auth_token != '' else 'No'}")
    print(f"  N8N Notification URL (what n8n should use): {config.n8n_notification_url or '(not set)'}")
    print()

    # Show local IPs for debugging
    print("🌐 Local Network Interfaces:")
    for ip_info in get_local_ips():
        print(f"  {ip_info}")
    print()

    # Determine what IP to listen on and what n8n should use
    listen_host = config.tailscale_ip if config.tailscale_ip != "0.0.0.0" else "0.0.0.0"
    bind_display = config.tailscale_ip if config.tailscale_ip != "0.0.0.0" else "0.0.0.0 (all interfaces)"

    print(f"🎯 Listener Configuration:")
    print(f"  Binding to: {bind_display}:{config.notification_port}")
    print(f"  n8n should send to: http://{config.tailscale_ip}:{config.notification_port}/notification")
    print()


def test_port_availability(host, port):
    """Test if we can bind to the specified port."""
    print("🔧 Testing Port Availability:")
    try:
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.settimeout(2)
        test_host = host if host != "0.0.0.0" else "127.0.0.1"
        result = test_socket.connect_ex((test_host, port))
        test_socket.close()
        if result == 0:
            print(f"  ⚠️  Port {port} appears to be already in use!")
            return False
        else:
            print(f"  ✅ Port {port} is available")
            return True
    except Exception as e:
        print(f"  ℹ️  Port check skipped: {e}")
        return True


async def test_webhook_api(test_id: str = "test-cli"):
    """Test connection to the webhook API (Client -> n8n)."""
    print("- Testing Webhook API (Client -> n8n)")

    config = ClientConfig()
    print(f"  Testing connection to webhook: {config.n8n_webhook_url}")

    api_client = ApiClient(
        webhook_url=config.n8n_webhook_url,
        api_key=config.n8n_api_key,
    )

    try:
        listener_ip = config.tailscale_ip
        listener_port = config.notification_port
        test_data = {
            "action": "test",
            "test_id": test_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "callback_url": f"http://{listener_ip}:{listener_port}/notification",
            "tailscale_ip": listener_ip,
            "notification_port": listener_port,
        }

        response = await api_client.ask_respond(test_data)

        if response is not None:
            print(f"  [OK] Webhook responded: {response}")
            return True
        else:
            print("  [FAIL] Webhook test failed: No response or error")
            return False

    finally:
        await api_client.close()


def test_notification_health(host, port):
    """Test the notification listener health check endpoint."""
    print("\n- Testing Notification Listener Health Check")

    if host == "0.0.0.0":
        host = "127.0.0.1"
    url = f"http://{host}:{port}/"

    print(f"  Testing health endpoint: {url}")

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get("status") == "ok":
                print(f"  [OK] Health check passed: {data}")
                return True
            else:
                print(f"  [FAIL] Health check failed: {data}")
                return False
    except Exception as e:
        print(f"  [FAIL] Health check error: {e}")
        return False


class NotificationTester(QObject):
    """Helper class to test notification reception using Qt signals."""

    notification_received = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.received = False
        self.payload = None
        self.notification_received.connect(self._on_notification)

    def _on_notification(self, payload):
        self.received = True
        self.payload = payload
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ✅ Notification received!")
        print(f"  Payload: {payload}")


def test_notification_listener(listen_host, port, auth_token, timeout_seconds=30):
    """Test the notification listener by actually listening for incoming posts."""
    print(f"\n- Testing Notification Listener (Listening for {timeout_seconds}s)")
    print(f"  Listening on http://{listen_host}:{port}/notification")

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    tester = NotificationTester()

    listener = NotificationListener(
        host=listen_host,
        port=port,
        auth_token=auth_token if auth_token and auth_token != "" else None
    )

    listener.notification_received.connect(tester._on_notification)

    try:
        listener.start()
        print(f"  🚀 Notification listener started on {listen_host}:{port}")

        start_time = time.time()
        while not tester.received and (time.time() - start_time) < timeout_seconds:
            time.sleep(0.5)
            remaining = int(timeout_seconds - (time.time() - start_time))
            if remaining % 10 == 0 and remaining > 0:
                print(f"  ⏰ Still waiting... {remaining} seconds remaining")

        listener.stop()

        if tester.received:
            print(f"  [OK] Notification received from n8n!")
            print(f"     Received at: {datetime.fromtimestamp(time.time()).strftime('%H:%M:%S')}")
            return True, tester.payload
        else:
            print(f"  [FAIL] TIMEOUT: No notification received within {timeout_seconds} seconds.")
            return False, None

    except Exception as e:
        print(f"  [FAIL] Listener error: {e}")
        listener.stop()
        return False, None


def print_troubleshooting_tips(config):
    """Print troubleshooting tips for common connectivity issues."""
    print("\n💡 Troubleshooting Tips:")
    print("   1. Ensure Tailscale is running on BOTH this machine and the n8n server")
    print(f"   2. Check that n8n can ping this machine's Tailscale IP:")
    print(f"      -> From n8n host: ping {config.tailscale_ip}")
    print("   3. Verify no firewall is blocking port 8080 between n8n and this machine")
    print("   4. Test connectivity from n8n using curl:")
    display_host = config.tailscale_ip if config.tailscale_ip != "0.0.0.0" else "<your-tailscale-ip>"
    print(f"      -> From n8n host: curl -X POST http://{display_host}:{config.notification_port}/notification -H \"Content-Type: application/json\" -d '{{\"test\":\"connectivity\"}}'")
    print("   5. Check that n8n workflow is configured to use the correct URL:")
    print(f"      -> Webhook URL: {config.n8n_webhook_url}")
    print(f"      -> Notification URL should be: http://{config.tailscale_ip}:{config.notification_port}/notification")
    print("   6. Verify the n8n auth token matches if authentication is enabled")


async def main():
    """Run all connectivity tests."""
    print("🚀 AI Desktop Assistant Connectivity Test")
    print("=" * 60)

    config = ClientConfig()
    print_diagnostics(config)

    listen_host = config.tailscale_ip if config.tailscale_ip != "0.0.0.0" else "0.0.0.0"
    port_available = test_port_availability(listen_host, config.notification_port)
    if not port_available:
        print("\n⚠️  Warning: Port may be in use. Continuing anyway...")

    print("\n📋 Running Connectivity Tests:")
    print("-" * 40)

    import uuid
    test_id = f"cli-{str(uuid.uuid4())[:8]}"

    host_for_health = config.tailscale_ip if config.tailscale_ip != "0.0.0.0" else "127.0.0.1"
    health_ok = test_notification_health(host_for_health, config.notification_port)

    # Start listener first if health passed or port is available
    listener = None
    tester = NotificationTester()
    auth_token = config.n8n_auth_token if config.n8n_auth_token and config.n8n_auth_token != "" else None
    
    app = QApplication.instance() or QApplication([])

    try:
        listener = NotificationListener(
            host=listen_host,
            port=config.notification_port,
            auth_token=auth_token
        )
        listener.notification_received.connect(tester._on_notification)
        listener.start()
        print(f"  🚀 Inbound Listener active on {listen_host}:{config.notification_port}")
    except Exception as e:
        print(f"  ⚠️  Could not start standalone listener (may already be running in Shadow.exe): {e}")

    # Now send webhook with callback_url and test_id
    webhook_ok = await test_webhook_api(test_id=test_id)

    # Wait up to 5 seconds to check if n8n triggered callback
    print("  ⏳ Waiting up to 5s for n8n callback...")
    start_t = time.time()
    while not tester.received and (time.time() - start_t) < 5.0:
        await asyncio.sleep(0.5)

    if listener:
        try:
            listener.stop()
        except Exception:
            pass

    notification_ok = tester.received
    notification_payload = tester.payload

    print("\n" + "=" * 60)
    print("📊 Test Results:")
    print(f"  Webhook API (Client → n8n):    {'PASS' if webhook_ok else 'FAIL'}")
    print(f"  Listener Health Check:         {'PASS' if health_ok else 'FAIL'}")
    print(f"  Notification Reception:        {'PASS' if notification_ok else 'FAIL (timeout or error)'}")

    overall_success = webhook_ok and health_ok and notification_ok

    if overall_success:
        print("\n🎉 ALL TESTS PASSED! Bidirectional communication is working.")
        if notification_payload:
            print(f"   Last received notification: {notification_payload}")
    else:
        print("\n❌ SOME TESTS FAILED. See troubleshooting tips below.")
        print_troubleshooting_tips(config)

    return overall_success


if __name__ == "__main__":
    success = False
    try:
        success = asyncio.run(main())
    except Exception as e:
        print(f"\n💥 Unexpected error during testing: {e}")
        import traceback
        traceback.print_exc()
        success = False

    sys.exit(0 if success else 1)
