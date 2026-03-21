"""
installer.py – Self-contained installer/uninstaller for Network Monitor.

As installer: copies files, installs service, creates Start Menu shortcut, 
               registers in Windows Settings > Apps (Add/Remove Programs).
As uninstaller: reverses all of the above cleanly.

Build the all-in-one Setup.exe with:
  pyinstaller --onefile --uac-admin --name Setup
              --add-data "dist/NetworkMonitor.exe;."
              --add-data "dist/TrackerService.exe;."
              installer.py
"""
import os
import sys
import shutil
import subprocess
import winreg

# ── App constants ───────────────────────────────────────────────────────────
APP_NAME        = "Network Monitor"
APP_FOLDER      = "NetworkMonitor"        # no spaces, used for paths
PUBLISHER       = "SAR4NGA"
VERSION         = "1.0.0"
SERVICE_NAME    = "NetworkUsageTracker"   # must match _svc_name_ in service.py
UNINSTALL_GUID  = "NetworkMonitor"        # key name under Uninstall in registry

INSTALL_DIR = os.path.join(
    os.environ.get("PROGRAMFILES", "C:\\Program Files"), APP_FOLDER
)
START_MENU_DIR = os.path.join(
    os.environ.get("PROGRAMDATA", "C:\\ProgramData"),
    "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME
)
UNINSTALL_REG = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\\" + UNINSTALL_GUID
)
STARTUP_REG = r"Software\Microsoft\Windows\CurrentVersion\Run"


# ── Helper: locate a bundled file ──────────────────────────────────────────
def _bundled(filename):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


# ── Helper: PowerShell shortcut creation (no extra deps needed) ────────────
def _create_shortcut(target, link_path, description=""):
    ps = (
        f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{link_path}");'
        f'$s.TargetPath="{target}";'
        f'$s.WorkingDirectory="{os.path.dirname(target)}";'
        f'$s.Description="{description}";'
        f'$s.Save()'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True
    )


def _stop_running_processes():
    print("Ensuring no instances are running...")
    # Kill the widget
    try:
        subprocess.run(["taskkill", "/F", "/IM", "NetworkMonitor.exe", "/T"],
                       capture_output=True)
    except Exception:
        pass

    # Stop the service via sc.exe (works even if file is missing)
    try:
        subprocess.run(["sc", "stop", SERVICE_NAME], capture_output=True, timeout=10)
    except Exception:
        pass

    import time
    time.sleep(2) # Give Windows a moment to release file handles


