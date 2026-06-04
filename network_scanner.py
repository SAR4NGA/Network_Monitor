"""
network_scanner.py – Utility functions to read live network metrics.

Speed measurement ONLY counts traffic on the primary internet-facing adapter
(the one with the default gateway) to match ISP-reported data.
Loopback, LAN, and virtual adapters are excluded.
"""
import socket
import subprocess
import psutil
import requests


# ---------------------------------------------------------------------------
# Primary adapter detection
# ---------------------------------------------------------------------------

_primary_adapter_cache: str | None = None


def get_primary_adapter() -> str | None:
    """
    Return the name of the network adapter that carries the default route
    (i.e. the internet-facing adapter). Result is cached for 30s via caller.

    Strategy:
      Match local IP to an adapter address via socket (fast, doesn't block UI).
      Return None if undetermined.
    """
    try:
        local_ip = get_local_ip()
        if local_ip and local_ip != "N/A":
            for iface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.address == local_ip:
                        return iface
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Speed helpers
# ---------------------------------------------------------------------------

_prev_counters = None
_primary_adapter: str | None = None
_adapter_check_counter = 0          # re-detect adapter every 30 calls (~30 s)
_fallback_mode = False

def get_speed():
    """
    Return (upload_bps, download_bps, sent_delta, recv_delta).

    Only traffic on the primary internet-facing adapter is counted so that
    loopback, LAN shares, and virtual adapters do not inflate the numbers.
    """
    global _prev_counters, _primary_adapter, _adapter_check_counter, _fallback_mode

    # Refresh primary adapter name every 30 calls
    _adapter_check_counter += 1
    if _adapter_check_counter >= 30 or _primary_adapter is None:
        new_primary = get_primary_adapter()
        if new_primary != _primary_adapter:
             # Adapter changed, reset baseline
             _prev_counters = None
        _primary_adapter = new_primary
        _adapter_check_counter = 0

    using_fallback = False

    # Collect counters
    if _primary_adapter:
        # Per-NIC mode – most accurate
        all_counters = psutil.net_io_counters(pernic=True)
        if _primary_adapter in all_counters:
            counters = all_counters[_primary_adapter]
        else:
            # Adapter name changed (e.g. after reconnect) — reset & retry next call
            _primary_adapter = None
            _prev_counters = None
            return 0, 0, 0, 0
    else:
        using_fallback = True
        # Fallback: sum non-loopback, non-virtual adapters
        all_counters = psutil.net_io_counters(pernic=True)
        _SKIP = {"loopback", "pseudo", "vmware", "vethernet", "hyper-v",
                 "vbox", "virtualbox", "wsl", "isatap", "teredo"}
        sent, recv = 0, 0
        stats = psutil.net_if_stats()
        for nic, c in all_counters.items():
            nic_lower = nic.lower()
            if not stats.get(nic, None) or not stats[nic].isup:
                continue
            if any(k in nic_lower for k in _SKIP):
                continue
            if "loopback" in nic_lower or nic_lower.startswith("lo"):
                continue
            sent += c.bytes_sent
            recv += c.bytes_recv

        # Build a synthetic object
        class _Cnt:
            def __init__(self, s, r):
                self.bytes_sent = s
                self.bytes_recv = r
        counters = _Cnt(sent, recv)

    if using_fallback != _fallback_mode:
         _prev_counters = None
         _fallback_mode = using_fallback

    if _prev_counters is None:
        _prev_counters = counters
        return 0, 0, 0, 0

    sent_delta = max(0, counters.bytes_sent - _prev_counters.bytes_sent)
    recv_delta = max(0, counters.bytes_recv - _prev_counters.bytes_recv)
    _prev_counters = counters

    # Ignore physically impossible deltas (e.g., > 100 Gbps or 12.5 GB/s)
    # This acts as a safety net against OS counter rollovers or glitches.
    if sent_delta > 12500000000 or recv_delta > 12500000000:
        return 0, 0, 0, 0

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
    """Return the active network name."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetConnectionProfile | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.stdout.strip():
            return result.stdout.strip().split("\n")[0].strip()
    except Exception:
        pass

    # Fallback: first UP non-loopback interface
    try:
        stats = psutil.net_if_stats()
        for iface, info in stats.items():
            if info.isup and "Loopback" not in iface:
                return iface
    except Exception:
        pass

    return "Unknown"
