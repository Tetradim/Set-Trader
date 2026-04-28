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
    """Start MongoDB daemon if not already running."""
    global _mongo_process
    
    mongo_exe = BASE_DIR / 'mongodb' / 'mongod.exe'
    data_dir = BASE_DIR / 'data' / 'db'
    
    # Check if MongoDB is already running (as admin, tasklist might need elevation)
    if is_port_in_use(27017):
        logger.info("Port 27017 in use - MongoDB likely already running")
        return
    
    # Create directories without admin check - Windows will prompt if needed
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        logger.warning(f"Permission denied creating data dir: {e}")
        logger.info("Trying to continue without bundled MongoDB...")
        return
    
    try:
        log_file = BASE_DIR / 'logs' / 'mongod.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        logger.warning(f"Permission denied creating log dir: {e}")
        # Continue anyway - logs can go to default location
    
    logger.info("Starting MongoDB on port 27017...")
    
    try:
        # Use CREATE_NO_WINDOW=0 when running as admin to avoid issues
        creation_flags = 0  # Always show window for debugging
        
        _mongo_process = subprocess.Popen(
            [
                str(mongo_exe),
                '--dbpath', str(data_dir),
                '--port', '27017',
                '--logpath', str(log_file) if log_file.parent.exists() else 'mongod.log',
                '--quiet',
                '--bind_ip', '127.0.0.1',
                '--noauth'
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creation_flags
        )
        
        # Give MongoDB a moment to start
        import time
        time.sleep(2)
        
        # Check if process is still running
        if _mongo_process.poll() is not None:
            # Process exited - get error output
            try:
                _, stderr = _mongo_process.communicate(timeout=2)
                if stderr:
                    logger.warning(f"MongoDB stderr: {stderr.decode('utf-8', errors='ignore')}")
            except:
                pass
            logger.warning("MongoDB process exited immediately")
            _mongo_process = None
            return
            
        logger.info("MongoDB started successfully (PID: %s)", _mongo_process.pid)
        
    except FileNotFoundError:
        logger.warning("MongoDB executable not found at: %s", mongo_exe)
        logger.info("Continuing without bundled MongoDB...")
    except PermissionError as e:
        logger.warning("Permission denied running MongoDB: %s", e)
        logger.info("Continuing without bundled MongoDB...")
    except Exception as e:
        logger.warning("MongoDB failed to start: %s", e)
        logger.info("Continuing without bundled MongoDB...")


def stop_mongodb():
    """Stop the bundled MongoDB instance if we started it."""
    global _mongo_process
    if not _mongo_process:
        logger.info("MongoDB was not started by this launcher")
        return
    
    logger.info("Stopping MongoDB...")
    try:
        _mongo_process.terminate()
        _mongo_process.wait(timeout=5)
    except Exception:
        try:
            _mongo_process.kill()
        except Exception:
            pass
    _mongo_process = None
    logger.info("MongoDB stopped")


def graceful_shutdown(signum, frame):
    """Handle graceful shutdown on Ctrl+C / SIGTERM."""
    logger.info("Sentinel Pulse shutting down gracefully...")
    stop_mongodb()
    sys.exit(0)


def open_browser():
    """Open browser after a short delay."""
    time.sleep(2)
    port = int(os.environ.get('PORT', '8002'))
    webbrowser.open(f"http://localhost:{port}")


# ---------------------------------------------------------------------------
# System Tray Integration (Windows)
# ---------------------------------------------------------------------------

def _setup_system_tray():
    """Set up Windows system tray icon with context menu."""
    global _tray_icon, _app
    
    try:
        import pystray
        from PIL import Image, ImageDraw
        
        # Create a simple tray icon image
        def create_tray_icon():
            img = Image.new('RGB', (64, 64), color='#6366f1')
            draw = ImageDraw.Draw(img)
            # Draw a simple pulse icon
            draw.ellipse([8, 8, 56, 56], outline='white', width=3)
            draw.ellipse([24, 24, 40, 40], fill='white')
            return img
        
        icon_image = create_tray_icon()
        
        def show_window(icon=None, item=None):
            """Show the main window / bring to front."""
            try:
                import webbrowser
                port = int(os.environ.get('PORT', '8002'))
                webbrowser.open(f"http://localhost:{port}")
            except Exception:
                pass
        
        def stop_server(icon=None, item=None):
            """Stop the server gracefully."""
            logger.info("Stop requested from tray")
            signal.raise_signal(signal.SIGTERM)
        
        menu = pystray.Menu(
            pystray.MenuItem("Open Sentinel Pulse", show_window),
            pystray.MenuItem("─────────────", lambda i, k: None, enabled=False),
            pystray.MenuItem("Start Trading", lambda i, k: _send_ws_command("START_BOT")),
            pystray.MenuItem("Stop Trading", lambda i, k: _send_ws_command("STOP_BOT")),
            pystray.MenuItem("─────────────", lambda i, k: None, enabled=False),
            pystray.MenuItem("Exit", stop_server),
        )
        
        _tray_icon = pystray.Icon("SentinelPulse", icon_image, "Sentinel Pulse", menu)
        threading.Thread(target=_tray_icon.run, daemon=True).start()
        logger.info("System tray icon created")
        
    except ImportError:
        logger.warning("pystray not available - system tray disabled")
    except Exception as e:
        logger.warning(f"System tray setup failed: %s", e)


def _send_ws_command(command: str):
    """Send a WebSocket command to the running server."""
    try:
        import websocket
        port = int(os.environ.get('PORT', '8002'))
        ws = websocket.WebSocket()
        ws.connect(f"ws://localhost:{port}/api/ws")
        ws.send(command)
        ws.close()
    except Exception as e:
        logger.warning(f"Failed to send WS command: {e}")


# ---------------------------------------------------------------------------
# Global Hotkeys (Windows)
# ---------------------------------------------------------------------------

def _setup_global_hotkeys():
    """Register global hotkeys for quick actions."""
    try:
        import keyboard
        
        port = int(os.environ.get('PORT', '8002'))
        
        # Ctrl+Shift+S to toggle trading
        keyboard.add_hotkey('ctrl+shift+s', lambda: _send_ws_command('TOGGLE_BOT'))
        
        # Ctrl+Shift+P to open dashboard
        keyboard.add_hotkey('ctrl+shift+p', lambda: webbrowser.open(f"http://localhost:{port}"))
        
        logger.info("Global hotkeys registered")
        
    except ImportError:
        logger.warning("keyboard not available - global hotkeys disabled")
    except Exception as e:
        logger.warning(f"Global hotkey setup failed: %s", e)


# ---------------------------------------------------------------------------
# Auto-start on Boot
# ---------------------------------------------------------------------------

def _setup_auto_start():
    """Set up auto-start on Windows boot."""
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        else:
            exe_path = str(BASE_DIR / "win_launcher.py")
        
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            try:
                existing = winreg.QueryValueEx(key, "SentinelPulse")[0]
                logger.info("Auto-start already configured")
            except FileNotFoundError:
                winreg.SetValueEx(key, "SentinelPulse", 0, winreg.REG_SZ, exe_path)
                logger.info("Auto-start configured")


def is_auto_start_enabled() -> bool:
    """Check if auto-start is enabled."""
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            try:
                winreg.QueryValueEx(key, "SentinelPulse")
                return True
            except FileNotFoundError:
                return False
    except Exception:
        return False


def enable_auto_start():
    """Enable auto-start on boot."""
    _setup_auto_start()


def disable_auto_start():
    """Disable auto-start on boot."""
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, "SentinelPulse")
                logger.info("Auto-start disabled")
            except FileNotFoundError:
                pass
    except Exception as e:
        logger.warning(f"Failed to disable auto-start: %s", e)


