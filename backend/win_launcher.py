"""
Windows entry point for Sentinel Pulse.

Starts the FastAPI server, optionally launches MongoDB, and opens browser automatically.
Features:
- System tray icon with context menu
- Global hotkeys for quick actions
- Auto-start option on system boot
- Native Windows notifications
- Self-update from GitHub Releases
"""
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
import shutil
import json
from pathlib import Path

# Current version - match setup.iss MyAppVersion
CURRENT_VERSION = "1.0.0"
UPDATE_REPO = "Tetradim/Sentinel-Pulse"
UPDATE_URL = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
INSTALLER_ASSET_PREFIXES = (
    "SentinelPulse-Beta-Setup-",
    "SentinelPulse-Setup-",
)

# Set Windows console to UTF-8 mode BEFORE any other imports
if sys.platform == 'win32':
    try:
        # Try to set console code page to UTF-8 (65001)
        os.system('chcp 65001 > NUL 2>&1')
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent

def get_default_mongo_data_dir() -> Path:
    """Return the machine-level MongoDB dbpath used by the Windows launcher."""
    drive = os.environ.get("SystemDrive", "C:")
    return Path(f"{drive}\\") / "data" / "db"


def get_log_path():
    """Return the easy-access desktop log used for launcher and backend logs."""
    desktop = Path.home() / "Desktop"
    try:
        desktop.mkdir(parents=True, exist_ok=True)
        return desktop / "Sentinel-Pulse.log"
    except Exception:
        return BASE_DIR / "Sentinel-Pulse.log"


# DATA_DIR for MongoDB database storage
DATA_DIR = get_default_mongo_data_dir()
os.environ.setdefault("LOG_FILE", str(get_log_path()))

sys.path.insert(0, str(BASE_DIR))

# Set up logger with UTF-8 encoding for console
def _get_stream_handler():
    import sys
    # stdout may not be initialized at import time; stderr may be None in --noconsole exe
    stream = sys.stderr if sys.stderr is not None else sys.stdout
    if stream is None:
        # Frozen --noconsole exe: no console attached, skip stream handler
        return logging.NullHandler()
    try:
        stream.reconfigure(errors='replace')
    except Exception:
        pass
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    return handler

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(str(get_log_path()), encoding="utf-8-sig"),
        _get_stream_handler()
    ]
)
logger = logging.getLogger("SentinelPulse")

# Simple file logger for debugging packaged app (on desktop for easy access)
try:
    log_file = get_log_path()
    
    # Use utf-8-sig to add BOM for Windows Notepad compatibility
    fh = logging.FileHandler(str(log_file), encoding="utf-8-sig")
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(fh)
    logger.info("=== Launcher PID: %d, Log: %s ===", os.getpid(), log_file)
except Exception as e:
    logger.warning("Log file failed: %s", e)


# Optional MongoDB process
_mongo_process = None
_tray_icon = None
_app = None


def is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect(('127.0.0.1', port))
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


