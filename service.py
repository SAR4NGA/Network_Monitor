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

# Add current directory to path so imports work when running as service
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import initialize_db, update_usage
from network_scanner import get_speed

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
        
        while self.running:
            # Poll every 2 seconds for "realtime" background logging
            up, down, sent_d, recv_d = get_speed()
            
            if sent_d > 0 or recv_d > 0:
                update_usage(sent_d, recv_d)
            
            # Periodic cleanup (every 1 hour)
            now = time.time()
            if now - last_cleanup > 3600:
                from database import cleanup_old_data
                cleanup_old_data(days=30)
                last_cleanup = now
                
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
