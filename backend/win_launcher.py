"""
Windows entry point for Sentinel Pulse.

Starts the FastAPI server and opens browser automatically.
"""
import asyncio
import os
import sys
import webbrowser
import threading
import time
from pathlib import Path

# Add the app directory to path
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent

sys.path.insert(0, str(BASE_DIR))

# Import and run the server
import uvicorn
from server import app


def open_browser():
    """Open browser after a short delay."""
    time.sleep(2)
    port = int(os.environ.get('PORT', '8002'))
    webbrowser.open(f"http://localhost:{port}")


def main():
    port = int(os.environ.get('PORT', '8002'))
    
    print(f"Starting Sentinel Pulse on port {port}...")
    
    # Start browser in background
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()