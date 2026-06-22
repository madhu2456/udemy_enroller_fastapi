#!/bin/bash
set -e
# Coupon Checker Script

echo "=========================================="
echo "    Udemy Enroller - Coupon Checker       "
echo "=========================================="

cd "$(dirname "$0")/.."

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Warning: Virtual environment 'venv' not found. Running with global python."
fi

# Run the python script
echo "Starting coupon validation..."
python3 scripts/coupon_checker.py

echo "Done!"
