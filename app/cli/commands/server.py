"""Server subcommand for Udemy Enroller CLI."""

from __future__ import annotations

import sys
import typer
import uvicorn

from app.cli.ui import console, print_banner, print_info


def server_command(
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        "-h",
        help="Host address to bind the web server to.",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="Port number to bind the web server to.",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        help="Enable auto-reload for local development.",
    ),
) -> None:
    """Launch the FastAPI Web Interface via Uvicorn."""
    print_banner()
    print_info(f"Starting Udemy Enroller Web UI on [bold white]http://{host if host != '0.0.0.0' else 'localhost'}:{port}[/bold white]")

    # If on Windows, check reload flag
    if sys.platform == "win32" and reload:
        console.print("[yellow]Note: Auto-reload on Windows forces SelectorEventLoop in child processes.[/yellow]")

    try:
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            reload=reload,
            loop="asyncio",
            ws="none",
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Web server stopped by user.[/dim]")
