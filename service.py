"""
service.py – Windows Service to track network usage in the background.

Install with: python service.py install
Start with:   python service.py start
"""
import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import time
import sys
import os
import psutil

# Add current directory to path so imports work when running as service
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import initialize_db, update_usage, update_connection_usage, update_app_usage, cleanup_old_data
from network_scanner import get_speed, get_network_name

class NetworkUsageService(win32serviceutil.ServiceFramework):
    _svc_name_ = "NetworkUsageTracker"
    _svc_display_name_ = "Network Usage Tracker Service"
    _svc_description_ = "Background service that logs daily network usage to the local SQLite database."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = True

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        self.running = False

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.main()

    def main(self):
        # Initialize baseline
        initialize_db()
        get_speed() # establishes baseline
        
        last_cleanup = 0
        last_app_track = time.time()
        
        window_sent = 0
        window_recv = 0
        
        PRIVATE_PREFIXES = ("127.", "::1", "0.0.0.0", "::")

        def is_external(addr):
            if not addr or not addr.ip:
                return False
            ip = addr.ip
            return not any(ip.startswith(p) for p in PRIVATE_PREFIXES) and \
                   not ip.startswith("10.") and \
                   not (ip.startswith("192.168.")) and \
                   not (ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31)
        
        while self.running:
            # Poll every 2 seconds for "realtime" background logging
            try:
                up, down, sent_d, recv_d = get_speed()
                
                if sent_d > 0 or recv_d > 0:
                    update_usage(sent_d, recv_d)
                    
                    # Track per-connection
                    network_name = get_network_name()
                    if network_name and network_name not in ("Detecting…", "Unknown"):
                         update_connection_usage(network_name, sent_d, recv_d)
                         
                    # Accumulate for app tracking
                    window_sent += sent_d
                    window_recv += recv_d
                
                # Every 5 seconds, track apps
                now = time.time()
                if now - last_app_track >= 5.0:
                    last_app_track = now
                    total_sent = window_sent
                    total_recv = window_recv
                    window_sent = 0
                    window_recv = 0
                    
                    if total_sent > 0 or total_recv > 0:
                        pid_conn_count = {}
                        pid_name = {}
                        
                        try:
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
                                
                            if pid_conn_count:
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
                            
                # Periodic cleanup (every 1 hour)
                if now - last_cleanup > 3600:
                    cleanup_old_data(days=30)
                    last_cleanup = now
            except Exception:
                 pass
                
            # Sleep 2s or until stop event
            rc = win32event.WaitForSingleObject(self.stop_event, 2000)
            if rc == win32event.WAIT_OBJECT_0:
                break

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(NetworkUsageService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(NetworkUsageService)