# ═══════════════════════════════════════════════════════════════════════════
#  INSTALL
# ═══════════════════════════════════════════════════════════════════════════
def install():
    print(f"--- {APP_NAME} Installer ---\n")

    _stop_running_processes()

    monitor_dest     = os.path.join(INSTALL_DIR, "NetworkMonitor.exe")
    service_dest     = os.path.join(INSTALL_DIR, "TrackerService.exe")
    uninstaller_dest = os.path.join(INSTALL_DIR, "Uninstall.exe")

    # ── 1. Create install folder ────────────────────────────────────────────
    print(f"Installing to: {INSTALL_DIR}")
    os.makedirs(INSTALL_DIR, exist_ok=True)

    # ── 2. Copy files ───────────────────────────────────────────────────────
    print("Copying files...")
    try:
        shutil.copy2(_bundled("NetworkMonitor.exe"), monitor_dest)
        shutil.copy2(_bundled("TrackerService.exe"), service_dest)
        # Copy this very exe as the uninstaller
        shutil.copy2(os.path.abspath(sys.argv[0]), uninstaller_dest)
        print("  Files copied.")
    except Exception as e:
        print(f"  ERROR: {e}"); input(); return

    # ── 3. Install & start service ──────────────────────────────────────────
    print("Installing background service...")
    for cmd in ("install", "start"):
        try:
            subprocess.run([service_dest, cmd], check=True, capture_output=True)
            print(f"  Service {cmd}ed.")
        except Exception as e:
            print(f"  Service '{cmd}' failed (may be OK if not first install): {e}")

    # ── 4. Startup registry (HKCU – no admin needed for this key) ───────────
    print("Setting up auto-start...")
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, f'"{monitor_dest}"')
        winreg.CloseKey(k)
        print("  Auto-start enabled.")
    except Exception as e:
        print(f"  Startup registry failed: {e}")

    # ── 5. Start Menu shortcut ───────────────────────────────────────────────
    print("Creating Start Menu shortcut...")
    try:
        os.makedirs(START_MENU_DIR, exist_ok=True)
        _create_shortcut(
            monitor_dest,
            os.path.join(START_MENU_DIR, f"{APP_NAME}.lnk"),
            f"Launch {APP_NAME}"
        )
        _create_shortcut(
            uninstaller_dest,
            os.path.join(START_MENU_DIR, f"Uninstall {APP_NAME}.lnk"),
            f"Uninstall {APP_NAME}"
        )
        print("  Start Menu shortcut created.")
    except Exception as e:
        print(f"  Start Menu shortcut failed: {e}")

    # ── 6. Register in Add/Remove Programs (Windows Settings > Apps) ─────────
    print("Registering in Windows Apps list...")
    try:
        k = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_REG)
        winreg.SetValueEx(k, "DisplayName",     0, winreg.REG_SZ,    APP_NAME)
        winreg.SetValueEx(k, "DisplayVersion",  0, winreg.REG_SZ,    VERSION)
        winreg.SetValueEx(k, "Publisher",       0, winreg.REG_SZ,    PUBLISHER)
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ,    INSTALL_DIR)
        winreg.SetValueEx(k, "DisplayIcon",     0, winreg.REG_SZ,    monitor_dest)
        winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ,    f'"{uninstaller_dest}" uninstall')
        winreg.SetValueEx(k, "NoModify",        0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair",        0, winreg.REG_DWORD, 1)
        winreg.CloseKey(k)
        print("  Registered in Windows Apps.")
    except Exception as e:
        print(f"  Apps registration failed: {e}")

    # ── 7. Launch ────────────────────────────────────────────────────────────
    print(f"\nLaunching {APP_NAME}...")
    try:
        subprocess.Popen([monitor_dest])
    except Exception as e:
        print(f"  Could not launch: {e}")

    print("\nInstallation complete!")
    print("Press Enter to close.")
    input()


# ═══════════════════════════════════════════════════════════════════════════
#  UNINSTALL
# ═══════════════════════════════════════════════════════════════════════════
def uninstall():
    print(f"--- {APP_NAME} Uninstaller ---\n")

    _stop_running_processes()

    service_dest = os.path.join(INSTALL_DIR, "TrackerService.exe")

    # ── 1. Stop and remove service ──────────────────────────────────────────
    print("Stopping background service...")
    for cmd in ("stop", "remove"):
        try:
            subprocess.run([service_dest, cmd], capture_output=True, timeout=15)
            print(f"  Service {cmd}d.")
        except Exception:
            # Fallback: use sc.exe in case exe is missing
            try:
                sc_cmd = "stop" if cmd == "stop" else "delete"
                subprocess.run(["sc", sc_cmd, SERVICE_NAME], capture_output=True)
            except Exception:
                pass

    # ── 2. Remove startup registry ──────────────────────────────────────────
    print("Removing startup entry...")
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(k, APP_NAME)
            print("  Startup entry removed.")
        except Exception:
            pass
        winreg.CloseKey(k)
    except Exception:
        pass

    # ── 3. Remove Start Menu shortcut ───────────────────────────────────────
    print("Removing Start Menu shortcuts...")
    if os.path.exists(START_MENU_DIR):
        try:
            shutil.rmtree(START_MENU_DIR)
            print("  Shortcuts removed.")
        except Exception as e:
            print(f"  Could not remove shortcuts: {e}")

    # ── 4. Remove Add/Remove Programs entry ─────────────────────────────────
    print("Removing Windows Apps entry...")
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_REG)
        print("  Apps entry removed.")
    except Exception:
        pass

    # ── 5. Delete installed files ────────────────────────────────────────────
    print("Removing files...")
    if os.path.exists(INSTALL_DIR):
        # Delete everything except this running exe (Uninstall.exe)
        running = os.path.abspath(sys.argv[0]).lower()
        for item in os.listdir(INSTALL_DIR):
            full = os.path.join(INSTALL_DIR, item)
            if full.lower() == running:
                continue
            try:
                if os.path.isfile(full):
                    os.remove(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full)
            except Exception:
                pass

        # Schedule self-deletion and folder cleanup via a temp batch file
        bat = os.path.join(os.environ.get("TEMP", "C:\\Windows\\Temp"), "_nm_cleanup.bat")
        with open(bat, "w") as f:
            f.write(f'@echo off\n')
            f.write(f'ping 127.0.0.1 -n 3 > nul\n')    # wait 3 seconds
            f.write(f'del /f /q "{running}"\n')
            f.write(f'rmdir /q "{INSTALL_DIR}"\n')
            f.write(f'del /f /q "%~f0"\n')              # delete this bat too
        subprocess.Popen(["cmd.exe", "/c", bat],
                         creationflags=0x00000008)       # DETACHED_PROCESS
        print("  Files removed.")

    print(f"\n{APP_NAME} has been uninstalled.")
    print("Press Enter to close.")
    input()


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "uninstall":
        uninstall()
    else:
        install()
