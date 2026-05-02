"""
Windows entry point for Sentinel Pulse.

Starts the FastAPI server, optionally launches MongoDB, and opens browser automatically.
Features:
- System tray icon with context menu
- Global hotkeys for quick actions
- Auto-start option on system boot
- Native Windows notifications
"""
import asyncio
import os
import sys
import webbrowser
import subprocess
import threading
import time
import signal
import socket
import logging
import winreg
from pathlib import Path

logger = logging.getLogger("SentinelPulse")

# Add the app directory to path
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent

sys.path.insert(0, str(BASE_DIR))

# Optional MongoDB process
_mongo_process = None
_tray_icon = None
_app = None


def is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect(('localhost', port))
            return True
        except OSError:
            return False


def check_mongo_running() -> bool:
    """Check if MongoDB is already running."""
    try:
        result = subprocess.run(
            ['tasklist'], 
            capture_output=True, 
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        return 'mongod' in result.stdout.lower()
    except Exception:
        return False


def start_mongodb():
    """Skip MongoDB in packaged app - use in-memory instead."""
    global _mongo_process
    # Packaged apps should not try to start bundled MongoDB
    if getattr(sys, 'frozen', False):
        logger.info("Packaged mode - skipping MongoDB, using in-memory")
        return
    
    # Skip MongoDB in packaged app
    if getattr(sys, 'frozen', False):
        logger.info('Packaged mode - using in-memory')
    else:
        mongo_exe = BASE_DIR / 'mongodb' / 'mongod.exe'
        if mongo_exe.exists():
            start_mongodb()
            for _ in range(10):
                if is_port_in_use(27017):
                    time.sleep(1)
                    break
                time.sleep(0.5)
            logger.info('MongoDB OK' if is_port_in_use(27017) else 'Using in-memory')
        else:
            logger.info('Using in-memory mode')

    logger.info("[Server] Starting on port %d...", port)
    logger.info("")
    


def open_browser():
    """Open the dashboard in the default browser."""
    import webbrowser
    import os
    port = int(os.environ.get("PORT", "8002"))
    webbrowser.open(f"http://localhost:{port}")


def graceful_shutdown(signum, frame):
    """Handle graceful shutdown."""
    logger.info("Shutting down...")
    stop_mongodb()
    sys.exit(0)




def _setup_system_tray(): pass  # Optional system tray (can be implemented later)

def _setup_global_hotkeys(): pass  # Optional global hotkeys (can be implemented later)

def stop_mongodb():
    """Stop the MongoDB process we started."""
    global _mongo_process
    if _mongo_process:
        try:
            _mongo_process.terminate()
            _mongo_process.wait(timeout=5)
        except Exception:
            try:
                _mongo_process.kill()
            except Exception:
                pass
        _mongo_process = None


def main():
    port = int(os.environ.get("PORT", "8002"))
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    logger.info("=" * 50)
    logger.info("Sentinel Pulse v1.0.0")
    logger.info("=" * 50)
    logger.info("")
    if getattr(sys, "frozen", False):
        logger.info("Packaged mode - in-memory")
    else:
        mongo_exe = BASE_DIR / "mongodb" / "mongod.exe"
        if mongo_exe.exists():
            start_mongodb()
    
    # Give server time to start before opening browser
    time.sleep(2)
    
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    # Set up system tray (optional - don't fail if it doesn't work)
    try:
        _setup_system_tray()
    except Exception as e:
        logger.warning(f"System tray setup skipped: {e}")
    
    # Set up global hotkeys (optional)
    try:
        _setup_global_hotkeys()
    except Exception as e:
        logger.warning(f"Global hotkeys setup skipped: {e}")
    
    import uvicorn
    from server import app
    
    try:
        uvicorn.run(
            app, 
            host="0.0.0.0", 
            port=port, 
            log_config=None
        )
    finally:
        stop_mongodb()
        logger.info("[Sentinel Pulse] Server stopped")


if __name__ == "__main__":
    main()