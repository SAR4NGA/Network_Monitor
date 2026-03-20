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

try:
    # Use type: ignore to bypass cross-platform static analysis warnings from linters
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore
except Exception:
    pass

import pystray
from PIL import Image, ImageDraw
from pystray import MenuItem as item

from database import initialize_db, update_usage
from network_scanner import get_speed, get_local_ip, get_public_ip, get_network_name
from widget import MiniWidget
from dashboard import Dashboard


def create_tray_image():
    """Create a simple 64x64 icon for the system tray."""
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

        # ── widget (Toplevel) ──────────────────────────────────────
        self.widget_win = tk.Toplevel(self.root)
        self.widget_win.withdraw()
        self.widget = MiniWidget(self.widget_win, on_click=self._open_dashboard)

        # ── dashboard ──────────────────────────────────────────────
        self.dashboard = Dashboard(self.root)

        # ── cached values ──────────────────────────────────────────
        self._local_ip = "Fetching…"
        self._public_ip = "Fetching…"
        self._network_name = "Detecting…"

        # ── background fetches ─────────────────────────────────────
        threading.Thread(target=self._fetch_ip, daemon=True).start()
        threading.Thread(target=self._fetch_public_ip, daemon=True).start()
        threading.Thread(target=self._fetch_net_name, daemon=True).start()

        # ── system tray setup ──────────────────────────────────────
        self.tray_icon = pystray.Icon(
            "network_monitor",
            create_tray_image(),
            "Network Monitor",
            menu=pystray.Menu(item('Exit', self._on_tray_exit))
        )
        # Start tray in a background thread because icon.run() blocks
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

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

    # ── 1-second polling loop ──────────────────────────────────────
    def _poll(self):
        if self._quit_requested:
            self.root.destroy()
            return

        up, down, sent_d, recv_d = get_speed()

        if sent_d > 0 or recv_d > 0:
            update_usage(sent_d, recv_d)

        self.widget.update_speed(up, down)
        self.widget.update_network_name(self._network_name)
        self.widget.update_local_ip(self._local_ip)

        # Feed live data to the dashboard graph if it's open
        if self.dashboard.is_open():
            self.dashboard.update_graph(up, down)

        self.root.after(self.POLL_MS, self._poll)

    # ── background helpers ─────────────────────────────────────────
    def _fetch_ip(self):
        self._local_ip = get_local_ip()

    def _fetch_public_ip(self):
        self._public_ip = get_public_ip()

    def _open_dashboard(self):
        """Called when the user clicks on the desktop widget."""
        self.dashboard.open(self._local_ip, self._public_ip)

    def _fetch_net_name(self):
        self._network_name = get_network_name()
        self.root.after(10_000, self._net_name_loop)

    def _net_name_loop(self):
        threading.Thread(target=self._refresh_net_name, daemon=True).start()

    def _refresh_net_name(self):
        self._network_name = get_network_name()
        try:
            self.root.after(10_000, self._net_name_loop)
        except Exception:
            pass


if __name__ == "__main__":
    NetworkMonitorApp()
