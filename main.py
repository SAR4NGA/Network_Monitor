"""
main.py – Entry point for the Network Monitor desktop widget.

Runs a glass-transparent, click-through overlay on the desktop that
shows live upload/download speeds.  Hover ▸ speeds + network name + IP.
Logs daily usage to SQLite in the background.
Includes a system tray icon to easily quit the application.
"""
import tkinter as tk
import threading
import ctypes
import winreg
import sys
import os
import time

try:
    # Single instance application check (mutex)
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "NetworkMonitor_SingleInstance_Mutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)
        
    # Use type: ignore to bypass cross-platform static analysis warnings from linters
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore
except Exception:
    pass

import pystray
from PIL import Image, ImageDraw
from pystray import MenuItem as item

from database import initialize_db, update_usage, update_connection_usage, update_app_usage
from network_scanner import get_speed, get_local_ip, get_public_ip, get_network_name
from widget import MiniWidget
from dashboard import Dashboard


def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def get_app_icon():
    """Load the application icon from the bundled assets."""
    icon_path = get_resource_path("app_icon.ico")
    if os.path.exists(icon_path):
        return Image.open(icon_path)
    # Fallback to a simple generated icon if file missing
    image = Image.new('RGB', (64, 64), color=(15, 52, 96))
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=(0, 245, 212))
    return image


