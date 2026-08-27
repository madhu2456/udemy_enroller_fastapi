"""Stats subcommand for Udemy Enroller CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from sqlalchemy import func
from rich.table import Table

from app.cli.ui import (
    console,
    print_banner,
    print_error,
    print_header,
    print_kpi_summary,
    print_success,
)
from app.models.database import EnrolledCourse, EnrollmentRun, SessionLocal
from app.services.session_store import load_persistent_session


def stats_command(
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        help="Number of recent enrollment runs to display.",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to export stats report (.json).",
    ),
) -> None:
    """Display lifetime enrollment statistics, savings, and historical run logs."""
    print_banner()
    print_header("Lifetime Enrollment Statistics")

    saved = load_persistent_session()
    if saved and saved.get("access_token"):
        console.print(f"[bold cyan]Connected Account:[/bold cyan] [bold white]{saved.get('display_name', 'Udemy User')}[/bold white] [dim]({saved.get('currency', 'USD')})[/dim] • [bold green]Active Session Saved[/bold green]\n")

    try:
        with SessionLocal() as db:
            total_runs = db.query(func.count(EnrollmentRun.id)).scalar() or 0
            total_enrolled = db.query(func.count(EnrolledCourse.id)).scalar() or 0
            total_saved = (
                db.query(func.sum(EnrolledCourse.price))
                .filter(EnrolledCourse.status == "enrolled")
                .scalar()
                or 0.0
            )
            total_already = (
                db.query(func.count(EnrolledCourse.id))
                .filter(EnrolledCourse.status == "already_enrolled")
                .scalar()
                or 0
            )

            stats_data = {
                "total_runs": total_runs,
                "enrolled": total_enrolled,
                "already_enrolled": total_already,
                "expired": 0,
                "excluded": 0,
                "failed": 0,
                "money_saved": float(total_saved),
                "currency": "USD",
            }
            print_kpi_summary(stats_data, title="Lifetime Account Statistics")

            # Historical Runs Table
            recent_runs = (
                db.query(EnrollmentRun)
                .order_by(EnrollmentRun.started_at.desc())
                .limit(limit)
                .all()
            )

            if recent_runs:
                table = Table(
                    title=f"Recent Enrollment Runs (Last {len(recent_runs)})",
                    show_header=True,
                    header_style="bold #A435F0",
                )
                table.add_column("Run ID", style="dim", justify="right", width=8)
                table.add_column("Started At", style="bold white", width=20)
                table.add_column("Status", width=12)
                table.add_column("Enrolled", justify="right", style="green", width=10)
                table.add_column("Processed", justify="right", style="cyan", width=10)
                table.add_column("Saved ($)", justify="right", style="#A435F0", width=12)

                for r in recent_runs:
                    status_color = "green" if r.status == "completed" else "yellow" if r.status in ("pending", "scraping", "enrolling") else "red"
                    started_str = r.started_at.strftime("%Y-%m-%d %H:%M") if r.started_at else "N/A"
                    table.add_row(
                        str(r.id),
                        started_str,
                        f"[{status_color}]{r.status.upper()}[/{status_color}]",
                        str(r.successfully_enrolled or 0),
                        str(r.total_processed or 0),
                        f"${float(r.amount_saved or 0.0):,.2f}",
                    )

                console.print(table)
            else:
                console.print("[dim]No historical enrollment runs found in database yet.[/dim]")

            if output:
                out_path = Path(output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                export_payload = {
                    "lifetime_stats": stats_data,
                    "recent_runs": [
                        {
                            "id": r.id,
                            "started_at": str(r.started_at),
                            "completed_at": str(r.completed_at),
                            "status": r.status,
                            "courses_found": r.total_courses_found,
                            "courses_processed": r.total_processed,
                            "enrolled_count": r.successfully_enrolled,
                            "amount_saved": float(r.amount_saved or 0.0),
                        }
                        for r in recent_runs
                    ],
                }
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(export_payload, f, indent=2)
                print_success(f"Stats exported to [bold]{out_path.resolve()}[/bold]")

    except Exception as e:
        print_error(f"Error loading stats from database: {e}")
        raise typer.Exit(code=1)
