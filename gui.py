#!/usr/bin/env python3
"""Desktop GUI launcher for Udemy Enroller with lazy import and headless safety."""

import os
import sys

def run_gui():
    """Launch the CustomTkinter GUI application."""
    # Check for display environment on Linux
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("[ERROR] No graphical display detected (DISPLAY or WAYLAND_DISPLAY environment variable is not set).")
        print("To run in headless / terminal mode, please use the CLI instead:")
        print("    python cli.py --help")
        sys.exit(1)

    import importlib.util
    if not importlib.util.find_spec("tkinter"):
        print("[ERROR] Python tkinter is not installed or available.")
        print("To run in headless / terminal mode, please use the CLI instead:")
        print("    python cli.py --help")
        sys.exit(1)

    try:
        from app.models.database import create_tables

        create_tables()
    except Exception:
        pass

    try:
        from app.gui.app import UdemyEnrollerApp

        app = UdemyEnrollerApp()
        app.mainloop()
    except Exception as e:
        if "no display name" in str(e).lower() or "couldn't connect to display" in str(e).lower():
            print(f"[ERROR] Cannot connect to display: {e}")
            print("Run the rich CLI with: python cli.py --help")
            sys.exit(1)
        raise

if __name__ == "__main__":
    run_gui()
