"""
database.py – SQLite layer for tracking daily network usage.
"""
import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "network_usage.db")


def _get_connection():
    """Return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
    """Create the daily_usage table if it doesn't exist."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_usage (
            date TEXT PRIMARY KEY,
            bytes_sent INTEGER DEFAULT 0,
            bytes_recv INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def update_usage(sent_delta: int, recv_delta: int):
    """
    Add the given deltas (bytes) to today's row.
    If no row exists for today, one is created.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT bytes_sent, bytes_recv FROM daily_usage WHERE date = ?", (today,))
    row = cursor.fetchone()

    if row:
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
    """
    Return a list of dicts [{date, bytes_sent, bytes_recv}, ...] for the last 30 days,
    filling in zeros for missing days.
    """
    conn = _get_connection()
    cursor = conn.cursor()

    end_date = datetime.now()
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
        if d in rows:
            results.append(rows[d])
        else:
            results.append({"date": d, "bytes_sent": 0, "bytes_recv": 0})

    return results
