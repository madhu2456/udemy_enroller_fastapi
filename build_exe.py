#!/usr/bin/env python3
"""Cross-platform executable compiler for Udemy Enroller.

Compiles:
- Gui.exe / Gui: Modern CustomTkinter Desktop GUI application
- cli.exe / cli: Unified Rich Terminal CLI application

Usage:
    python build_exe.py --all        # Build both GUI and CLI executables
    python build_exe.py --gui        # Build only GUI executable (Gui.exe / Gui)
    python build_exe.py --cli        # Build only CLI executable (cli.exe / cli)
    python build_exe.py --clean      # Clean previous build and dist artifacts
"""

import argparse
import importlib.util
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def check_prerequisites() -> bool:
    """Verify build tools and dependencies are available before compilation."""
    if importlib.util.find_spec("PyInstaller") is None:
        print("\n" + "=" * 65)
        print("[ERROR] Missing required build dependency: PyInstaller")
        print("=" * 65)
        print(f"Current Python executable:\n  {sys.executable}\n")
        print("To install PyInstaller in your current environment, run:")
        print(f"  {sys.executable} -m pip install pyinstaller\n")
        print("Or activate your project virtual environment first:")
        print("  Linux/macOS:        source venv/bin/activate (or .venv/bin/activate)")
        print("  Windows PowerShell: .\\venv\\Scripts\\Activate.ps1")
        print("  Windows CMD:        venv\\Scripts\\activate.bat\n")
        print("Pre-compiled standalone binaries can also be downloaded directly from:")
        print("  https://github.com/madhu2456/udemy_enroller_fastapi/releases")
        print("=" * 65 + "\n")
        return False
    return True


def clean_artifacts():
    """Remove build, dist, and spec artifacts."""
    print("[*] Cleaning build and dist directories...")
    for dir_name in ["build", "dist"]:
        target_dir = PROJECT_ROOT / dir_name
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
            print(f"  Removed {dir_name}/")


def build_executable(spec_file: str, name: str) -> bool:
    """Run PyInstaller with the given spec file."""
    spec_path = PROJECT_ROOT / spec_file
    if not spec_path.exists():
        print(f"[ERROR] Spec file not found: {spec_path}")
        return False

    print("\n==================================================")
    print(f"[*] Building {name} ({platform.system()} {platform.machine()})...")
    print("==================================================")

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec_path)]
    try:
        subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
        is_windows = platform.system() == "Windows"
        ext = ".exe" if is_windows else ""
        out_bin = PROJECT_ROOT / "dist" / f"{name}{ext}"
        if out_bin.exists():
            size_mb = out_bin.stat().st_size / (1024 * 1024)
            print(f"\n[SUCCESS] Built {out_bin.name} ({size_mb:.1f} MB) in dist/")
            return True
        else:
            print(f"\n[WARNING] Build finished but {out_bin.name} not found in dist/")
            return True
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Build failed for {name}: {e}")
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile standalone executables for Udemy Enroller.")
    parser.add_argument("--all", action="store_true", help="Build both GUI and CLI executables.")
    parser.add_argument("--gui", action="store_true", help="Build only the Desktop GUI (Gui.exe / Gui).")
    parser.add_argument("--cli", action="store_true", help="Build only the Unified CLI (cli.exe / cli).")
    parser.add_argument("--clean", action="store_true", help="Clean build and dist artifacts before building.")

    args = parser.parse_args(argv)

    if not any([args.all, args.gui, args.cli, args.clean]):
        parser.print_help()
        print("\nDefaulting to building both GUI and CLI executables (--all)...")
        args.all = True

    requires_build = bool(args.all or args.gui or args.cli)
    if requires_build and not check_prerequisites():
        return 1

    if args.clean:
        clean_artifacts()
        if not requires_build:
            print("[*] Clean completed.")
            return 0

    success = True
    if args.gui or args.all:
        if not build_executable("gui.spec", "Gui"):
            success = False

    if args.cli or args.all:
        if not build_executable("cli.spec", "cli"):
            success = False

    if success:
        print("\n==================================================")
        print("[★] All requested standalone builds completed successfully!")
        print("    Executables are located in the dist/ folder.")
        print("==================================================\n")
        return 0
    else:
        print("\n[!] One or more builds failed. Check logs above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