def check_for_update():
    """Check for updates from GitHub Releases and self-update if newer version available."""
    import urllib.request
    import zipfile
    import io
    from packaging import version
    
    try:
        # Skip update check if not a frozen exe
        if not getattr(sys, 'frozen', False):
            return False, None
            
        # Request latest release info
        req = urllib.request.Request(UPDATE_URL)
        req.add_header('User-Agent', f'SentinelPulse/{CURRENT_VERSION}')
        req.add_header('Accept', 'application/vnd.github.v3+json')
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            release_data = json.loads(resp.read().decode('utf-8'))
        
        latest_version = release_data.get('tag_name', '').lstrip('v')
        current_ver = version.parse(CURRENT_VERSION)
        latest_ver = version.parse(latest_version)
        
        if latest_ver > current_ver:
            logger.info(f"Update available: {CURRENT_VERSION} → {latest_version}")
            
            # Find the source zip asset
            zip_url = None
            source_link = None
            for asset in release_data.get('assets', []):
                asset_name = asset.get('name', '').lower()
                # Look for source zip or the portable folder
                if 'source' in asset_name and asset_name.endswith('.zip'):
                    zip_url = asset.get('browser_download_url')
                    break
            
            # Fallback: download the exe directly
            if not zip_url:
                for installer_prefix in INSTALLER_ASSET_PREFIXES:
                    for asset in release_data.get('assets', []):
                        asset_name = asset.get('name', '')
                        if asset_name.startswith(installer_prefix) and asset_name.endswith('.exe'):
                            exe_url = asset.get('browser_download_url')
                            # Download exe to temp location
                            temp_exe = BASE_DIR / f"SentinelPulse_{latest_version}.exe.new"
                            logger.info(f"Downloading update...")
                            urllib.request.urlretrieve(exe_url, str(temp_exe))

                            # Rename current to .old, new to current
                            current_exe = sys.executable
                            old_exe = sys.executable + '.old'

                            # Replace on next startup - create marker
                            marker = BASE_DIR / 'update_pending.txt'
                            with open(marker, 'w') as f:
                                f.write(f"{latest_version}\n{current_exe}\n{old_exe}\n{temp_exe}")

                            logger.info(f"Update downloaded. Will apply on restart.")
                            return True, latest_version
            
            # Source zip approach - extract and replace files
            if zip_url:
                logger.info(f"Downloading source package...")
                zip_path = BASE_DIR / f"update_{latest_version}.zip"
                urllib.request.urlretrieve(zip_url, str(zip_path))
                
                # Extract to temp location
                extract_dir = BASE_DIR / f"update_{latest_version}"
                with zipfile.ZipFile(str(zip_path), 'r') as zf:
                    zf.extractall(str(extract_dir))
                
                # Create marker for post-restart apply
                marker = BASE_DIR / 'update_pending.txt'
                with open(marker, 'w') as f:
                    f.write(f"{latest_version}\n{extract_dir}\n")
                
                logger.info(f"Update extracted to {extract_dir}. Will apply on restart.")
                return True, latest_ver
            
    except ImportError:
        # packaging not installed, skip version check
        pass
    except Exception as e:
        logger.info(f"Update check failed: {e}")
    
    return False, None


def apply_pending_update():
    """Apply any pending update from previous session."""
    marker = BASE_DIR / 'update_pending.txt'
    if not marker.exists():
        return
    
    try:
        with open(marker, 'r') as f:
            lines = [l.strip() for l in f.readlines()]
        
        new_version = lines[0]
        logger.info(f"Applying update to v{new_version}...")
        
        if len(lines) >= 4:
            # Direct exe replacement
            temp_exe = Path(lines[3])
            current_exe = Path(lines[1])
            old_exe = Path(lines[2])
            
            if temp_exe.exists():
                # Swap: current → old, temp → current
                if old_exe.exists():
                    old_exe.unlink()
                current_exe.rename(old_exe)
                temp_exe.rename(current_exe)
                logger.info(f"Update applied: {current_exe.name}")
        
        elif len(lines) >= 2:
            # Source zip extraction
            extract_dir = Path(lines[1])
            if extract_dir.exists():
                # Move all files from extract_dir to BASE_DIR
                for src in extract_dir.rglob('*'):
                    if src.is_file():
                        dest = BASE_DIR / src.relative_to(extract_dir)
                        if dest.exists():
                            dest.unlink()
                        shutil.move(str(src), str(dest))
                # Cleanup
                shutil.rmtree(extract_dir)
                logger.info(f"Update applied from {extract_dir}")
        
        # Clear marker
        marker.unlink()
        logger.info(f"Update to v{new_version} complete!")
        
    except Exception as e:
        logger.info(f"Update apply failed: {e}")


def start_mongodb():
    """Start MongoDB from bundled location."""
    mongo_exe = BASE_DIR / 'mongodb' / 'mongod.exe'
    if mongo_exe.exists():
        start_mongodb_path(mongo_exe)
    else:
        logger.error("MongoDB not found - Sentinel Pulse requires MongoDB")
        logger.error("Please install MongoDB or bundle it with the app")
        sys.exit(1)


