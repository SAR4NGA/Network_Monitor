"""
build_all.py – Script to build both the Widget and the Background Service as EXEs.
Requires: pip install pyinstaller
"""
import subprocess
import sys
import os

def build():
    # Ensure we are in the project folder
    proj_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(proj_dir)
    print(f"Working in: {proj_dir}")

    # 1. Build the main Widget (GDI-transparent)
    print("Building NetworkMonitor.exe...")
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "NetworkMonitor",
        "--icon", "app_icon.ico",
        "--add-data", "database.py;.",
        "--add-data", "network_scanner.py;.",
        "--add-data", "dashboard.py;.",
        "--add-data", "widget.py;.",
        "--add-data", "app_icon.ico;.",
        "main.py"
    ], check=True)

    # 2. Build the Service (needs console=True for registration logic, but runs hidden as service)
    print("\nBuilding TrackerService.exe...")
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--name", "TrackerService",
        "--icon", "app_icon.ico",
        "--hidden-import", "win32timezone",
        "service.py"
    ], check=True)

    # 3. Build the Bundled Setup (All-in-one Installer)
    print("\nBuilding Setup.exe...")
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--uac-admin", # Request admin for service registration
        "--name", "Setup",
        "--icon", "app_icon.ico",
        "--add-data", f"dist/NetworkMonitor.exe;.",
        "--add-data", f"dist/TrackerService.exe;.",
        "installer.py"
    ], check=True)

    print("\nDone! Look in the 'dist' folder for:")
    print(" - NetworkMonitor.exe (The GUI widget)")
    print(" - TrackerService.exe (The background tracker)")
    print(" - Setup.exe (The single-file installer)")

if __name__ == "__main__":
    try:
        build()
    except Exception as e:
        print(f"Build failed: {e}")
