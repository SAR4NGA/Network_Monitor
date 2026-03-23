"""
dashboard.py – Advanced Dashboard with live graph, IP info and 30-day history.
"""
import tkinter as tk
from tkinter import ttk
from collections import deque

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from database import get_last_30_days, get_connection_usage_30_days, get_app_usage_today
import os
import sys

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class Dashboard:
    """
    A Toplevel window containing:
    1. A live line-chart (last 20 s of up/down speeds).
    2. Local & Public IP info.
    3. A 30-day usage history table.
    4. Per-connection usage table (last 30 days).
    5. Per-app usage table (today).
    """

    # ── colour tokens ──────────────────────────────────────────────
    BG           = "#36393f"  # Discord main bg
    FG           = "#ffffff"  # Pure white
    ACCENT_UP    = "#5865F2"  # Blurple
    ACCENT_DOWN  = "#57F287"  # Green
    CARD_BG      = "#2f3136"  # Discord sub bg
    HEADER_FG    = "#ffffff"  # Pure white
    TITLE_BG     = "#202225"  # Headings bg

    HISTORY_SIZE = 60  # seconds of live data

    def __init__(self, master: tk.Tk):
        self.win = None
        self.master = master
        self._up_history: deque = deque([0] * self.HISTORY_SIZE, maxlen=self.HISTORY_SIZE)
        self._down_history: deque = deque([0] * self.HISTORY_SIZE, maxlen=self.HISTORY_SIZE)
        self.canvas = None
        self.fig = None
        self.ax = None
        self.line_up = None
        self.line_down = None
        self.local_ip_label = None
        self.public_ip_label = None
        self.tree = None
        self.conn_tree = None
        self.app_tree = None
        self._is_opening = False

    # ── public API ─────────────────────────────────────────────────
    def open(self, local_ip: str, public_ip: str):
        """Create / raise the dashboard window."""
        if getattr(self, "_is_opening", False):
            return
        
        if self.win is not None and self.win.winfo_exists():
            self.win.lift()
            return

        self._is_opening = True
        self.master.after(500, lambda: setattr(self, "_is_opening", False))

        self.win = tk.Toplevel(self.master)
        self.win.title("Network Monitor – Dashboard")
        self.win.configure(bg=self.BG)
        self.win.geometry("820x900")
        self.win.minsize(700, 700)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        # -- Icon
        icon_path = get_resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            self.win.iconbitmap(icon_path)

        # -- Style
        style = ttk.Style(self.win)
        style.theme_use("clam")
        style.configure("Card.TFrame", background=self.CARD_BG)
        style.configure("Card.TLabel", background=self.CARD_BG, foreground=self.FG,
                        font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=self.CARD_BG, foreground=self.HEADER_FG,
                        font=("Segoe UI", 9, "bold"))
        style.configure("Title.TLabel", background=self.BG, foreground=self.FG,
                        font=("Segoe UI", 14, "bold"))
        style.configure("Hist.Treeview",
                        background=self.CARD_BG, foreground=self.FG,
                        fieldbackground=self.CARD_BG, rowheight=28,
                        font=("Segoe UI", 9), borderwidth=0)
        style.configure("Hist.Treeview.Heading",
                        background=self.TITLE_BG, foreground=self.HEADER_FG,
                        font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("Hist.Treeview", background=[("selected", "#393c43")])

        # -- Scrollable main frame
        outer = tk.Frame(self.win, bg=self.BG)
        outer.pack(fill="both", expand=True)

        canvas_scroll = tk.Canvas(outer, bg=self.BG, highlightthickness=0)
        vbar = ttk.Scrollbar(outer, orient="vertical", command=canvas_scroll.yview)
        canvas_scroll.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        canvas_scroll.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas_scroll, bg=self.BG)
        inner_id = canvas_scroll.create_window((0, 0), window=inner, anchor="nw")

        def _on_frame_configure(e):
            canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
        def _on_canvas_configure(e):
            canvas_scroll.itemconfig(inner_id, width=e.width)

        inner.bind("<Configure>", _on_frame_configure)
        canvas_scroll.bind("<Configure>", _on_canvas_configure)

        # Mousewheel scrolling
        def _on_mousewheel(e):
            canvas_scroll.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas_scroll.bind_all("<MouseWheel>", _on_mousewheel)

        # -- Title
        ttk.Label(inner, text="⚡ Network Dashboard", style="Title.TLabel").pack(
            anchor="w", padx=20, pady=(16, 8))

        # -- Live Graph Card
        graph_card = ttk.Frame(inner, style="Card.TFrame", padding=10)
        graph_card.pack(fill="x", padx=20, pady=(0, 10))

        ttk.Label(graph_card, text="LIVE SPEED  (last 1 min)", style="Header.TLabel").pack(anchor="w")

        self.fig = Figure(figsize=(7, 2.2), dpi=100, facecolor=self.CARD_BG)
        self.ax = self.fig.add_subplot(111)
        self._style_axis()

        xs = list(range(-self.HISTORY_SIZE + 1, 1))
        self.line_up, = self.ax.plot(xs, list(self._up_history), color=self.ACCENT_UP,
                                     linewidth=2, label="Upload")
        self.fill_up = self.ax.fill_between(xs, list(self._up_history), color=self.ACCENT_UP, alpha=0.15)
        
        self.line_down, = self.ax.plot(xs, list(self._down_history), color=self.ACCENT_DOWN,
                                       linewidth=2, label="Download")
        self.fill_down = self.ax.fill_between(xs, list(self._down_history), color=self.ACCENT_DOWN, alpha=0.15)
        
        self.ax.legend(loc="upper left", fontsize=8, facecolor=self.BG,
                       edgecolor=self.BG, labelcolor=self.FG, framealpha=0.8)

        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_card)
        self.canvas.get_tk_widget().pack(fill="x")

        # -- IP Info Card
        ip_card = ttk.Frame(inner, style="Card.TFrame", padding=10)
        ip_card.pack(fill="x", padx=20, pady=(0, 10))

        ttk.Label(ip_card, text="IP INFORMATION", style="Header.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Label(ip_card, text="Local IP:", style="Card.TLabel").grid(row=1, column=0, sticky="w")
        self.local_ip_label = ttk.Label(ip_card, text=local_ip, style="Card.TLabel")
        self.local_ip_label.grid(row=1, column=1, sticky="w", padx=(10, 0))

        ttk.Label(ip_card, text="Public IP:", style="Card.TLabel").grid(row=2, column=0, sticky="w")
        self.public_ip_label = ttk.Label(ip_card, text=public_ip, style="Card.TLabel")
        self.public_ip_label.grid(row=2, column=1, sticky="w", padx=(10, 0))

        # -- 30-Day History Card
        self.tree = self._make_table_card(
            inner,
            title="USAGE HISTORY  (last 30 days)",
            columns=("date", "recv", "sent"),
            headings=("Date", "Downloaded", "Uploaded"),
            widths=(160, 140, 140),
            height=7,
        )
        self._populate_history()

        # -- Per-Connection Card
        self.conn_tree = self._make_table_card(
            inner,
            title="USAGE BY CONNECTION  (last 30 days)",
            columns=("connection", "recv", "sent", "total"),
            headings=("Network", "Downloaded", "Uploaded", "Total"),
            widths=(180, 120, 120, 120),
            height=5,
        )
        self._populate_connection()

        # -- Per-App Card
        self.app_tree = self._make_table_card(
            inner,
            title="USAGE BY APP  (today)",
            columns=("app", "recv", "sent", "total"),
            headings=("Application", "Downloaded", "Uploaded", "Total"),
            widths=(200, 110, 110, 110),
            height=8,
        )
        self._populate_apps()

        # Start 5-second auto-refresh
        self._auto_refresh()

    def _make_table_card(self, parent, title, columns, headings, widths, height):
        """Helper: build a labeled card containing a Treeview and return it."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=10)
        card.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        style = ttk.Style(self.win)
        ttk.Label(card, text=title, style="Header.TLabel").pack(anchor="w", pady=(0, 6))

        tree = ttk.Treeview(card, columns=columns, show="headings",
                             height=height, style="Hist.Treeview")
        for col, heading, width in zip(columns, headings, widths):
            tree.heading(col, text=heading)
            tree.column(col, width=width, anchor="center")

        sb = ttk.Scrollbar(card, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        tree.tag_configure("total", font=("Segoe UI", 9, "bold"))
        tree.tag_configure("sep", foreground=self.HEADER_FG)
        return tree

    # ── auto-refresh (5 s) ─────────────────────────────────────────
    def _auto_refresh(self):
        if not self.is_open():
            return
        self._populate_history()
        self._populate_connection()
        self._populate_apps()
        self.master.after(5000, self._auto_refresh)

    # ── populate helpers ───────────────────────────────────────────
    def _populate_history(self):
        """Fill the 30-day history table."""
        if not self.tree:
            return
        for row in self.tree.get_children():
            self.tree.delete(row)

        data = get_last_30_days()
        total_sent = total_recv = 0
        for entry in reversed(data):
            sent, recv = entry["bytes_sent"], entry["bytes_recv"]
            total_sent += sent
            total_recv += recv
            self.tree.insert("", "end", values=(
                entry["date"], self._fmt(recv), self._fmt(sent),
            ))
        if data:
            self.tree.insert("", "end", values=("──────────", "──────────", "──────────"), tags=("sep",))
            self.tree.insert("", "end", values=("TOTAL (30 Days)", self._fmt(total_recv), self._fmt(total_sent)), tags=("total",))

    def _populate_connection(self):
        """Fill the per-connection table."""
        if not self.conn_tree:
            return
        for row in self.conn_tree.get_children():
            self.conn_tree.delete(row)

        data = get_connection_usage_30_days()
        total_sent = total_recv = 0
        for entry in data:
            sent, recv = entry["bytes_sent"], entry["bytes_recv"]
            total_sent += sent
            total_recv += recv
            self.conn_tree.insert("", "end", values=(
                entry["connection"], self._fmt(recv), self._fmt(sent), self._fmt(sent + recv),
            ))
        if data:
            self.conn_tree.insert("", "end", values=("──────────", "──────", "──────", "──────"), tags=("sep",))
            self.conn_tree.insert("", "end", values=("TOTAL", self._fmt(total_recv), self._fmt(total_sent), self._fmt(total_sent + total_recv)), tags=("total",))

    def _populate_apps(self):
        """Fill the per-app table."""
        if not self.app_tree:
            return
        for row in self.app_tree.get_children():
            self.app_tree.delete(row)

        data = get_app_usage_today()
        total_sent = total_recv = 0
        for entry in data:
            sent, recv = entry["bytes_sent"], entry["bytes_recv"]
            total_sent += sent
            total_recv += recv
            self.app_tree.insert("", "end", values=(
                entry["app_name"], self._fmt(recv), self._fmt(sent), self._fmt(sent + recv),
            ))
        if data:
            self.app_tree.insert("", "end", values=("──────────", "──────", "──────", "──────"), tags=("sep",))
            self.app_tree.insert("", "end", values=("TOTAL (Today)", self._fmt(total_recv), self._fmt(total_sent), self._fmt(total_sent + total_recv)), tags=("total",))

    # ── live updates ──────────────────────────────────────────────
    def update_graph(self, up_bps: int, down_bps: int):
        """Push a new data point and redraw the graph (called every second)."""
        if not self.is_open():
            return

        self._up_history.append(up_bps)
        self._down_history.append(down_bps)

        self.line_up.set_ydata(list(self._up_history))
        self.line_down.set_ydata(list(self._down_history))

        if hasattr(self, 'fill_up') and self.fill_up:
            self.fill_up.remove()
        if hasattr(self, 'fill_down') and self.fill_down:
            self.fill_down.remove()

        xs = list(range(-self.HISTORY_SIZE + 1, 1))
        self.fill_up = self.ax.fill_between(xs, list(self._up_history), color=self.ACCENT_UP, alpha=0.15)
        self.fill_down = self.ax.fill_between(xs, list(self._down_history), color=self.ACCENT_DOWN, alpha=0.15)

        max_val = max(max(self._up_history), max(self._down_history), 1)
        self.ax.set_ylim(0, max_val * 1.2)

        self.canvas.draw_idle()

    def update_ips(self, local_ip: str, public_ip: str):
        """Update the IP labels in the UI while the window is open."""
        if not self.is_open():
            return
        self.local_ip_label.config(text=local_ip)
        self.public_ip_label.config(text=public_ip)

    def is_open(self) -> bool:
        return self.win is not None and self.win.winfo_exists()

    # ── internal ───────────────────────────────────────────────────
    def _style_axis(self):
        self.ax.set_facecolor(self.CARD_BG)
        self.ax.tick_params(colors=self.HEADER_FG, labelsize=8)
        self.ax.set_xlabel("Seconds ago", fontsize=8, color=self.HEADER_FG)
        self.ax.set_ylabel("Speed", fontsize=8, color=self.HEADER_FG)

        from matplotlib.ticker import FuncFormatter
        self.ax.yaxis.set_major_formatter(FuncFormatter(self._format_yaxis))

        for spine in self.ax.spines.values():
            spine.set_visible(False)
        self.ax.grid(True, color="#3e4147", linewidth=0.5, linestyle="--")

    def _format_yaxis(self, val, pos):
        if val < 1024:
            return f"{int(val)} B/s"
        elif val < 1024 ** 2:
            return f"{val / 1024:.1f} KB/s"
        elif val < 1024 ** 3:
            return f"{val / 1024**2:.1f} MB/s"
        else:
            return f"{val / 1024**3:.2f} GB/s"

    def _on_close(self):
        if self.fig:
            import matplotlib.pyplot as plt
            plt.close(self.fig)
        self.win.destroy()
        self.win = None

    @staticmethod
    def _fmt(b: int) -> str:
        """Human-friendly byte string."""
        if b < 1024:
            return f"{b} B"
        elif b < 1024 ** 2:
            return f"{b / 1024:.1f} KB"
        elif b < 1024 ** 3:
            return f"{b / 1024**2:.1f} MB"
        else:
            return f"{b / 1024**3:.2f} GB"
