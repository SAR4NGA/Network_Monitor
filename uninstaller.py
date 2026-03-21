"""
uninstaller.py – Uninstaller for Network Monitor.
Removes the service, files, shortcuts, and registry entries.
"""
import os
import sys
import shutil
import subprocess
import winreg

APP_NAME = "Network Monitor"
INSTALL_DIR = os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"), "NetworkMonitor")
START_MENU_FOLDER = os.path.join(
    os.environ.get("PROGRAMDATA", "C:\\ProgramData"),
    "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME
)
UNINSTALL_REG_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\NetworkMonitor"


def uninstall():
    print(f"--- {APP_NAME} Uninstaller ---")

    service_exe = os.path.join(INSTALL_DIR, "TrackerService.exe")

    # 1. Stop and remove the Windows Service
    print("Stopping and removing background service...")
    if os.path.exists(service_exe):
        try:
            subprocess.run([service_exe, "stop"], timeout=10)
        except Exception:
            pass
        try:
            subprocess.run([service_exe, "remove"], timeout=10)
            print("Service removed.")
        except Exception as e:
            print(f"  Could not remove service (may need to be done manually): {e}")
    else:
        # Fallback via sc.exe if files already deleted
        try:
            subprocess.run(["sc", "stop", "NetworkUsageTracker"], timeout=10)
            subprocess.run(["sc", "delete", "NetworkUsageTracker"], timeout=10)
        except Exception:
            pass

    # 2. Remove Start Menu shortcut folder
    print("Removing Start Menu shortcuts...")
    if os.path.exists(START_MENU_FOLDER):
        try:
            shutil.rmtree(START_MENU_FOLDER)
            print("Shortcuts removed.")
        except Exception as e:
            print(f"  Could not remove shortcuts: {e}")

    # 3. Remove startup registry entry
    print("Removing startup registry entry...")
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        print("Startup entry removed.")
    except Exception:
        pass  # Entry may not exist

    # 4. Remove uninstall registry entry
    print("Removing uninstall registry entry...")
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_REG_KEY)
        print("Uninstall entry removed.")
    except Exception:
        pass  # Entry may not exist

    # 5. Remove installed files (last step so we can still use the exes above)
    print("Removing installed files...")
    if os.path.exists(INSTALL_DIR):
        try:
            shutil.rmtree(INSTALL_DIR)
            print("Files removed.")
        except Exception as e:
            print(f"  Could not remove all files: {e}")
            print("  Some files may need to be deleted manually.")

    print(f"\n{APP_NAME} has been uninstalled successfully.")
    print("\nPress Enter to exit.")
    input()


if __name__ == "__main__":
    uninstall()
