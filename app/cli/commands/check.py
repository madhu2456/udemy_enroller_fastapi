"""Check subcommand for Udemy Enroller CLI."""

from __future__ import annotations

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
from app.services.course import Course
from app.services.session_store import (
    load_persistent_session,
    save_persistent_session,
)
from app.services.udemy_client import UdemyClient


async def _run_check_pipeline(
    browser: Optional[str],
    token: Optional[str],
    client_id: Optional[str],
    csrf: Optional[str],
    url: Optional[str],
) -> int:
    """Async implementation of the health check command."""
    print_banner()

    udemy_client = UdemyClient()
    try:
        # Check single course URL if provided
        if url:
            print_header("Checking Udemy Coupon URL", url)
            course = Course(title="Target Course", url=url)

            # Extract or set credentials if available for authenticated check
            access_token = token or ""
            cid = client_id or ""
            csrf_token = csrf or ""
            if not access_token:
                extracted = get_udemy_cookies(browser=browser)
                if extracted.is_valid:
                    access_token = extracted.access_token
                    cid = extracted.client_id
                    csrf_token = extracted.csrf_token

            if access_token:
                udemy_client.cookie_login(access_token=access_token, client_id=cid, csrf_token=csrf_token)
                await udemy_client.get_session_info()

            print_info("Querying Udemy API for course and coupon metadata...")
            try:
                await udemy_client.check_course(course)
            except Exception as e:
                print_error(f"Error checking course: {e}")
                return 1

            table = Table(title="Course & Coupon Status", show_header=True, header_style="bold #A435F0")
            table.add_column("Property", style="bold white", width=20)
            table.add_column("Value", style="cyan")

            inst_list = getattr(course, "instructors", None)
            inst_str = ", ".join(inst_list) if inst_list else getattr(course, "instructor", "Unknown")

            table.add_row("Title", course.title or "Unknown")
            table.add_row("Course ID", str(course.course_id) if course.course_id else "N/A")
            table.add_row("Instructor", inst_str)
            table.add_row("Rating", f"⭐ {course.rating:.1f}" if course.rating else "N/A")
            table.add_row("Category", course.category or "N/A")
            table.add_row("Language", course.language or "N/A")
            table.add_row("Coupon Code", course.coupon_code or "None (Direct Free or Full Price)")
            is_already = getattr(course, "status", "") == "Already Enrolled" or getattr(course, "is_already_enrolled", False)
            is_exp = (course.error and "expired" in str(course.error).lower()) or getattr(course, "is_expired", False)
            is_valid_free = (course.is_coupon_valid or course.is_free) and not is_exp

            if is_already:
                status_disp = "[bold yellow]Already in Library[/bold yellow]"
            elif is_exp:
                status_disp = "[bold red]Expired / Invalid Coupon[/bold red]"
            elif is_valid_free:
                status_disp = "[bold green]Active 100% OFF Free Coupon[/bold green]"
            else:
                status_disp = "[bold magenta]Paid Course (No 100% discount)[/bold magenta]"

            table.add_row("Coupon Status", status_disp)
            console.print(table)
            return 0

        # Otherwise perform Session Health Check
        print_header("Checking Udemy Account & Session Health")
        access_token = token or ""
        cid = client_id or ""
        csrf_token = csrf or ""
        source_name = "Manual Credentials"

        if not access_token:
            saved = load_persistent_session()
            if saved and saved.get("access_token") and (not browser or browser.lower() in ("auto", "auto-detect")):
                access_token = saved["access_token"]
                cid = saved.get("client_id", "")
                csrf_token = saved.get("csrf_token", "")
                source_name = f"Saved Session ({saved.get('display_name', 'User')})"
                print_success(f"Loaded persistent session for [bold white]{saved.get('display_name', 'Udemy User')}[/bold white]")
            else:
                print_info(f"Scanning for browser cookies ({browser or 'auto-detect'})...")
                extracted = get_udemy_cookies(browser=browser)
                if extracted.is_valid:
                    access_token = extracted.access_token
                    cid = extracted.client_id
                    csrf_token = extracted.csrf_token
                    source_name = f"{extracted.browser_name.title()} ({extracted.profile_name or 'Default'})"
                    print_success(f"Found active cookies in {source_name}")
                else:
                    if extracted.notes:
                        print_warning(extracted.notes)
                    print_error(extracted.error or "No valid browser session found.")
                    return 1

        udemy_client.cookie_login(access_token=access_token, client_id=cid, csrf_token=csrf_token)
        print_info("Testing authentication with Udemy API...")
        try:
            is_logged_in = await udemy_client.get_session_info()
        except Exception:
            is_logged_in = False

        table = Table(title="Udemy Session Health Report", show_header=True, header_style="bold #A435F0")
        table.add_column("Parameter", style="bold white", width=22)
        table.add_column("Status / Value", style="cyan")

        table.add_row("Source", source_name)
        table.add_row("Access Token", f"{access_token[:8]}...{access_token[-4:]}" if len(access_token) > 12 else "Present")
        table.add_row("Client ID", f"{cid[:8]}..." if cid else "[dim]Not Set[/dim]")
        table.add_row("CSRF Token", f"{csrf_token[:8]}..." if csrf_token else "[dim]Not Set[/dim]")

        if is_logged_in:
            table.add_row("Auth Status", "[bold green]AUTHENTICATED[/bold green]")
            table.add_row("Display Name", f"[bold white]{udemy_client.display_name}[/bold white]")
            table.add_row("User ID", str(udemy_client.udemy_user_id or "N/A"))
            table.add_row("Preferred Currency", udemy_client.currency.upper())

            # Save session for long-term reuse
            save_persistent_session(
                cookies={"access_token": access_token, "client_id": cid, "csrf_token": csrf_token},
                display_name=udemy_client.display_name,
                user_id=udemy_client.udemy_user_id,
                currency=udemy_client.currency.upper(),
            )

            # Check library count
            await udemy_client.get_enrolled_courses()
            lib_count = len(udemy_client.enrolled_courses or {})
            table.add_row("Total Enrolled Courses", f"[bold white]{lib_count}[/bold white]")

            console.print(table)
            print_success("Udemy session is healthy, saved, and ready for auto-enrollment!")
            return 0
        else:
            table.add_row("Auth Status", "[bold red]FAILED / EXPIRED[/bold red]")
            console.print(table)
            print_error("Failed to authenticate with Udemy. Please refresh your browser login or provide new tokens.")
            return 1
    finally:
        await udemy_client.close()


def check_command(
    browser: Optional[str] = typer.Option(
        None,
        "--browser",
        "-b",
        help="Browser to auto-extract cookies from for testing.",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        "-t",
        help="Manual Udemy access_token.",
    ),
    client_id: Optional[str] = typer.Option(
        None,
        "--client-id",
        "-c",
        help="Manual Udemy client_id.",
    ),
    csrf: Optional[str] = typer.Option(
        None,
        "--csrf",
        help="Manual Udemy csrf_token.",
    ),
    url: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="Specific Udemy course or coupon URL to test for free coupon validity.",
    ),
) -> None:
    """Check Udemy session health or validate a specific course coupon link."""
    from app.cli.ui import run_sync

    code = run_sync(
        _run_check_pipeline(
            browser=browser,
            token=token,
            client_id=client_id,
            csrf=csrf,
            url=url,
        )
    )
    if code != 0:
        raise typer.Exit(code=code)
