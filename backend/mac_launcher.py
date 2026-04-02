"""
mac_launcher.py — Sentinel Pulse macOS entry point.

Responsibilities:
  1. Start the bundled mongod process
  2. Start the FastAPI server (uvicorn) in a background thread
  3. Wait for both services to be ready
  4. Open the dashboard in the user's default browser
  5. Show a minimal tkinter status window so non-technical users
     can see what's happening and quit cleanly
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _base() -> Path:
    """Directory that contains our bundled executables and data."""
    if getattr(sys, "frozen", False):
        # PyInstaller: executable lives in  SentinelPulse.app/Contents/MacOS/
        return Path(sys.executable).resolve().parent
    # Dev / test run from repo root
    return Path(__file__).resolve().parent


def _data() -> Path:
    """Per-user data directory (MongoDB files, logs).  Created on first run."""
    d = Path.home() / "Library" / "Application Support" / "SentinelPulse"
    (d / "db").mkdir(parents=True, exist_ok=True)
    (d / "logs").mkdir(parents=True, exist_ok=True)
    return d


BASE = _base()
DATA = _data()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _port_open(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_port(port: int, timeout: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(port):
            return True
        time.sleep(0.4)
    return False


# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------

_mongod_proc: subprocess.Popen | None = None


def _start_mongodb(status) -> bool:
    global _mongod_proc

    mongod = BASE / "mongod"
    if not mongod.exists():
        status("MongoDB binary not found — cannot start database.")
        return False

    # Remove macOS quarantine flag that blocks unsigned binaries
    try:
        subprocess.run(["xattr", "-d", "com.apple.quarantine", str(mongod)],
                       capture_output=True)
    except Exception:
        pass
    mongod.chmod(0o755)

    if _port_open(27017):
        status("Database already running.")
        return True

    log_file = DATA / "logs" / "mongod.log"
    status("Starting database…")
    _mongod_proc = subprocess.Popen(
        [
            str(mongod),
            "--dbpath",  str(DATA / "db"),
            "--logpath", str(log_file),
            "--port",    "27017",
            "--bind_ip", "127.0.0.1",
            "--quiet",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if _wait_port(27017, timeout=30):
        status("Database ready.")
        return True

    status("Database failed to start. See logs in ~/Library/Application Support/SentinelPulse/logs/")
    return False


# ---------------------------------------------------------------------------
# FastAPI / uvicorn
# ---------------------------------------------------------------------------

def _start_server(status) -> bool:
    # Inject env vars before importing server (server.py reads them at import time)
    os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
    os.environ.setdefault("DB_NAME",   "sentinel_pulse")
    os.environ.setdefault("CORS_ORIGINS", "http://localhost:8001,http://127.0.0.1:8001")

    # Add BASE to sys.path so local modules are importable when frozen
    if str(BASE) not in sys.path:
        sys.path.insert(0, str(BASE))

    status("Starting web server…")

    def _run():
        try:
            import uvicorn
            from server import app  # full import — PyInstaller traces all deps
            uvicorn.run(
                app,
                host="127.0.0.1",
                port=8001,
                log_level="warning",
                access_log=False,
            )
        except Exception as exc:
            print(f"[server] fatal: {exc}", file=sys.stderr)

    thread = threading.Thread(target=_run, name="uvicorn", daemon=True)
    thread.start()

    if _wait_port(8001, timeout=45):
        status("Web server ready.")
        return True

    status("Web server failed to start.")
    return False


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

def _shutdown(*_):
    global _mongod_proc
    if _mongod_proc and _mongod_proc.poll() is None:
        _mongod_proc.terminate()
        try:
            _mongod_proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _mongod_proc.kill()
    sys.exit(0)


# ---------------------------------------------------------------------------
# UI — tkinter status window
# ---------------------------------------------------------------------------

def _run_ui():
    """Minimal status window that shows startup progress and a Quit button."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        _run_headless()
        return

    root = tk.Tk()
    root.title("Sentinel Pulse")
    root.geometry("440x210")
    root.resizable(False, False)
    root.configure(bg="#0f172a")
    root.eval("tk::PlaceWindow . center")

    # -- Title --
    tk.Label(root, text="Sentinel Pulse",
             font=("Helvetica Neue", 20, "bold"),
             fg="#818cf8", bg="#0f172a").pack(pady=(22, 2))
    tk.Label(root, text="Automated Trading Bot  ·  Signal Forge Laboratory",
             font=("Helvetica Neue", 10),
             fg="#475569", bg="#0f172a").pack()

    # -- Status line --
    status_var = tk.StringVar(value="Initialising…")
    tk.Label(root, textvariable=status_var,
             font=("Helvetica Neue", 11),
             fg="#cbd5e1", bg="#0f172a").pack(pady=(14, 6))

    # -- Progress bar --
    sty = ttk.Style(root)
    sty.theme_use("default")
    sty.configure("SP.Horizontal.TProgressbar",
                  troughcolor="#1e293b", background="#6366f1", thickness=5)
    bar = ttk.Progressbar(root, style="SP.Horizontal.TProgressbar",
                          mode="indeterminate", length=360)
    bar.pack()
    bar.start(10)

    # -- Quit button (shown only after startup) --
    quit_btn = tk.Button(
        root, text="Quit Sentinel Pulse",
        font=("Helvetica Neue", 11),
        fg="#64748b", bg="#1e293b",
        activeforeground="#f87171", activebackground="#1e293b",
        relief="flat", bd=0, padx=16, pady=6, cursor="hand2",
    )

    def _status(msg: str):
        root.after(0, lambda: status_var.set(msg))

    def _on_ready():
        bar.stop()
        bar.configure(mode="determinate", value=100)
        status_var.set("Running — dashboard open in your browser.")
        quit_btn.configure(command=lambda: (_shutdown(), root.destroy()))
        quit_btn.pack(pady=(16, 0))
        root.after(8000, root.iconify)  # minimize after 8 s

    def _on_fail():
        bar.stop()
        status_var.set("Startup failed. See ~/Library/Application Support/SentinelPulse/logs/")
        tk.Label(root, text="You can close this window.",
                 font=("Helvetica Neue", 10), fg="#475569", bg="#0f172a").pack(pady=4)

    def _start():
        if not _start_mongodb(_status):
            root.after(0, _on_fail)
            return
        if not _start_server(_status):
            root.after(0, _on_fail)
            return
        root.after(0, _on_ready)
        threading.Thread(
            target=lambda: (time.sleep(1.2), webbrowser.open("http://127.0.0.1:8001")),
            daemon=True,
        ).start()

    threading.Thread(target=_start, daemon=True).start()
    root.protocol("WM_DELETE_WINDOW", lambda: (_shutdown(), root.destroy()))
    signal.signal(signal.SIGTERM, lambda *_: (_shutdown(), root.destroy()))
    root.mainloop()


# ---------------------------------------------------------------------------
# Headless fallback (if tkinter is unavailable)
# ---------------------------------------------------------------------------

def _run_headless():
    print("Sentinel Pulse starting (headless mode)…")
    if not _start_mongodb(print):
        sys.exit(1)
    if not _start_server(print):
        sys.exit(1)
    time.sleep(1)
    webbrowser.open("http://127.0.0.1:8001")
    print("Dashboard open at http://127.0.0.1:8001")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _shutdown()


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _shutdown)
    _run_ui()
