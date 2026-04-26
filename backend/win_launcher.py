"""
Windows entry point for Sentinel Pulse.

Starts the FastAPI server, optionally launches MongoDB, and opens browser automatically.
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
from pathlib import Path

# Add the app directory to path
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent

sys.path.insert(0, str(BASE_DIR))

# Optional MongoDB process
_mongo_process = None


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
    
    # Check if MongoDB is already running
    if check_mongo_running() or is_port_in_use(27017):
        print("[MongoDB] Already running on port 27017")
        return
    
    # Create data directory if needed
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Start MongoDB
    print("[MongoDB] Starting on port 27017...")
    log_file = BASE_DIR / 'logs' / 'mongod.log'
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        _mongo_process = subprocess.Popen(
            [
                str(mongo_exe),
                '--dbpath', str(data_dir),
                '--port', '27017',
                '--logpath', str(log_file),
                '--quiet'
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        print("[MongoDB] Started successfully")
    except Exception as e:
        print(f"[MongoDB] Failed to start: {e}")
        print("[MongoDB] Continuing without bundled MongoDB...")


def stop_mongodb():
    """Stop the bundled MongoDB instance."""
    global _mongo_process
    if _mongo_process:
        print("[MongoDB] Stopping...")
        try:
            _mongo_process.terminate()
            _mongo_process.wait(timeout=5)
        except Exception:
            try:
                _mongo_process.kill()
            except Exception:
                pass
        print("[MongoDB] Stopped")


def graceful_shutdown(signum, frame):
    """Handle graceful shutdown on Ctrl+C / SIGTERM."""
    print("\n[Sentinel Pulse] Shutting down gracefully...")
    stop_mongodb()
    sys.exit(0)


def open_browser():
    """Open browser after a short delay."""
    time.sleep(2)
    port = int(os.environ.get('PORT', '8002'))
    webbrowser.open(f"http://localhost:{port}")


def main():
    port = int(os.environ.get('PORT', '8002'))
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    
    print("=" * 50)
    print("  Sentinel Pulse v1.0.0")
    print("  Trading Bot - Starting...")
    print("=" * 50)
    print()
    
    # Start MongoDB if bundled
    mongo_exe = BASE_DIR / 'mongodb' / 'mongod.exe'
    if mongo_exe.exists():
        start_mongodb()
    
    # Wait for MongoDB to be ready
    if mongo_exe.exists():
        for _ in range(10):
            if is_port_in_use(27017):
                time.sleep(1)
                break
            time.sleep(0.5)
    
    print(f"[Server] Starting on port {port}...")
    print()
    
    # Start browser in background
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    # Run the server with explicit logging config
    import logging
    logging.basicConfig(level=logging.INFO)
    
    import uvicorn
    from server import app
    
    try:
        uvicorn.run(
            app, 
            host="0.0.0.0", 
            port=port, 
            log_config=None  # Use default uvicorn logging
        )
    finally:
        # Cleanup on server stop
        stop_mongodb()
        print("[Sentinel Pulse] Server stopped")


if __name__ == "__main__":
    main()