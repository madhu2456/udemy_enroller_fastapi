"""Main Typer application registering all CLI subcommands."""

from __future__ import annotations

from typing import Optional
import typer

from app.cli.commands.check import check_command
from app.cli.commands.enroll import enroll_command
from app.cli.commands.login import login_command
from app.cli.commands.logout import logout_command
from app.cli.commands.scrape import scrape_command
from app.cli.commands.server import server_command
from app.cli.commands.stats import stats_command
from app.cli.ui import console


def version_callback(value: bool) -> None:
    if value:
        console.print("[bold #A435F0]Udemy Enroller[/bold #A435F0] [bold white]v2.2.0[/bold white]")
        raise typer.Exit()


app = typer.Typer(
    name="udemy-enroller",
    help="🎓 Udemy Course Enroller — Fast, modern CLI for scraping coupons and auto-enrolling in free Udemy courses.",
    add_completion=False,
    no_args_is_help=True,
)

# Register subcommands
app.command(name="login", help="Authenticate with Udemy and save credentials for long-term CLI & GUI use.")(login_command)
app.command(name="logout", help="Clear saved persistent Udemy session credentials.")(logout_command)
app.command(name="enroll", help="Auto-enroll in free Udemy courses using saved session, browser cookies, or manual token.")(enroll_command)
app.command(name="scrape", help="Scrape free Udemy courses from 17 coupon sites without enrolling.")(scrape_command)
app.command(name="check", help="Verify Udemy session health or check a single course coupon URL.")(check_command)
app.command(name="stats", help="View lifetime enrollment statistics, savings, and historical runs.")(stats_command)
app.command(name="server", help="Launch the FastAPI Web Interface via Uvicorn.")(server_command)


@app.callback()
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version information and exit.",
        callback=version_callback,
        is_eager=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-V",
        help="Enable INFO logging (stderr-only).",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable DEBUG logging (wins over --verbose).",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Log level override: DEBUG, INFO, WARNING, ERROR. Default WARNING.",
    ),
    log_file: Optional[str] = typer.Option(
        None,
        "--log-file",
        help="Write logs to this file in addition to stderr.",
    ),
) -> None:
    """Udemy Course Enroller CLI application."""
    if ctx.invoked_subcommand is None and not verbose and not debug and log_level is None and log_file is None:
        return
    if log_level is not None and log_level.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise typer.BadParameter("log-level must be one of: DEBUG, INFO, WARNING, ERROR")
    if log_level is not None:
        resolved = log_level.upper()
    elif debug:
        resolved = "DEBUG"
    elif verbose:
        resolved = "INFO"
    else:
        resolved = None  # setup_logging falls back to settings.LOG_LEVEL (WARNING)
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = resolved
    ctx.obj["log_file"] = log_file
    from app.logging_config import setup_logging

    setup_logging(level=resolved, log_file=log_file)

    if ctx.invoked_subcommand is not None:
        try:
            from app.models.database import create_tables

            create_tables()
        except Exception as exc:
            from loguru import logger

            logger.debug(f"SQLite auto-initialization non-fatal notice: {exc}")


if __name__ == "__main__":
    app()
