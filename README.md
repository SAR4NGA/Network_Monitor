# Network Monitor

A lightweight, unobtrusive desktop network monitoring application for Windows. It provides a transparent, click-through widget to track your upload and download speeds in real-time, coupled with a background Windows service that continually logs data usage.

## Features

- **Click-Through Glass UI**: A sleek, transparent overlay built with `tkinter` and `ctypes`. It blends into your desktop environment and lets you click through it without interrupting your workflow.
- **Accurate Traffic Monitoring**: Leverages `psutil` to intelligently measure bandwidth strictly on the primary internet-facing adapter. It ignores local loopback, LAN shares, and virtual adapters (like VM/WSL) for ISP-accurate readings.
- **Per-App Usage Tracking**: Maps active external TCP/UDP connections to running processes, providing a granular breakdown of which individual apps are consuming data.
- **Background Windows Service**: Includes an optional decoupled service (`NetworkUsageTracker`) built with `win32serviceutil`. It runs persistently in the background, logging daily network usage to a local SQLite database even when the UI is closed. Includes automated 30-day data retention cleanup.
- **System Tray Integration**: Sits quietly in your system tray via `pystray` for easy access to the dashboard, toggling the widget, and setting up run-at-startup.
- **Smart Resource Management**: Handles Sleep/Wake lifecycle events gracefully, managing adapters dropping or reconnecting without crashing.
- **IP & Network Detection**: Rapidly fetches external and internal IPs, along with the active network profile name.

## Architecture

- `main.py`: Entry point for the desktop widget and system tray app.
- `service.py`: The background Windows service for persistent data logging.
- `network_scanner.py`: Core logic for speed tracking, adapter sensing, and IP detection.
- `database.py`: SQLite backend for logging and storing traffic history.
- `widget.py` & `dashboard.py`: UI components for the glass overlay and detailed statistics dashboard.

## Requirements

- Python 3.8+
- Windows OS
- Dependencies (see `requirements.txt`):
  - `psutil`
  - `pystray`
  - `Pillow`
  - `requests`
  - `pywin32` (for the background service)

## Installation & Usage

### Using CMD (From Source)

1. **Install Dependencies:**
   ```cmd
   pip install -r requirements.txt
   ```

2. **Run the Desktop Widget:**
   ```cmd
   python main.py
   ```

3. **Install & Start the Background Service (Optional):**
   Requires Administrator privileges.
   ```cmd
   python service.py install
   python service.py start
   ```

### Using Executable (.exe)

Simply double-click the `setup.exe` executable to run the widget. No Python installation or manual dependency setup is required!

## Building

A `build_all.py` script is provided to bundle the application into a standalone Windows Executable (`.exe`) via PyInstaller, embedding the custom `app_icon.ico` and producing `NetworkMonitor.exe`.
