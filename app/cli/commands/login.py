"""Login subcommand for Udemy Enroller CLI to authenticate and persist credentials."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.table import Table

from app.cli.ui import (
    console,
    print_banner,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)
from app.services.browser_cookies import get_udemy_cookies
from app.services.session_store import save_persistent_session
from app.services.udemy_client import UdemyClient


async def _run_login_pipeline(
    browser: Optional[str],
    token: Optional[str],
    client_id: Optional[str],
    csrf: Optional[str],
) -> int:
    """Async implementation of CLI login and long-term credential persistence."""
    print_banner()
    print_header("Authenticate & Save Persistent Udemy Session")

    access_token = token or ""
    cid = client_id or ""
    csrf_token = csrf or ""
    source_name = "Manual Token"

    if not access_token:
        target_browser = browser or "auto"
        print_info(f"Extracting session cookies from browser ({target_browser})...")
        extracted = get_udemy_cookies(browser=target_browser)
        if extracted.is_valid:
            access_token = extracted.access_token
            cid = extracted.client_id
            csrf_token = extracted.csrf_token
            source_name = f"{extracted.browser_name.title()} ({extracted.profile_name or 'Default'})"
            print_success(f"Discovered active Udemy cookies in {source_name}")
        else:
            if extracted.notes:
                print_warning(extracted.notes)
            print_error(extracted.error or "Failed to extract active Udemy cookies from browser.")
            console.print("\n[dim]Provide tokens directly with: python cli.py login --token <TOKEN> --client-id <ID> --csrf <CSRF>[/dim]")
            return 1

    udemy_client = UdemyClient()
    try:
        udemy_client.cookie_login(access_token=access_token, client_id=cid, csrf_token=csrf_token)
        print_info("Verifying credentials with Udemy API...")
        try:
            is_logged_in = await udemy_client.get_session_info()
        except Exception:
            is_logged_in = False

        if not is_logged_in:
            print_error("Failed to authenticate with Udemy API. Credentials may be invalid or expired.")
            return 1

        # Fetch library count
        try:
            await udemy_client.get_enrolled_courses()
        except Exception as e:
            print_warning(f"Could not pre-fetch course library: {e}")

        lib_count = len(udemy_client.enrolled_courses or {})
        user_name = udemy_client.display_name or "Udemy User"
        curr = (udemy_client.currency or "USD").upper()

        # Save credentials for long-term persistence
        save_persistent_session(
            cookies={"access_token": access_token, "client_id": cid, "csrf_token": csrf_token},
            display_name=user_name,
            user_id=udemy_client.udemy_user_id,
            currency=curr,
        )

        table = Table(title="Authenticated Session Details", show_header=True, header_style="bold #A435F0")
        table.add_column("Property", style="bold white", width=22)
        table.add_column("Value", style="cyan")

        table.add_row("Account Name", f"[bold white]{user_name}[/bold white]")
        table.add_row("User ID", str(udemy_client.udemy_user_id or "N/A"))
        table.add_row("Currency", curr)
        table.add_row("Courses Owned", f"[bold white]{lib_count}[/bold white]")
        table.add_row("Credential Source", source_name)
        table.add_row("Long-Term Storage", "[bold green]SAVED (Encrypted)[/bold green]")

        console.print(table)
        print_success("✓ Session authenticated and saved for long-term reuse!")
        console.print("\n[dim]You can now run 'python cli.py enroll' or 'python gui.py' without re-entering tokens.[/dim]\n")
        return 0
    finally:
        await udemy_client.close()


def login_command(
    browser: Optional[str] = typer.Option(
        None,
        "--browser",
        "-b",
        help="Extract session from browser: chrome, edge, firefox, brave, opera, chromium, auto.",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        "-t",
        help="Udemy access_token cookie string.",
    ),
    client_id: Optional[str] = typer.Option(
        None,
        "--client-id",
        "-c",
        help="Udemy client_id cookie string.",
    ),
    csrf: Optional[str] = typer.Option(
        None,
        "--csrf",
        help="Udemy csrf_token / csrftoken value.",
    ),
) -> None:
    """Authenticate with Udemy, verify credentials, and save them for long-term CLI & GUI use."""
    exit_code = asyncio.run(_run_login_pipeline(browser=browser, token=token, client_id=client_id, csrf=csrf))
    if exit_code != 0:
        raise typer.Exit(code=exit_code)