class NetworkMonitorApp:
    """Orchestrates the desktop widget and background data collection."""

    POLL_MS = 1000  # 1 second

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # hide the default root window
        self._quit_requested = False

        # ── database ───────────────────────────────────────────────
        initialize_db()

        # ── Branding ───────────────────────────────────────────────
        self.icon = get_app_icon()
        icon_path = get_resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)

        # ── widget (Toplevel) ──────────────────────────────────────
        self.widget_win = tk.Toplevel(self.root)
        self.widget_win.withdraw()
        if os.path.exists(icon_path):
            self.widget_win.iconbitmap(icon_path)
        self.widget = MiniWidget(self.widget_win, on_click=self._open_dashboard)

        # ── dashboard ──────────────────────────────────────────────
        self.dashboard = Dashboard(self.root)

        # ── cached values ──────────────────────────────────────────
        self._local_ip = "Fetching…"
        self._public_ip = "Fetching…"
        self._network_name = "Detecting…"
        # Shared bandwidth window accumulators (filled by _poll, read by _app_usage_loop)
        self._window_sent = 0
        self._window_recv = 0

        # ── background fetches ─────────────────────────────────────
        threading.Thread(target=self._network_info_loop, daemon=True).start()
        threading.Thread(target=self._app_usage_loop, daemon=True).start()

        # ── system tray ────────────────────────────────────────────
        self.tray = pystray.Icon(
            "NetworkMonitor",
            self.icon,
            "Network Monitor",
            menu=pystray.Menu(
                item('Show Widget', self._on_tray_show),
                item('Dashboard', lambda: self.root.after(0, self._open_dashboard)),
                item('Run at Startup', self._on_toggle_startup, checked=lambda item: self._is_at_startup()),
                item('Exit', self._on_tray_exit)
            )
        )
        # Start tray in a background thread because icon.run() blocks
        threading.Thread(target=self.tray.run, daemon=True).start()

        # ── start polling ──────────────────────────────────────────
        self.widget_win.deiconify()

        # Apply desktop mode after the window is mapped (need a valid HWND)
        self.root.after(200, self.widget.apply_desktop_mode)

        self._poll()
        self.root.mainloop()

    # ── tray actions ───────────────────────────────────────────────
    def _on_tray_exit(self, icon, cur_item):
        self._quit_requested = True
        icon.stop()

    def _on_tray_show(self, icon, cur_item):
        self.root.after(0, self.widget_win.deiconify)

    def _is_at_startup(self):
        """Check if the app is in the Windows Startup registry."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(key, "Network Monitor")
            winreg.CloseKey(key)
            return True
        except WindowsError:
            return False

    def _on_toggle_startup(self, icon, cur_item):
        """Toggle the application in the Windows Startup registry."""
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        if self._is_at_startup():
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, "Network Monitor")
                winreg.CloseKey(key)
            except Exception:
                pass
        else:
            try:
                # Use current exe or script path
                path = os.path.abspath(sys.argv[0])
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "Network Monitor", 0, winreg.REG_SZ, f'"{path}"')
                winreg.CloseKey(key)
            except Exception:
                pass

    # ── 1-second polling loop ──────────────────────────────────────
    def _poll(self):
        if self._quit_requested:
            self.root.destroy()
            return

        up, down, sent_d, recv_d = get_speed()

        if sent_d > 0 or recv_d > 0:
            update_usage(sent_d, recv_d)
            # Track per-connection usage using the current network name
            if self._network_name and self._network_name not in ("Detecting…", "Unknown"):
                update_connection_usage(self._network_name, sent_d, recv_d)
            # Accumulate for app attribution window
            self._window_sent += sent_d
            self._window_recv += recv_d

        self.widget.update_speed(up, down)
        self.widget.update_network_name(self._network_name)
        self.widget.update_public_ip(self._public_ip)

        # Feed live data to the dashboard if it's open
        if self.dashboard.is_open():
            self.dashboard.update_graph(up, down)
            self.dashboard.update_ips(self._local_ip, self._public_ip)

        self.root.after(self.POLL_MS, self._poll)

    # ── background helpers ─────────────────────────────────────────
    def _network_info_loop(self):
        """Unified background loop to keep network name and IPs up to date."""
        last_public_ip_check = 0

        while not self._quit_requested:
            try:
                # 1) Refresh basic local info
                new_name = get_network_name()
                new_local = get_local_ip()

                # 2) Detect change
                info_changed = (new_name != self._network_name or new_local != self._local_ip)

                # Update local state
                self._network_name = new_name
                self._local_ip = new_local

                # 3) Refresh Public IP if network changed OR 5 mins have passed (or it's the first run)
                now = time.time()
                if info_changed or (now - last_public_ip_check > 300) or self._public_ip == "Fetching…":
                    self._public_ip = get_public_ip()
                    last_public_ip_check = now

            except Exception:
                pass

            # Poll every 10 seconds
            # Using a shorter sleep with a loop to respond to quit_requested faster
            for _ in range(100):
                if self._quit_requested: break
                time.sleep(0.1)

    def _app_usage_loop(self):
        """
        Background loop: track per-app network usage every 5 seconds.

        Approach: identify which processes have active external (non-loopback,
        non-LAN) TCP/UDP connections, then proportionally attribute the total
        measured internet bandwidth among those processes by connection count.
        This avoids using proc.io_counters() which includes disk I/O on Windows.
        """
        import psutil

        PRIVATE_PREFIXES = ("127.", "::1", "0.0.0.0", "::")

        def is_external(addr):
            if not addr or not addr.ip:
                return False
            ip = addr.ip
            return not any(ip.startswith(p) for p in PRIVATE_PREFIXES) and \
                   not ip.startswith("10.") and \
                   not (ip.startswith("192.168.")) and \
                   not (ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31)

        while not self._quit_requested:
            try:
                # Get total internet bytes in this 5s window from the main poll
                # We read cumulative values and diff them
                total_sent = 0
                total_recv = 0

                # Count connections per process (external only)
                pid_conn_count: dict = {}
                pid_name: dict = {}

                for conn in psutil.net_connections(kind="inet"):
                    if conn.pid is None:
                        continue
                    raddr = conn.raddr
                    if not raddr:
                        continue
                    if not is_external(raddr):
                        continue
                    pid = conn.pid
                    if pid not in pid_conn_count:
                        pid_conn_count[pid] = 0
                        try:
                            p = psutil.Process(pid)
                            pid_name[pid] = p.name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pid_name[pid] = "Unknown"
                    pid_conn_count[pid] += 1

                # We'll attribute the bandwidth measured over the last 5s window.
                # The _poll loop already wrote the per-second deltas to daily_usage.
                # Here we need the 5s window total — read it from a shared counter.
                total_sent = self._window_sent
                total_recv = self._window_recv
                self._window_sent = 0
                self._window_recv = 0

                if pid_conn_count and (total_sent + total_recv) > 0:
                    total_conns = sum(pid_conn_count.values())
                    for pid, conn_count in pid_conn_count.items():
                        fraction = conn_count / total_conns
                        app_sent = int(total_sent * fraction)
                        app_recv = int(total_recv * fraction)
                        name = pid_name.get(pid, "Unknown")
                        if name and (app_sent + app_recv) > 0:
                            update_app_usage(name, app_sent, app_recv)

            except Exception:
                pass

            # Every 5 seconds
            for _ in range(50):
                if self._quit_requested: break
                time.sleep(0.1)


    def _open_dashboard(self):
        """Called when the user clicks on the desktop widget."""
        self.dashboard.open(self._local_ip, self._public_ip)



if __name__ == "__main__":
    NetworkMonitorApp()
