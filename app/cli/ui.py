"""Rich console UI helpers and terminal styling for Udemy Enroller CLI."""

from __future__ import annotations

import signal
import sys
from typing import Any, Callable, Dict, List, Optional

from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# Udemy brand custom theme
UDEMY_THEME = Theme(
    {
        "primary": "bold #A435F0",
        "secondary": "#5624D0",
        "success": "bold green",
        "warning": "bold yellow",
        "danger": "bold red",
        "info": "bold cyan",
        "muted": "dim white",
        "highlight": "bold magenta",
        "title": "bold white on #5624D0",
    }
)

console = Console(theme=UDEMY_THEME)
err_console = Console(theme=UDEMY_THEME, stderr=True)


def is_tty() -> bool:
    """Return True if stdout is an interactive TTY terminal."""
    try:
        return bool(console.is_terminal and sys.stdout.isatty())
    except Exception:
        return False


def setup_signal_handlers(cleanup_callback: Optional[Callable[[], None]] = None) -> None:
    """Install graceful SIGINT signal handler to trap Ctrl+C."""
    def _sigint_handler(sig, frame):
        console.print("\n[warning]Interrupted by user (Ctrl+C). Cleaning up and shutting down...[/warning]")
        if cleanup_callback:
            try:
                cleanup_callback()
            except Exception as e:
                console.print(f"[danger]Error during cleanup: {e}[/danger]")
        sys.exit(130)

    try:
        signal.signal(signal.SIGINT, _sigint_handler)
    except (ValueError, AttributeError):
        pass  # On Windows non-main thread or when running in restricted environments


def print_banner() -> None:
    """Print the Udemy Enroller ASCII / Rich banner."""
    banner_text = Text()
    banner_text.append("🎓 Udemy Course Enroller", style="bold #A435F0")
    banner_text.append(" — Next-Gen Auto Enrollment & Scraper CLI\n", style="bold white")
    banner_text.append("Universal Browser Cookies • 17 Coupon Scrapers • Zero-Freeze Engine", style="dim white")

    panel = Panel(
        Align.center(banner_text),
        border_style="#A435F0",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)


def print_header(title: str, subtitle: Optional[str] = None) -> None:
    """Print a section header."""
    header_text = Text()
    header_text.append(f"❯ {title}", style="bold #A435F0")
    if subtitle:
        header_text.append(f"  ({subtitle})", style="dim white")
    console.print(header_text)


def print_success(message: str) -> None:
    """Print a green success message."""
    console.print(f"[success]✓[/success] {message}")


def print_warning(message: str) -> None:
    """Print a yellow warning message."""
    console.print(f"[warning]⚠[/warning] {message}")


def print_error(message: str) -> None:
    """Print a red error message."""
    err_console.print(f"[danger]✗[/danger] {message}")


def print_info(message: str) -> None:
    """Print a cyan info message."""
    console.print(f"[info]ℹ[/info] {message}")


def create_progress_bar() -> Progress:
    """Create a styled Rich Progress instance."""
    return Progress(
        SpinnerColumn(spinner_name="dots", style="#A435F0"),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None, complete_style="#A435F0", finished_style="green"),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def print_kpi_summary(stats: Dict[str, Any], title: str = "Enrollment Summary") -> None:
    """Print a Rich panel containing key performance indicators (KPIs)."""
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold #A435F0", expand=True)
    table.add_column("Metric", style="bold white", width=24)
    table.add_column("Value", style="bold cyan", justify="right")
    table.add_column("Status / Note", style="dim white")

    total_scraped = stats.get("total_scraped", 0)
    enrolled = stats.get("enrolled", 0)
    already_enrolled = stats.get("already_enrolled", 0)
    expired = stats.get("expired", 0)
    excluded = stats.get("excluded", 0)
    failed = stats.get("failed", 0)
    money_saved = stats.get("money_saved", 0.0)
    currency = stats.get("currency", "USD").upper()

    table.add_row("Coupons Scraped", str(total_scraped), "From active coupon providers")
    table.add_row("Successfully Enrolled", f"[bold green]{enrolled}[/bold green]", "Added to your Udemy account")
    table.add_row("Already Owned", f"[bold yellow]{already_enrolled}[/bold yellow]", "Previously in your library")
    table.add_row("Expired / Invalid", f"[bold red]{expired}[/bold red]", "Coupon quota exhausted or expired")
    table.add_row("Filter Excluded", str(excluded), "Filtered by rating, language, or category")
    if failed > 0:
        table.add_row("Errors / Blocked", f"[bold red]{failed}[/bold red]", "API or network failures")

    if isinstance(money_saved, (int, float)):
        money_str = f"{currency} ${money_saved:,.2f}"
    else:
        money_str = f"{currency} ${float(money_saved):,.2f}"
    table.add_row("Estimated Money Saved", f"[bold #A435F0]{money_str}[/bold #A435F0]", "Value of free enrollments")

    panel = Panel(
        table,
        title=f"[bold #A435F0]{title}[/bold #A435F0]",
        border_style="#5624D0",
        box=box.ROUNDED,
    )
    console.print(panel)


def run_sync(coro):
    """Run an async coroutine synchronously, handling already running event loops safely."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


def print_courses_table(courses: List[Any], title: str = "Discovered Courses", max_rows: int = 50) -> None:
    """Print a list of Course objects in a formatted Rich table."""
    table = Table(
        title=f"[bold #A435F0]{title}[/bold #A435F0] ({len(courses)} total)",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold #A435F0",
        expand=True,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Title", style="bold white", ratio=3, overflow="ellipsis", no_wrap=True)
    table.add_column("Instructor", style="cyan", ratio=1, overflow="ellipsis", no_wrap=True)
    table.add_column("Rating", style="yellow", justify="center", width=7)
    table.add_column("Language", style="dim white", width=10)
    table.add_column("Source", style="#5624D0", width=16)

    displayed_courses = courses[:max_rows]
    for idx, c in enumerate(displayed_courses, 1):
        rating_str = f"⭐ {c.rating:.1f}" if getattr(c, "rating", None) else "N/A"
        instructors = getattr(c, "instructors", None)
        inst_str = ", ".join(instructors) if instructors else (getattr(c, "instructor", "") or "Unknown")
        lang_str = getattr(c, "language", "") or "All"
        src_str = getattr(c, "source", "") or getattr(c, "site_name", "") or getattr(c, "site", "") or "Web"
        title_str = getattr(c, "title", "Untitled Course")

        table.add_row(str(idx), title_str, inst_str, rating_str, lang_str, src_str)

    if len(courses) > max_rows:
        table.add_row("...", f"[dim]... and {len(courses) - max_rows} more courses[/dim]", "", "", "", "")

    console.print(table)
