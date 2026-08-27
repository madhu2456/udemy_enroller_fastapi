"""Scrape subcommand for Udemy Enroller CLI."""

from __future__ import annotations

import csv
import json
from typing import List, Optional

import typer

from app.cli.ui import (
    console,
    create_progress_bar,
    print_banner,
    print_courses_table,
    print_header,
    print_info,
    print_success,
    print_warning,
)
from app.services.course import Course
from app.services.scraper import SCRAPER_REGISTRY, ScraperService


def _parse_list(val: Optional[str]) -> List[str]:
    """Parse comma-separated strings into a clean list of trimmed values."""
    if not val:
        return []
    return [x.strip() for x in val.split(",") if x.strip()]


async def _run_scrape_pipeline(
    sites: Optional[str],
    categories: Optional[str],
    languages: Optional[str],
    min_rating: Optional[float],
    limit: Optional[int],
    output: Optional[str],
    format_type: str,
) -> int:
    """Async implementation of the standalone scraper command."""
    if format_type.lower() == "table":
        print_banner()

    available_sites = list(SCRAPER_REGISTRY.keys())
    sites_filter = _parse_list(sites)

    if sites_filter:
        selected_sites = []
        for s in sites_filter:
            match = next((k for k in available_sites if k.lower() == s.lower()), None)
            if match:
                selected_sites.append(match)
            else:
                print_warning(f"Unknown scraper site '{s}', skipping.")
        if not selected_sites:
            selected_sites = available_sites
    else:
        selected_sites = available_sites

    if format_type.lower() == "table":
        print_info(f"Targeting [bold]{len(selected_sites)}[/bold] coupon scrapers: {', '.join(selected_sites)}")
        print_header("Scraping Coupon Sites")

    scraper_service = ScraperService(sites_to_scrape=selected_sites)
    all_courses: List[Course] = []

    if format_type.lower() == "table":
        with create_progress_bar() as progress:
            scrape_task = progress.add_task("[bold cyan]Scraping coupon sites...", total=len(scraper_service.scrapers))
            async for scraper, state in scraper_service.stream_results():
                status_color = "green" if state == "completed" else "yellow" if state == "timed_out" else "red"
                course_cnt = len(scraper.courses)
                progress.console.print(
                    f"  [{status_color}]●[/{status_color}] {scraper.site_name:<20} "
                    f"[{status_color}]{state.upper():<10}[/{status_color}] "
                    f"Found: [bold]{course_cnt}[/bold] courses"
                )
                all_courses.extend(scraper.courses)
                progress.advance(scrape_task, 1)
    else:
        async for scraper, state in scraper_service.stream_results():
            all_courses.extend(scraper.courses)

    # Deduplicate courses by slug or url
    seen_urls = set()
    unique_courses: List[Course] = []
    for c in all_courses:
        dedup_key = getattr(c, "slug", None) or getattr(c, "url", None)
        if dedup_key and dedup_key not in seen_urls:
            seen_urls.add(dedup_key)
            unique_courses.append(c)

    # Apply client-side filters
    cat_filters = [c.lower() for c in _parse_list(categories)]
    lang_filters = [lang.lower() for lang in _parse_list(languages)]

    filtered_courses: List[Course] = []
    for c in unique_courses:
        if cat_filters and c.category and c.category.lower() not in cat_filters:
            continue
        if lang_filters and c.language and c.language.lower() not in lang_filters:
            continue
        if min_rating and c.rating and c.rating < min_rating:
            continue
        filtered_courses.append(c)

    if limit and len(filtered_courses) > limit:
        filtered_courses = filtered_courses[:limit]

    # Handle output formatting
    if format_type.lower() == "json":
        json_data = []
        for c in filtered_courses:
            inst_list = getattr(c, "instructors", None)
            inst_str = ", ".join(inst_list) if inst_list else getattr(c, "instructor", "Unknown")
            json_data.append(
                {
                    "title": c.title,
                    "url": c.url,
                    "coupon_code": c.coupon_code,
                    "instructor": inst_str,
                    "rating": c.rating,
                    "language": c.language,
                    "category": c.category,
                    "price": float(c.price) if c.price else None,
                    "source": getattr(c, "source", "") or getattr(c, "site_name", "") or getattr(c, "site", ""),
                }
            )
        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2)
            print_success(f"Wrote {len(filtered_courses)} courses to {output}")
        else:
            console.print_json(data=json_data)
    elif format_type.lower() == "csv":
        rows = []
        for c in filtered_courses:
            inst_list = getattr(c, "instructors", None)
            inst_str = ", ".join(inst_list) if inst_list else getattr(c, "instructor", "Unknown")
            rows.append(
                {
                    "title": c.title,
                    "url": c.url,
                    "coupon_code": c.coupon_code,
                    "instructor": inst_str,
                    "rating": c.rating,
                    "language": c.language,
                    "category": c.category,
                    "source": getattr(c, "source", "") or getattr(c, "site_name", "") or getattr(c, "site", ""),
                }
            )
        if output:
            with open(output, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["title", "rating", "language", "category", "instructor", "coupon_code", "url", "source"],
                )
                writer.writeheader()
                writer.writerows(rows)
            print_success(f"Wrote {len(filtered_courses)} courses to {output}")
        else:
            import io

            buf = io.StringIO()
            writer = csv.DictWriter(
                buf,
                fieldnames=["title", "rating", "language", "category", "instructor", "coupon_code", "url", "source"],
            )
            writer.writeheader()
            writer.writerows(rows)
            console.print(buf.getvalue())
    else:
        # Rich Table format
        print_courses_table(filtered_courses, title="Scraped Udemy Courses", max_rows=limit or 50)
        print_success(f"Total discovered courses: [bold]{len(filtered_courses)}[/bold]")
        if output:
            with open(output, "w", encoding="utf-8") as f:
                for c in filtered_courses:
                    f.write(f"[{getattr(c, 'source', 'Web')}] {c.title} - {c.url}\n")
            print_success(f"Course list saved to {output}")

    return 0


def scrape_command(
    sites: Optional[str] = typer.Option(
        None,
        "--sites",
        "-s",
        help="Comma-separated scraper site names (default: all 17 scrapers).",
    ),
    categories: Optional[str] = typer.Option(
        None,
        "--categories",
        help="Filter by categories (e.g. 'Development,IT & Software').",
    ),
    languages: Optional[str] = typer.Option(
        None,
        "--languages",
        help="Filter by languages (e.g. 'English,Spanish').",
    ),
    min_rating: Optional[float] = typer.Option(
        None,
        "--min-rating",
        help="Minimum course rating filter (e.g. 4.0).",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Max number of courses to display/export.",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to export scraped courses (.json, .csv, or .txt).",
    ),
    format_type: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: 'table', 'json', or 'csv'.",
    ),
) -> None:
    """Scrape and list free Udemy coupons across 17 top sources without enrolling."""
    from app.cli.ui import run_sync

    code = run_sync(
        _run_scrape_pipeline(
            sites=sites,
            categories=categories,
            languages=languages,
            min_rating=min_rating,
            limit=limit,
            output=output,
            format_type=format_type,
        )
    )
    if code != 0:
        raise typer.Exit(code=code)
