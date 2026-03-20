"""
widget.py – Glass-transparent desktop widget that sits BEHIND all windows.

Behaviours:
  • Fully transparent background (glass effect).
  • Rendered on the desktop layer (behind apps, on the wallpaper).
  • White text for a clean modern look.
  • Normally shows nothing visually prominent – on hover shows
    upload/download speed, network name, and IP.
  • Completely click-through – does not intercept any mouse events.
"""
import tkinter as tk
import ctypes
import ctypes.wintypes

# ── Win32 constants ────────────────────────────────────────────
GWL_EXSTYLE       = -20
WS_EX_LAYERED     = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW  = 0x00000080
WS_EX_NOACTIVATE  = 0x08000000
LWA_COLORKEY      = 0x00000001

# Suppress cross-platform static analysis warnings from linters
user32 = ctypes.windll.user32  # type: ignore
user32.SetWindowLongW.restype  = ctypes.c_long
user32.SetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.GetWindowLongW.restype  = ctypes.c_long
user32.GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
user32.SetLayeredWindowAttributes.argtypes = [
    ctypes.wintypes.HWND, ctypes.wintypes.COLORREF, ctypes.c_byte, ctypes.wintypes.DWORD,
]

SWP_NOSIZE      = 0x0001
SWP_NOMOVE      = 0x0002
SWP_NOACTIVATE  = 0x0010
HWND_TOPMOST    = -1
HWND_BOTTOM     = 1

# Colour that will be punched out as transparent
_TRANSPARENT_KEY = "#010101"