# ---------------------------------------------------------------------------
# Native Notifications (Windows Toast)
# ---------------------------------------------------------------------------

def _send_toast_notification(title: str, message: str):
    """Send a Windows toast notification."""
    try:
        from winotify import Notifier
        notifier = Notifier()
        notifier.show(title=title, msg=message, duration=5)
    except ImportError:
        logger.warning("winotify not available for toast notifications")
    except Exception as e:
        logger.warning(f"Toast notification failed: %s", e)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main():
    port = int(os.environ.get('PORT', '8002'))
    
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    
    logger.info("=" * 50)
    logger.info("  Sentinel Pulse v1.0.0")
    logger.info("  Trading Bot - Starting...")
    logger.info("=" * 50)
    logger.info("")
    
    # Only try to start MongoDB if the executable exists
    mongo_exe = BASE_DIR / 'mongodb' / 'mongod.exe'
    mongo_started = False
    
    if mongo_exe.exists():
        logger.info("MongoDB bundle found, attempting to start...")
        start_mongodb()
        # Wait for MongoDB to be ready
        for _ in range(10):
            if is_port_in_use(27017):
                time.sleep(1)
                mongo_started = True
                break
            time.sleep(0.5)
        if mongo_started:
            logger.info("MongoDB ready")
    else:
        logger.info("MongoDB bundle not found - will run in Demo mode (no persistence)")
    
    logger.info("[Server] Starting on port %d...", port)
    logger.info("")
    
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