def start_mongodb_path(mongo_exe: Path):
    """Start MongoDB from a specific path."""
    global _mongo_process
    
    # Check if MongoDB already running
    if is_port_in_use(27017):
        logger.info("MongoDB already running on port 27017")
        return
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Preparing MongoDB working directory: %s", mongo_exe.parent)
    time.sleep(3)
    logger.info("Starting MongoDB from: %s", mongo_exe)
    _mongo_process = subprocess.Popen(
        [str(mongo_exe), "--dbpath", str(DATA_DIR)],
        cwd=str(mongo_exe.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    )
    # Wait for MongoDB to start; check every 3 seconds, 3 times.
    for attempt in range(1, 4):
        time.sleep(3)
        if is_port_in_use(27017):
            logger.info("MongoDB started on check %d of 3", attempt)
            return
        logger.warning("MongoDB port 27017 not open yet; check %d of 3", attempt)
    logger.error("MongoDB failed to start")


def wait_for_server(port: int, timeout: int = 30) -> bool:
    """Wait for the server to be ready to accept connections."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_in_use(port):
            # Give server a moment to fully initialize
            time.sleep(0.5)
            return True
        time.sleep(0.5)
    return False


def open_browser():
    """Open the dashboard in the default browser."""
    import webbrowser
    import os
    if os.environ.get("SENTINEL_OPEN_BROWSER", "1").lower() in {"0", "false", "no"}:
        logger.info("Browser auto-open suppressed by SENTINEL_OPEN_BROWSER")
        return
    port = int(os.environ.get("PORT", "8002"))
    webbrowser.open(f"http://127.0.0.1:{port}")


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
    logger.info(f"Sentinel Pulse v{CURRENT_VERSION}")
    logger.info("=" * 50)
    logger.info("")
    
    # First, apply any pending update from previous session
    apply_pending_update()
    
    # Check for updates (non-blocking)
    try:
        update_needed, new_version = check_for_update()
        if update_needed:
            logger.info(f"Update to v{new_version} downloaded. Restart to apply.")
            # Don't exit - continue running and apply on next restart
    except Exception as e:
        logger.info(f"Update check skipped: {e}")
    
    # MongoDB is required - check for bundled, system MongoDB, or running instance
    mongo_exe = BASE_DIR / "mongodb" / "mongod.exe"
    
    # Check system MongoDB locations
    system_mongo_paths = [
        Path(r"C:\Program Files\MongoDB\Server\8.2\bin\mongod.exe"),
        Path(r"C:\Program Files\MongoDB\Server\8.0\bin\mongod.exe"),
        Path(r"C:\Program Files\MongoDB\Server\7.0\bin\mongod.exe"),
        Path(r"C:\Program Files (x86)\MongoDB\Server\8.2\bin\mongod.exe"),
    ]
    
    mongo_running = check_mongo_running()
    
    if mongo_exe.exists():
        logger.info("Using bundled MongoDB...")
        start_mongodb()
    elif any(p.exists() for p in system_mongo_paths):
        logger.info("Using system MongoDB...")
        # System MongoDB is installed and running - just verify connection
        if not mongo_running:
            # Try to start system MongoDB
            for mongo_path in system_mongo_paths:
                if mongo_path.exists():
                    logger.info("Starting system MongoDB from: %s", mongo_path)
                    start_mongodb_path(mongo_path)
                    break
        else:
            logger.info("System MongoDB already running")
    elif mongo_running:
        logger.info("MongoDB already running (detected via tasklist)")
    else:
        logger.error("MongoDB not found - please install MongoDB or bundle mongod.exe")
        logger.error("Download from: https://www.mongodb.com/try/download/community")
        sys.exit(1)
    
    import uvicorn
    from server import app
    
    def run_server():
        try:
            uvicorn.run(
                app, 
                host="0.0.0.0", 
                port=port, 
                log_config=None,
            )
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
        finally:
            stop_mongodb()
            logger.info("[Sentinel Pulse] Server stopped")
    
    server_thread = threading.Thread(target=run_server)
    server_thread.start()
    
    # Wait for server to be ready before opening browser
    if not wait_for_server(port):
        logger.warning("Server may not be ready, opening browser anyway...")
    
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    # Wait for server thread to complete (blocks until server stops)
    server_thread.join()


if __name__ == "__main__":
    main()
