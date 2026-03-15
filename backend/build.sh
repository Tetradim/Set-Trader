#!/bin/bash
# Build script for macOS/Linux
# Run this from the bracket-bot directory

set -e

echo "========================================"
echo "Bracket Bot - Build Script"
echo "========================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python not found. Please install Python 3.11+"
    exit 1
fi

# Check Node
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js not found. Please install Node.js 20+"
    exit 1
fi

echo "[1/5] Installing Python dependencies..."
cd backend
pip3 install -r requirements.txt
pip3 install pyinstaller

echo ""
echo "[2/5] Building Python backend..."
pyinstaller --onefile --name bracket-bot-server main.py
cd ..

echo ""
echo "[3/5] Installing frontend dependencies..."
cd frontend
npm install

echo ""
echo "[4/5] Building frontend..."
npm run build
cd ..

echo ""
echo "[5/5] Building Electron app..."
cd desktop
npm install

if [[ "$OSTYPE" == "darwin"* ]]; then
    npm run dist:mac
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    npm run dist:linux
else
    npm run dist:win
fi
cd ..

echo ""
echo "========================================"
echo "Build complete!"
echo ""
echo "Output files in: desktop/dist/"
echo "========================================"
