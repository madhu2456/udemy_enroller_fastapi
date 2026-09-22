#!/bin/bash
# Coupon Checker Script (one-shot)
#
# Local:
#   ./scripts/coupon_checker.sh
#
# Production (Docker one-shot, without waiting for the loop):
#   docker compose exec -T coupon-checker python -u scripts/coupon_checker.py
#   # or against the web container:
#   docker compose exec -T web python -u scripts/coupon_checker.py
#
# Continuous every 2h on server: use the docker-compose ``coupon-checker`` service
# (scripts/coupon_checker_loop.py). See README "Validating Expired Coupons".

set -euo pipefail

# Change to project root (one level up from scripts/)
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "=========================================="
echo "    Udemy Course Enroller - Coupon Checker"
echo "=========================================="

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

# Prefer healthy venv or .venv when present
RUN_PYTHON=""
for venv_dir in "venv" ".venv"; do
    cand_py="${venv_dir}/${VENV_BIN_DIR}/python${EXE_EXT}"
    if [ -f "$cand_py" ] && "$cand_py" -c "import sys" &>/dev/null; then
        echo "Activating virtual environment ($venv_dir)..."
        # shellcheck disable=SC1091
        if [ -f "${venv_dir}/${VENV_BIN_DIR}/activate" ]; then
            source "${venv_dir}/${VENV_BIN_DIR}/activate"
        fi
        hash -r 2>/dev/null || true
        RUN_PYTHON="$cand_py"
        break
    fi
done

# Fall back to container / system environment if no venv was found
if [ -z "$RUN_PYTHON" ]; then
    CANDIDATES=()
    if [ -n "${PYTHON:-}" ]; then
        CANDIDATES+=("$PYTHON")
    fi
    CANDIDATES+=(
        "python3.13"
        "python3.12"
        "python3.11"
        "python3"
        "python"
    )
    for cand in "${CANDIDATES[@]}"; do
        if ([ -x "$cand" ] || command -v "$cand" &>/dev/null); then
            if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
                RUN_PYTHON="$cand"
                break
            fi
        fi
    done
fi

if [ -z "$RUN_PYTHON" ]; then
    echo "[ERROR] Python 3.10+ interpreter not found." >&2
    exit 1
fi

echo "Starting coupon validation..."
echo "  PUBLIC_DEALS_PATH=${PUBLIC_DEALS_PATH:-<project root public_deals.json>}"
exec "$RUN_PYTHON" -u scripts/coupon_checker.py "$@"
