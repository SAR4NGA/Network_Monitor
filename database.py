"""
database.py – SQLite layer for tracking daily network usage.
Tables:
  - daily_usage      : total bytes per day
  - connection_usage : bytes per network connection name per day
  - app_usage        : bytes per process/app per day
"""
import sqlite3
import os
from datetime import datetime, timedelta

# Use a fixed path in %APPDATA% so the widget, service, and dashboard
# all read/write the SAME database regardless of install location.
DB_DIR  = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "NetworkMonitor")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "network_usage.db")


def _get_connection():
    """Return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
    """Create all tables if they don't exist."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_usage (
            date TEXT PRIMARY KEY,
            bytes_sent INTEGER DEFAULT 0,
            bytes_recv INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS connection_usage (
            date        TEXT,
            connection  TEXT,
            bytes_sent  INTEGER DEFAULT 0,
            bytes_recv  INTEGER DEFAULT 0,
            PRIMARY KEY (date, connection)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_usage (
            date        TEXT,
            app_name    TEXT,
            bytes_sent  INTEGER DEFAULT 0,
            bytes_recv  INTEGER DEFAULT 0,
            PRIMARY KEY (date, app_name)
        )
    """)
    conn.commit()
    conn.close()


# ── Daily total usage ──────────────────────────────────────────────────────

def update_usage(sent_delta: int, recv_delta: int):
    """Add the given deltas (bytes) to today's row."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM daily_usage WHERE date = ?", (today,))
    if cursor.fetchone():
        cursor.execute(
            "UPDATE daily_usage SET bytes_sent = bytes_sent + ?, bytes_recv = bytes_recv + ? WHERE date = ?",
            (sent_delta, recv_delta, today),
        )
    else:
        cursor.execute(
            "INSERT INTO daily_usage (date, bytes_sent, bytes_recv) VALUES (?, ?, ?)",
            (today, sent_delta, recv_delta),
        )
    conn.commit()
    conn.close()


def get_last_30_days():
    """Return [{date, bytes_sent, bytes_recv}, ...] for the last 30 days."""
    conn = _get_connection()
    cursor = conn.cursor()
    end_date   = datetime.now()
    start_date = end_date - timedelta(days=29)
    cursor.execute(
        "SELECT date, bytes_sent, bytes_recv FROM daily_usage "
        "WHERE date BETWEEN ? AND ? ORDER BY date ASC",
        (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")),
    )
    rows = {row["date"]: dict(row) for row in cursor.fetchall()}
    conn.close()
    results = []
    for i in range(30):
        d = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        results.append(rows.get(d, {"date": d, "bytes_sent": 0, "bytes_recv": 0}))
    return results


# ── Per-connection usage ───────────────────────────────────────────────────

def update_connection_usage(connection: str, sent_delta: int, recv_delta: int):
    """Add deltas to today's row for a specific network connection name."""
    if not connection or sent_delta + recv_delta == 0:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM connection_usage WHERE date = ? AND connection = ?",
        (today, connection),
    )
    if cursor.fetchone():
        cursor.execute(
            "UPDATE connection_usage SET bytes_sent = bytes_sent + ?, bytes_recv = bytes_recv + ? "
            "WHERE date = ? AND connection = ?",
            (sent_delta, recv_delta, today, connection),
        )
    else:
        cursor.execute(
            "INSERT INTO connection_usage (date, connection, bytes_sent, bytes_recv) VALUES (?, ?, ?, ?)",
            (today, connection, sent_delta, recv_delta),
        )
    conn.commit()
    conn.close()


def get_connection_usage_30_days():
    """Return [{connection, bytes_sent, bytes_recv}, ...] aggregated over the last 30 days, sorted by total desc."""
    conn = _get_connection()
    cursor = conn.cursor()
    limit = (datetime.now() - timedelta(days=29)).strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT connection, SUM(bytes_sent) AS bytes_sent, SUM(bytes_recv) AS bytes_recv "
        "FROM connection_usage WHERE date >= ? GROUP BY connection ORDER BY (bytes_sent + bytes_recv) DESC",
        (limit,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ── Per-app usage ──────────────────────────────────────────────────────────

def update_app_usage(app_name: str, sent_delta: int, recv_delta: int):
    """Add deltas to today's row for a specific app."""
    if not app_name or sent_delta + recv_delta == 0:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM app_usage WHERE date = ? AND app_name = ?",
        (today, app_name),
    )
    if cursor.fetchone():
        cursor.execute(
            "UPDATE app_usage SET bytes_sent = bytes_sent + ?, bytes_recv = bytes_recv + ? "
            "WHERE date = ? AND app_name = ?",
            (sent_delta, recv_delta, today, app_name),
        )
    else:
        cursor.execute(
            "INSERT INTO app_usage (date, app_name, bytes_sent, bytes_recv) VALUES (?, ?, ?, ?)",
            (today, app_name, sent_delta, recv_delta),
        )
    conn.commit()
    conn.close()


def get_app_usage_today():
    """Return [{app_name, bytes_sent, bytes_recv}, ...] for today, sorted by total desc."""
    conn = _get_connection()
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT app_name, bytes_sent, bytes_recv FROM app_usage "
        "WHERE date = ? ORDER BY (bytes_sent + bytes_recv) DESC",
        (today,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ── Cleanup ────────────────────────────────────────────────────────────────

def cleanup_old_data(days=30):
    """Delete all records older than the given number of days from all tables."""
    conn = _get_connection()
    limit_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        conn.execute("DELETE FROM daily_usage      WHERE date < ?", (limit_date,))
        conn.execute("DELETE FROM connection_usage WHERE date < ?", (limit_date,))
        conn.execute("DELETE FROM app_usage        WHERE date < ?", (limit_date,))
        conn.commit()
    finally:
        conn.close()
