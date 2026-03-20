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

from database import get_last_30_days


class Dashboard:
    """
    A Toplevel window containing:
    1. A live line-chart (last 20 s of up/down speeds).
    2. Local & Public IP info.
    3. A 30-day usage history table.
    """

    # ── colour tokens ──────────────────────────────────────────────
    BG           = "#0f0f1a"
    FG           = "#e0e0e0"
    ACCENT_UP    = "#00f5d4"
    ACCENT_DOWN  = "#f72585"
    CARD_BG      = "#1a1a2e"
    HEADER_FG    = "#7b7f9e"

    HISTORY_SIZE = 20  # seconds of live data

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

    # ── public API ─────────────────────────────────────────────────
    def open(self, local_ip: str, public_ip: str):
        """Create / raise the dashboard window."""
        if self.win is not None and self.win.winfo_exists():
            self.win.lift()
            return

        self.win = tk.Toplevel(self.master)
        self.win.title("Network Monitor – Dashboard")
        self.win.configure(bg=self.BG)
        self.win.geometry("780x720")
        self.win.minsize(700, 650)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

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

        # -- Title
        ttk.Label(self.win, text="⚡ Network Dashboard", style="Title.TLabel").pack(
            anchor="w", padx=20, pady=(16, 8))

        # -- Live Graph Card
        graph_card = ttk.Frame(self.win, style="Card.TFrame", padding=10)
        graph_card.pack(fill="x", padx=20, pady=(0, 10))

        ttk.Label(graph_card, text="LIVE SPEED  (last 20 s)", style="Header.TLabel").pack(anchor="w")

        self.fig = Figure(figsize=(7, 2.4), dpi=100, facecolor=self.CARD_BG)
        self.ax = self.fig.add_subplot(111)
        self._style_axis()

        xs = list(range(-self.HISTORY_SIZE + 1, 1))
        self.line_up, = self.ax.plot(xs, list(self._up_history), color=self.ACCENT_UP,
                                     linewidth=2, label="Upload")
        self.line_down, = self.ax.plot(xs, list(self._down_history), color=self.ACCENT_DOWN,
                                       linewidth=2, label="Download")
        self.ax.legend(loc="upper left", fontsize=8, facecolor=self.CARD_BG,
                       edgecolor="#333", labelcolor=self.FG)

        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_card)
        self.canvas.get_tk_widget().pack(fill="x")

        # -- IP Info Card
        ip_card = ttk.Frame(self.win, style="Card.TFrame", padding=10)
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
        hist_card = ttk.Frame(self.win, style="Card.TFrame", padding=10)
        hist_card.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        ttk.Label(hist_card, text="USAGE HISTORY  (last 30 days)", style="Header.TLabel").pack(
            anchor="w", pady=(0, 6))

        # Treeview styles
        style.configure("Hist.Treeview",
                        background=self.CARD_BG, foreground=self.FG,
                        fieldbackground=self.CARD_BG, rowheight=24,
                        font=("Segoe UI", 9))
        style.configure("Hist.Treeview.Heading",
                        background="#16213e", foreground=self.HEADER_FG,
                        font=("Segoe UI", 9, "bold"))
        style.map("Hist.Treeview", background=[("selected", "#0f3460")])

        cols = ("date", "sent", "recv")
        self.tree = ttk.Treeview(hist_card, columns=cols, show="headings",
                                 height=8, style="Hist.Treeview")
        self.tree.heading("date", text="Date")
        self.tree.heading("sent", text="Uploaded")
        self.tree.heading("recv", text="Downloaded")
        self.tree.column("date", width=140, anchor="center")
        self.tree.column("sent", width=140, anchor="center")
        self.tree.column("recv", width=140, anchor="center")

        scrollbar = ttk.Scrollbar(hist_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._populate_history()

    def update_graph(self, up_bps: int, down_bps: int):
        """Push a new data point and redraw the graph (called every second)."""
        if self.win is None or not self.win.winfo_exists():
            return

        self._up_history.append(up_bps)
        self._down_history.append(down_bps)

        self.line_up.set_ydata(list(self._up_history))
        self.line_down.set_ydata(list(self._down_history))

        max_val = max(max(self._up_history), max(self._down_history), 1)
        self.ax.set_ylim(0, max_val * 1.2)

        self.canvas.draw_idle()

    def is_open(self) -> bool:
        return self.win is not None and self.win.winfo_exists()

    # ── internal ───────────────────────────────────────────────────
    def _style_axis(self):
        self.ax.set_facecolor(self.CARD_BG)
        self.ax.tick_params(colors=self.FG, labelsize=8)
        self.ax.set_xlabel("Seconds ago", fontsize=8, color=self.HEADER_FG)
        self.ax.set_ylabel("Bytes/s", fontsize=8, color=self.HEADER_FG)
        for spine in self.ax.spines.values():
            spine.set_color("#333")
        self.ax.grid(True, color="#222", linewidth=0.5)

    def _populate_history(self):
        """Fill the treeview with 30-day data from the database."""
        for row in self.tree.get_children():
            self.tree.delete(row)

        data = get_last_30_days()
        for entry in reversed(data):  # most recent first
            self.tree.insert("", "end", values=(
                entry["date"],
                self._fmt(entry["bytes_sent"]),
                self._fmt(entry["bytes_recv"]),
            ))

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
