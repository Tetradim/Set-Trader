#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Sentinel Pulse"
DESKTOP_COMMAND_NAME="Sentinel Pulse.command"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"
LOG_FILE="${HOME}/Desktop/Sentinel-Pulse-Local.log"
MONGO_LOG_FILE="${HOME}/Desktop/Sentinel-Pulse-MongoDB.log"
BACKEND_PORT=8001
FRONTEND_PORT=3001
MONGO_PORT=27017
MONGO_DATA_DIR="${HOME}/Library/Application Support/SentinelPulse/mongodb"
INSTALL_DEPS=0
NO_BROWSER=0
LAUNCH=0
PREPARE_ONLY=0
SKIP_MONGO=0

usage() {
  cat <<USAGE
Usage:
  ./install-macos.sh                 Install dependencies and create a Desktop launcher
  ./install-macos.sh --launch        Start ${APP_NAME}

Options:
  --backend-port PORT    FastAPI backend port (default: ${BACKEND_PORT})
  --frontend-port PORT   Vite frontend port (default: ${FRONTEND_PORT})
  --mongo-port PORT      MongoDB port (default: ${MONGO_PORT})
  --mongo-data PATH      MongoDB data path
  --skip-mongo           Require an already-running MongoDB instead of starting one
  --install-deps         Reinstall Python and npm dependencies before launch
  --no-browser           Do not open the browser automatically
  --prepare-only         Install dependencies without starting the app
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --launch) LAUNCH=1 ;;
    --install-deps) INSTALL_DEPS=1 ;;
    --no-browser) NO_BROWSER=1 ;;
    --prepare-only) PREPARE_ONLY=1 ;;
    --skip-mongo) SKIP_MONGO=1 ;;
    --backend-port)
      BACKEND_PORT="${2:?Missing value for --backend-port}"
      shift
      ;;
    --backend-port=*) BACKEND_PORT="${1#*=}" ;;
    --frontend-port)
      FRONTEND_PORT="${2:?Missing value for --frontend-port}"
      shift
      ;;
    --frontend-port=*) FRONTEND_PORT="${1#*=}" ;;
    --mongo-port)
      MONGO_PORT="${2:?Missing value for --mongo-port}"
      shift
      ;;
    --mongo-port=*) MONGO_PORT="${1#*=}" ;;
    --mongo-data)
      MONGO_DATA_DIR="${2:?Missing value for --mongo-data}"
      shift
      ;;
    --mongo-data=*) MONGO_DATA_DIR="${1#*=}" ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
  shift
done

log() {
  mkdir -p "$(dirname "$LOG_FILE")"
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

require_macos() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This installer is intended for macOS." >&2
    exit 1
  fi
}

find_python() {
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)
PY
    then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

require_node() {
  command -v node >/dev/null 2>&1 || {
    echo "Node.js is required. Install Node.js 20+ from https://nodejs.org/ or Homebrew." >&2
    exit 1
  }
  command -v npm >/dev/null 2>&1 || {
    echo "npm is required with Node.js." >&2
    exit 1
  }
}