class MiniWidget:
    """
    Glass-transparent, click-through widget rendered on the desktop layer.
    """

    FG = "#ffffff"  # white text

    def __init__(self, root: tk.Tk, on_click=None):
        self.root = root
        self.on_click = on_click

        # ── window basics ──────────────────────────────────────────
        self.root.overrideredirect(True)
        self.root.configure(bg=_TRANSPARENT_KEY)
        self.root.attributes("-topmost", False)

        # Position: bottom-right, close to the edge (above taskbar)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        win_w, win_h = 240, 130
        self.win_w = win_w
        self.win_h = win_h
        # Right in the corner, snug against the edges
        x = sw - win_w - 10
        y = sh - win_h - 55
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")

        # ── canvas for text ────────────────────────────────────────
        self.canvas = tk.Canvas(
            self.root, width=win_w, height=win_h,
            bg=_TRANSPARENT_KEY, highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        # Default speed text (always visible)
        self._speed_id = self.canvas.create_text(
            win_w - 10, 100, anchor="ne", justify="right",
            text="↑  0 B/s    ↓  0 B/s",
            font=("Segoe UI", 10, "bold"), fill=self.FG,
        )

        # Hover detail text (hidden until hover)
        self._detail_id = self.canvas.create_text(
            win_w - 10, 68, anchor="ne", justify="right", text="",
            font=("Segoe UI", 10), fill=self.FG,
        )

        # Bind hover on the *root* so it works even though window is click-through
        # We'll poll the mouse position instead.
        self._is_hovering = False
        self._was_clicked = False
        self._network_name = ""
        self._local_ip = ""
        self._upload_text = "↑  0 B/s"
        self._download_text = "↓  0 B/s"
        
        self._current_speed_y = 100.0
        self._target_speed_y = 100.0

        self._is_dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._win_start_x = 0
        self._win_start_y = 0

        # Start hover-polling
        self._poll_hover()

    # ── public setters ─────────────────────────────────────────────
    def update_speed(self, up_bps: int, down_bps: int):
        self._upload_text = f"↑  {self._fmt(up_bps)}"
        self._download_text = f"↓  {self._fmt(down_bps)}"
        self._refresh_display()

    def update_network_name(self, name: str):
        self._network_name = name

    def update_local_ip(self, ip: str):
        self._local_ip = ip

    # ── apply Win32 desktop-layer magic ────────────────────────────
    def apply_desktop_mode(self):
        """Call AFTER mainloop has started (via root.after) so HWND exists."""
        hwnd = int(self.root.wm_frame(), 16)

        # 1) Make layered + tool-window (no taskbar) + no-activate + click-through
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)

        # 2) Set the transparent colour key
        colour_ref = 0x00010101  # BGR for #010101
        user32.SetLayeredWindowAttributes(hwnd, colour_ref, 0, LWA_COLORKEY)

        # 3) Push to BOTTOM of Z-order (behind other windows)
        user32.SetWindowPos(
            hwnd, HWND_BOTTOM, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )

        # Keep pushing to bottom periodically
        self._stay_on_bottom()

    def _stay_on_bottom(self):
        """Periodically push to HWND_BOTTOM so we don't pop up over apps."""
        try:
            hwnd = int(self.root.wm_frame(), 16)
            user32.SetWindowPos(
                hwnd, HWND_BOTTOM, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        except Exception:
            pass
        self.root.after(2000, self._stay_on_bottom)

    # ── hover polling ──────────────────────────────────────────────
    def _poll_hover(self):
        """Check if cursor is over the widget area (since events pass through)."""
        try:
            px, py = self.root.winfo_pointerxy()
            wx = self.root.winfo_rootx()
            wy = self.root.winfo_rooty()
            ww = self.root.winfo_width()
            wh = self.root.winfo_height()
            
            # Formally check if we are covered by another app window
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            
            hwnd_under = user32.WindowFromPoint(POINT(px, py))
            under_class = ""
            if hwnd_under:
                buff = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd_under, buff, 256)
                under_class = buff.value
                
            desktop_classes = ("Progman", "WorkerW", "SysListView32", "TkTopLevel")
            
            in_bounds = wx <= px <= wx + ww and wy <= py <= wy + wh
            # Only count as hovering if nothing is covering us!
            hovering = in_bounds and (under_class in desktop_classes)
            
            if hovering != self._is_hovering:
                self._is_hovering = hovering
                self._target_speed_y = 35.0 if hovering else 100.0
                self._refresh_display()

            # Smooth animation for speed and detail text position
            if abs(self._current_speed_y - self._target_speed_y) > 0.5:
                self._current_speed_y += (self._target_speed_y - self._current_speed_y) * 0.3
                self.canvas.coords(self._speed_id, self.win_w - 10, int(self._current_speed_y))
                self.canvas.coords(self._detail_id, self.win_w - 10, int(self._current_speed_y) + 33)
            elif self._current_speed_y != self._target_speed_y:
                self._current_speed_y = self._target_speed_y
                self.canvas.coords(self._speed_id, self.win_w - 10, int(self._current_speed_y))
                self.canvas.coords(self._detail_id, self.win_w - 10, int(self._current_speed_y) + 33)

            # Global mouse hook for drag & click support
            lmb_down = user32.GetAsyncKeyState(0x01) & 0x8000
            
            if lmb_down:
                if not self._was_clicked:
                    self._was_clicked = True
                    # If clicked while hovering, start dragging
                    if hovering:
                        self._is_dragging = True
                        self._drag_start_x = px
                        self._drag_start_y = py
                        self._win_start_x = wx
                        self._win_start_y = wy
                elif self._is_dragging:
                    # Update window position relative to drag start
                    new_x = self._win_start_x + (px - self._drag_start_x)
                    new_y = self._win_start_y + (py - self._drag_start_y)
                    self.root.geometry(f"+{new_x}+{new_y}")
            else:
                if self._was_clicked:
                    # Released LMB
                    if self._is_dragging:
                        self._is_dragging = False
                        # If the drag distance was very small, treat it as a click (Dashboard)
                        dist_sq = (px - self._drag_start_x)**2 + (py - self._drag_start_y)**2
                        if dist_sq < 25 and self.on_click:
                            self.on_click()
                    self._was_clicked = False

        except Exception:
            pass
        self.root.after(30, self._poll_hover)

    def _refresh_display(self):
        horiz_text = f"{self._upload_text}    {self._download_text}"
        self.canvas.itemconfigure(self._speed_id, text=horiz_text)
        
        if self._is_hovering:
            detail = f"Network:  {self._network_name}\nLocal IP:   {self._local_ip}"
            self.canvas.itemconfigure(self._detail_id, text=detail)
        else:
            self.canvas.itemconfigure(self._detail_id, text="")

    # ── helpers ────────────────────────────────────────────────────
    @staticmethod
    def _fmt(b: int) -> str:
        if b < 1024:
            return f"{b} B/s"
        elif b < 1024 ** 2:
            return f"{b / 1024:.1f} KB/s"
        elif b < 1024 ** 3:
            return f"{b / 1024**2:.1f} MB/s"
        else:
            return f"{b / 1024**3:.2f} GB/s"
