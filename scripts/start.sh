#!/bin/bash
# Local development start script (Linux/macOS/Git Bash on Windows)

set -euo pipefail

# Change to project root (one level up from scripts/)
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "========================================"
echo " Udemy Course Enroller - Starting..."
echo "========================================"

# Ensure directories exist
mkdir -p logs Courses data

# Detect OS to determine virtual environment directory layout and binary extension
OS="$(uname -s 2>/dev/null || echo "Unknown")"
case "$OS" in
    CYGWIN*|MINGW*|MSYS*)
        VENV_BIN_DIR="Scripts"
        EXE_EXT=".exe"
        ;;
    *)
        VENV_BIN_DIR="bin"
        EXE_EXT=""
        ;;
esac

# Discover base Python interpreter (>= 3.10)
BASE_PYTHON=""
if [ -n "${PYTHON:-}" ] && ([ -x "$PYTHON" ] || command -v "$PYTHON" &>/dev/null); then
    if "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        BASE_PYTHON="$PYTHON"
    fi
fi

if [ -z "$BASE_PYTHON" ]; then
    CANDIDATES=(
        "$HOME/.local/python3.13/bin/python3.13"
        "$HOME/.local/bin/python3.13"
        "python3.13"
        "python3.12"
        "python3.11"
        "python3.10"
        "python3"
        "python"
    )
    for cand in "${CANDIDATES[@]}"; do
        if ([ -x "$cand" ] || command -v "$cand" &>/dev/null); then
            if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
                BASE_PYTHON="$cand"
                break
            fi
        fi
    done
fi

if [ -z "$BASE_PYTHON" ]; then
    echo "[ERROR] Python 3.10+ interpreter not found. Please install Python 3.10 or higher." >&2
    exit 1
fi

echo "Using Base Python: $($BASE_PYTHON --version 2>&1)"

# Probe virtual environment health
VENV_PYTHON="venv/${VENV_BIN_DIR}/python${EXE_EXT}"
RECREATE_VENV=0

if [ -d "venv" ]; then
    if ! "$VENV_PYTHON" -c "import sys" &>/dev/null; then
        CORRUPT_BAK="venv.broken.$(date +%s).bak"
        echo "[WARN] Existing venv is broken or incompatible. Rotating to ${CORRUPT_BAK}..." >&2
        mv venv "$CORRUPT_BAK"
        RECREATE_VENV=1
    fi
else
    RECREATE_VENV=1
fi

# Create fresh virtual environment if needed
if [ "$RECREATE_VENV" -eq 1 ]; then
    echo "Creating virtual environment using $BASE_PYTHON..."
    if ! "$BASE_PYTHON" -m venv venv; then
        echo "[ERROR] Virtual environment creation failed." >&2
        echo "Ensure 'python3-venv' or 'python3.X-venv' is installed (e.g., 'sudo apt-get install python3-venv')." >&2
        exit 1
    fi
fi

# Activate virtual environment
if [ -f "venv/${VENV_BIN_DIR}/activate" ]; then
    # shellcheck disable=SC1091
    source "venv/${VENV_BIN_DIR}/activate"
fi

hash -r 2>/dev/null || true
VENV_INTERP="$PWD/$VENV_PYTHON"

# Check dependencies with SHA-256 caching
SENTINEL="venv/.requirements.sha256"
CURR_HASH=""
if [ -f "requirements.txt" ]; then
    CURR_HASH=$("$VENV_INTERP" -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' requirements.txt 2>/dev/null || true)
fi

PREV_HASH=""
if [ -f "$SENTINEL" ]; then
    PREV_HASH=$(cat "$SENTINEL" 2>/dev/null || true)
fi

if [ -n "$CURR_HASH" ] && [ "$CURR_HASH" != "$PREV_HASH" ]; then
    echo "Installing/updating dependencies..."
    "$VENV_INTERP" -m pip install --upgrade pip -q --prefer-binary || true
    if ! "$VENV_INTERP" -m pip install -r requirements.txt --prefer-binary; then
        echo "[ERROR] Dependency installation failed." >&2
        exit 1
    fi
    echo "$CURR_HASH" > "$SENTINEL"
fi

# Copy .env.example to .env if missing and restrict permissions
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        chmod 600 .env 2>/dev/null || true
        echo "[INFO] .env created from .env.example"
    fi
fi

echo ""
echo "========================================"
echo " Server starting via run.py"
echo " Press Ctrl+C to stop"
echo "========================================"
echo ""

# Replace process with application runner
exec "$VENV_INTERP" run.py "$@"
