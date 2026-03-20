"""
network_scanner.py – Utility functions to read live network metrics.
"""
import socket
import subprocess
import psutil
import requests


# ---------------------------------------------------------------------------
# Speed helpers
# ---------------------------------------------------------------------------

_prev_counters = None


def get_speed():
    """
    Return (upload_bytes_per_sec, download_bytes_per_sec, sent_delta, recv_delta).
    Must be called at a regular interval (e.g. every 1 s) for meaningful results.
    The first call returns zeros while it establishes a baseline.
    """
    global _prev_counters
    counters = psutil.net_io_counters()

    if _prev_counters is None:
        _prev_counters = counters
        return 0, 0, 0, 0

    sent_delta = counters.bytes_sent - _prev_counters.bytes_sent
    recv_delta = counters.bytes_recv - _prev_counters.bytes_recv
    _prev_counters = counters

    return sent_delta, recv_delta, sent_delta, recv_delta


# ---------------------------------------------------------------------------
# IP helpers
# ---------------------------------------------------------------------------

def get_local_ip() -> str:
    """Return the local IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "N/A"


def get_public_ip() -> str:
    """Return the public IP address (calls an external service)."""
    try:
        resp = requests.get("https://api.ipify.org", timeout=5)
        return resp.text.strip()
    except Exception:
        return "N/A"


# ---------------------------------------------------------------------------
# Network name
# ---------------------------------------------------------------------------

def get_network_name() -> str:
    """
    Return the active network name.
    On Wi-Fi this is the SSID; otherwise falls back to adapted name via psutil.
    """
    # Try Wi-Fi SSID on Windows
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            if "SSID" in line and "BSSID" not in line:
                return line.split(":")[1].strip()
    except Exception:
        pass

    # Fallback: find the first UP network adapter using psutil
    try:
        stats = psutil.net_if_stats()
        for iface, info in stats.items():
            if info.isup and iface != "Loopback Pseudo-Interface 1" and "Loopback" not in iface:
                return f"{iface}"
    except Exception:
        pass

    return "Unknown"
