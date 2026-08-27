"""Logout subcommand for Udemy Enroller CLI to clear saved credentials."""

from __future__ import annotations

from app.cli.ui import console, print_banner, print_header, print_success
from app.services.session_store import clear_persistent_session


def logout_command() -> None:
    """Clear saved persistent Udemy credentials from local storage and database."""
    print_banner()
    print_header("Udemy Session Disconnect")

    clear_persistent_session()
    print_success("✓ Persistent Udemy credentials and saved sessions have been cleared.")
    console.print("\n[dim]To reconnect your account, run 'python cli.py login' or use the Desktop GUI.[/dim]\n")
