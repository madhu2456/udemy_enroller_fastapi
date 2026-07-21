#!/bin/bash
set -e
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

echo "=========================================="
echo "    Udemy Course Enroller - Coupon Checker"
echo "=========================================="

cd "$(dirname "$0")/.."

# Prefer venv when present (local); container has deps on PATH
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    # shellcheck disable=SC1091
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

echo "Starting coupon validation..."
echo "  DATABASE_URL=${DATABASE_URL:-<default from settings>}"
echo "  PUBLIC_DEALS_PATH=${PUBLIC_DEALS_PATH:-<project root public_deals.json>}"
python3 -u scripts/coupon_checker.py

echo "Done!"
