# sentinel_win.spec
# PyInstaller spec for Windows .exe
# Run from the backend/ directory:
#   pyinstaller sentinel_win.spec

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
from pathlib import Path

block_cipher = None

# ---- Collect dynamic/data-heavy packages --------------------------------

def _gather(pkg):
    d, b, h = collect_all(pkg)
    return d, b, h

pymongo_d, pymongo_b, pymongo_h = _gather("pymongo")
bson_d,    bson_b,    bson_h    = _gather("bson")
motor_d,   motor_b,   motor_h   = _gather("motor")
yf_d,      yf_b,      yf_h      = _gather("yfinance")
ta_d,      ta_b,      ta_h      = _gather("ta")
tg_d,      tg_b,      tg_h      = _gather("telegram")
pd_d,      pd_b,      pd_h      = _gather("pandas")

a = Analysis(
    ["win_launcher.py"],
    pathex=["."],          # run from backend/
    binaries=[
        # Bundled MongoDB — only if mongod exists (macOS typically)
        *([("mongod", ".")] if Path("mongod").exists() else []),
        *pymongo_b,
        *bson_b,
    ],
    datas=[
        # Built React app (served by FastAPI as static files)
        ("static",     "static"),
        # All local Python modules that server.py imports
        ("routes",     "routes"),
        ("brokers",    "brokers"),
        ("strategies", "strategies"),
        # Individual files
        ("server.py",          "."),
        ("deps.py",            "."),
        ("schemas.py",         "."),
        ("trading_engine.py",  "."),
        ("broker_manager.py",  "."),
        ("price_service.py",   "."),
        ("resilience.py",      "."),
        ("markets.py",         "."),
        ("audit_service.py",   "."),
        ("telegram_service.py","." ),
        ("email_service.py",   "."),
        ("ws_manager.py",      "."),
        ("telemetry.py",       "."),
        # Env — overridden at runtime by mac_launcher but kept as fallback
        (".env.mac",   ".env"),
        *pymongo_d,
        *bson_d,
        *motor_d,
        *yf_d,
        *ta_d,
        *tg_d,
        *pd_d,
    ],
    hiddenimports=[
        # uvicorn internals (not auto-detected)
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # starlette / fastapi
        "starlette",
        "starlette.middleware",
        "starlette.middleware.cors",
        "starlette.staticfiles",
        "starlette.responses",
        "fastapi",
        "fastapi.middleware.cors",
        # pydantic (required by strategies)
        "pydantic",
        "pydantic._internal",
        "pydantic.main",
        "pydantic.fields",
        # motor / pymongo
        *pymongo_h,
        *bson_h,
        *motor_h,
        # data / analysis
        *yf_h,
        *ta_h,
        *pd_h,
        # telegram
        *tg_h,
        # resilience
        "aiolimiter",
        # watchdog (strategy hot-reload)
        "watchdog",
        "watchdog.observers",
        "watchdog.events",
        "watchdog.observers.fsevents",   # macOS-native backend
        # opentelemetry
        "opentelemetry",
        "opentelemetry.sdk.trace",
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        # misc
        "dotenv",
        "python_dotenv",
        "multipart",
        "email_validator",
        "zoneinfo",
        "tkinter",
        "tkinter.ttk",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "matplotlib", "IPython", "jupyter", "notebook",
        "scipy", "sklearn", "torch", "tensorflow",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SentinelPulse",
    debug=False,
    strip=False,
    upx=False,          # skip UPX — macOS notarization dislikes it
    console=False,      # no terminal window — we use tkinter
    disable_windowed_traceback=False,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="SentinelPulse",
)

app = BUNDLE(
    coll,
    name="SentinelPulse.app",
    # icon="SentinelPulse.icns",   # uncomment when icon file is present
    bundle_identifier="com.signalforgelab.sentinelpulse",
    info_plist={
        "CFBundleName":             "Sentinel Pulse",
        "CFBundleDisplayName":      "Sentinel Pulse",
        "CFBundleVersion":          "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSPrincipalClass":         "NSApplication",
        "NSHighResolutionCapable":  True,
        "LSMinimumSystemVersion":   "12.0",
        "LSUIElement":              False,   # show in Dock
        "NSAppleEventsUsageDescription":
            "Sentinel Pulse uses Apple Events to open your browser.",
        "NSLocalNetworkUsageDescription":
            "Sentinel Pulse runs a local web server for its dashboard.",
    },
)
