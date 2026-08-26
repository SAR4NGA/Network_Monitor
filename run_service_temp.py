import sys, os, time, threading
sys.path.insert(0, r'C:\Users\sar4n\Desktop\antigravity\scratch\network_monitor')
os.chdir(r'C:\Users\sar4n\Desktop\antigravity\scratch\network_monitor')

from database import initialize_db, update_usage, update_connection_usage, update_app_usage, cleanup_old_data
from network_scanner import get_speed, get_network_name
import psutil

PRIVATE_PREFIXES = ("127.", "::1", "0.0.0.0", "::")
def is_external(addr):
    if not addr or not addr.ip:
        return False
    ip = addr.ip
    return not any(ip.startswith(p) for p in PRIVATE_PREFIXES) and \
           not ip.startswith("10.") and \
           not (ip.startswith("192.168.")) and \
           not (ip.startswith("172.") and 16 <= int(ip.split('.')[1]) <= 31)

initialize_db()
get_speed()  # baseline
window_sent = 0
window_recv = 0
last_app_track = time.time()
last_cleanup = 0

for _ in range(10):
    try:
        up, down, sent_d, recv_d = get_speed()
        if sent_d > 0 or recv_d > 0:
            update_usage(sent_d, recv_d)
            nn = get_network_name()
            if nn and nn not in ("Detecting…", "Unknown"):
                update_connection_usage(nn, sent_d, recv_d)
            window_sent += sent_d
            window_recv += recv_d
        now = time.time()
        if now - last_app_track >= 5.0:
            last_app_track = now
            total_sent, total_recv = window_sent, window_recv
            window_sent = window_recv = 0
            if total_sent > 0 or total_recv > 0:
                pid_conn_count = {}
                pid_name = {}
                for conn in psutil.net_connections(kind="inet"):
                    if conn.pid is None: continue
                    raddr = conn.raddr
                    if not raddr or not is_external(raddr): continue
                    pid = conn.pid
                    if pid not in pid_conn_count:
                        pid_conn_count[pid] = 0
                        try:
                            pid_name[pid] = psutil.Process(pid).name()
                        except:
                            pid_name[pid] = "Unknown"
                    pid_conn_count[pid] += 1
                if pid_conn_count:
                    total_conns = sum(pid_conn_count.values())
                    for pid, cc in pid_conn_count.items():
                        frac = cc / total_conns
                        app_sent = int(total_sent * frac)
                        app_recv = int(total_recv * frac)
                        name = pid_name.get(pid, "Unknown")
                        if name and (app_sent + app_recv) > 0:
                            update_app_usage(name, app_sent, app_recv)
        if now - last_cleanup > 3600:
            cleanup_old_data(30)
            last_cleanup = now
    except Exception:
        import traceback; traceback.print_exc()
    time.sleep(2)
print("Service simulation completed OK")