prepare_runtime() {
  local python_bin
  python_bin="$(find_python)" || {
    echo "Python 3.11, 3.12, or 3.13 is required." >&2
    exit 1
  }
  require_node

  local venv_dir="${BACKEND_DIR}/.venv"
  local venv_python="${venv_dir}/bin/python"
  if [[ ! -x "$venv_python" ]]; then
    log "Creating backend virtual environment"
    "$python_bin" -m venv "$venv_dir"
    INSTALL_DEPS=1
  fi

  if [[ "$INSTALL_DEPS" -eq 1 || ! -d "${venv_dir}/lib" ]]; then
    log "Installing backend dependencies"
    "$venv_python" -m pip install --upgrade pip
    "$venv_python" -m pip install --retries 10 --timeout 180 --prefer-binary -r "${BACKEND_DIR}/requirements.txt"
  fi

  if [[ "$INSTALL_DEPS" -eq 1 || ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    log "Installing frontend dependencies"
    (cd "$FRONTEND_DIR" && npm install)
  fi
}

create_desktop_launcher() {
  local desktop_dir="${HOME}/Desktop"
  local command_path="${desktop_dir}/${DESKTOP_COMMAND_NAME}"
  mkdir -p "$desktop_dir"
  cat > "$command_path" <<EOF
#!/usr/bin/env bash
cd "$ROOT_DIR"
exec "$ROOT_DIR/install-macos.sh" --launch
EOF
  chmod +x "$command_path"
  log "Desktop launcher created: ${command_path}"
}

port_open() {
  nc -z 127.0.0.1 "$1" >/dev/null 2>&1
}

wait_port() {
  local port="$1"
  local seconds="${2:-30}"
  local start
  start="$(date +%s)"
  while (( "$(date +%s)" - start < seconds )); do
    if port_open "$port"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_url() {
  local url="$1"
  local seconds="${2:-60}"
  local start
  start="$(date +%s)"
  while (( "$(date +%s)" - start < seconds )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_mongo() {
  if port_open "$MONGO_PORT"; then
    log "Using existing MongoDB on port ${MONGO_PORT}"
    return 0
  fi
  if [[ "$SKIP_MONGO" -eq 1 ]]; then
    echo "MongoDB is not running on port ${MONGO_PORT}." >&2
    exit 1
  fi
  command -v mongod >/dev/null 2>&1 || {
    echo "MongoDB is required. Install with: brew tap mongodb/brew && brew install mongodb-community" >&2
    exit 1
  }
  mkdir -p "$MONGO_DATA_DIR" "$(dirname "$MONGO_LOG_FILE")"
  log "Starting MongoDB on port ${MONGO_PORT}"
  mongod --dbpath "$MONGO_DATA_DIR" --bind_ip 127.0.0.1 --port "$MONGO_PORT" >> "$MONGO_LOG_FILE" 2>&1 &
  MONGO_PID=$!
  if ! wait_port "$MONGO_PORT" 45; then
    log "MongoDB did not become ready. Recent MongoDB log output:"
    tail -n 80 "$MONGO_LOG_FILE" || true
    exit 1
  fi
}

launch_app() {
  prepare_runtime
  if [[ "$PREPARE_ONLY" -eq 1 ]]; then
    log "Preparation complete"
    return 0
  fi

  local backend_url="http://127.0.0.1:${BACKEND_PORT}"
  local frontend_url="http://127.0.0.1:${FRONTEND_PORT}"
  local venv_python="${BACKEND_DIR}/.venv/bin/python"
  local pids=()
  MONGO_PID=""

  start_mongo
  [[ -n "${MONGO_PID:-}" ]] && pids+=("$MONGO_PID")

  export MONGO_URL="mongodb://127.0.0.1:${MONGO_PORT}"
  log "Starting backend on ${backend_url}"
  (cd "$BACKEND_DIR" && "$venv_python" -m uvicorn server:app --host 127.0.0.1 --port "$BACKEND_PORT" --reload) >> "$LOG_FILE" 2>&1 &
  pids+=("$!")

  log "Starting frontend on ${frontend_url}"
  (cd "$FRONTEND_DIR" && VITE_BACKEND_URL="$backend_url" npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT") >> "$LOG_FILE" 2>&1 &
  pids+=("$!")

  cleanup() {
    for pid in "${pids[@]}"; do
      kill "$pid" >/dev/null 2>&1 || true
    done
  }
  trap cleanup EXIT INT TERM

  if ! wait_url "${backend_url}/api/health" 90; then
    log "Backend did not become healthy. Recent log output:"
    tail -n 100 "$LOG_FILE" || true
    exit 1
  fi
  if ! wait_url "$frontend_url" 90; then
    log "Frontend did not become ready. Recent log output:"
    tail -n 100 "$LOG_FILE" || true
    exit 1
  fi

  log "Ready: ${frontend_url}"
  if [[ "$NO_BROWSER" -eq 0 ]]; then
    open "$frontend_url"
  fi
  wait "${pids[@]}"
}

require_macos
if [[ "$LAUNCH" -eq 1 ]]; then
  launch_app
else
  INSTALL_DEPS=1
  PREPARE_ONLY=1
  prepare_runtime
  create_desktop_launcher
  log "Install complete. Double-click '${DESKTOP_COMMAND_NAME}' on the Desktop to start ${APP_NAME}."
fi
