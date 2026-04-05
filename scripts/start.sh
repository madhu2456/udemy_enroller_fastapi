#!/bin/bash
# Local development start script (Linux/macOS/Git Bash on Windows)

set -e

# Change to project root (one level up from scripts/)
cd "$(dirname "$0")/.."

echo "========================================"
echo " Udemy Course Enroller - Starting..."
echo "========================================"

# Create directories
mkdir -p logs Courses

# Detect Python command (python3 or python)
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "[ERROR] Python not found. Install Python 3.10+ first."
    exit 1
fi

echo "Using Python: $($PYTHON --version)"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv venv 2>/dev/null || {
        # On Debian/Ubuntu if python3-venv is missing, try installing deps globally
        echo "[WARN] venv creation failed — falling back to global pip install."
        $PYTHON -m pip install -r requirements.txt
        echo "Starting server (no venv)..."
        $PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
        exit 0
    }
fi

# Activate venv (works on Linux/macOS and Git Bash on Windows)
if [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate   # Git Bash / Windows
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate       # Linux / macOS
fi

# Upgrade pip
$PYTHON -m pip install --upgrade pip -q

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt -q

# Copy .env.example to .env if .env doesn't exist
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[INFO] .env created from .env.example"
fi

echo ""
echo "========================================"
echo " Server starting at http://localhost:8000"
echo " Press Ctrl+C to stop"
echo "========================================"
echo ""

# Run the application
$PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
