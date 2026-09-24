"""Enroll subcommand for Udemy Enroller CLI."""

from __future__ import annotations

import asyncio
import csv
import inspect
import json
import random
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.prompt import Confirm

from app.cli.ui import (
    console,
    create_progress_bar,
    is_tty,
    print_banner,
    print_error,
    print_header,
    print_info,
    print_kpi_summary,
    print_success,
    print_warning,
    run_sync,
    setup_signal_handlers,
)
from app.core.constants import FM036_PRICE_UNKNOWN  # W3-02: FM036 unknown-price sentinel 9999.0
from app.services.browser_cookies import get_udemy_cookies
from app.services.course import Course
from app.services.scraper import SCRAPER_REGISTRY, ScraperService
from app.services.session_store import (
    load_persistent_session,
    save_persistent_session,
)
from app.services.udemy_client import UdemyClient


def _parse_list(val: Optional[str]) -> List[str]:
    """Parse comma-separated strings into a clean list of trimmed values."""
    if not val:
        return []
    return [x.strip() for x in val.split(",") if x.strip()]


async def _run_enrollment_pipeline(
    browser: Optional[str],
    token: Optional[str],
    client_id: Optional[str],
    csrf: Optional[str],
    sites: Optional[str],
    categories: Optional[str],
    languages: Optional[str],
    min_rating: Optional[float],
    limit: Optional[int],
    discounted_only: bool,
    output: Optional[str],
    dry_run: bool,
    interactive: bool,
    workers: Optional[int] = None,
    resync_library: bool = False,
) -> int:
    """Async implementation of the enrollment pipeline."""
    print_banner()

    # 1. Resolve Credentials
    access_token = token or ""
    cid = client_id or ""
    csrf_token = csrf or ""
    browser_source = "Manual Token"

    if not access_token:
        # Check saved session first if browser was not explicitly passed
        saved = load_persistent_session()
        if saved and saved.get("access_token") and (not browser or browser.lower() in ("auto", "auto-detect")):
            access_token = saved["access_token"]
            cid = saved.get("client_id", "")
            csrf_token = saved.get("csrf_token", "")
            browser_source = f"Saved Session ({saved.get('display_name', 'User')})"
            print_success(f"Using saved session credentials for [bold white]{saved.get('display_name', 'Udemy User')}[/bold white]")
        else:
            print_info(f"Extracting cookies from browser ({browser or 'auto-detect'})...")
            extracted = get_udemy_cookies(browser=browser)
            if extracted.is_valid:
                access_token = extracted.access_token
                cid = extracted.client_id
                csrf_token = extracted.csrf_token
                browser_source = f"{extracted.browser_name.title()} ({extracted.profile_name or 'Default'})"
                print_success(f"Extracted Udemy session from {browser_source}")
            else:
                if extracted.notes:
                    print_warning(extracted.notes)
                print_error(extracted.error or "Failed to extract active Udemy cookies from browser.")
                console.print("\n[dim]Provide tokens manually with: --token <TOKEN> --client-id <ID> --csrf <CSRF>[/dim]")
                return 1

    # 2. Authenticate Udemy Client
    udemy_client = UdemyClient()
    setup_signal_handlers(cleanup_callback=lambda: asyncio.run(udemy_client.close()))

    try:
        udemy_client.cookie_login(access_token=access_token, client_id=cid, csrf_token=csrf_token)
        print_info("Verifying Udemy session credentials...")
        is_logged_in = await udemy_client.get_session_info()
        if not is_logged_in:
            print_error("Failed to authenticate with Udemy API. Cookies may be expired or invalid.")
            return 1

        user_name = udemy_client.display_name or "Udemy User"
        user_currency = udemy_client.currency.upper()

        # Save valid credentials for future long-term CLI and GUI runs
        save_persistent_session(
            cookies={"access_token": access_token, "client_id": cid, "csrf_token": csrf_token},
            display_name=user_name,
            user_id=udemy_client.udemy_user_id,
            currency=user_currency,
        )

        print_success(f"Authenticated as [bold white]{user_name}[/bold white] (Currency: {user_currency})")

        # 3. Load Library
        print_info("Fetching existing enrolled courses to prevent duplicate checkouts...")
        if resync_library:
            udemy_client.full_sync_complete = False
            udemy_client.archived_sync_complete = False
            udemy_client.archived_sync_cursor_page = 1
            udemy_client._save_enrolled_cache()
        await udemy_client.get_enrolled_courses()
        existing_count = len(udemy_client.enrolled_courses or {})
        print_success(f"Found [bold]{existing_count}[/bold] courses already in your library.")

        # 4. Resolve Scraper Sites
        available_sites = list(SCRAPER_REGISTRY.keys())
        sites_filter = _parse_list(sites)
        if sites_filter:
            selected_sites = []
            for s in sites_filter:
                match = next((k for k in available_sites if k.lower() == s.lower()), None)
                if match:
                    selected_sites.append(match)
                else:
                    print_warning(f"Unknown scraper site '{s}', ignoring.")
            if not selected_sites:
                selected_sites = available_sites
        else:
            selected_sites = available_sites

        print_info(f"Targeting [bold]{len(selected_sites)}[/bold] coupon scraper sources: {', '.join(selected_sites)}")

        # 5. Scrape Courses
        print_header("Scraping Coupon Sources")
        scraper_service = ScraperService(sites_to_scrape=selected_sites, max_workers=workers)
        all_courses: List[Course] = []

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

        # Deduplicate courses by clean URL or slug
        seen_urls = set()
        unique_courses: List[Course] = []
        for c in all_courses:
            dedup_key = getattr(c, "slug", None) or getattr(c, "url", None)
            if dedup_key and dedup_key not in seen_urls:
                seen_urls.add(dedup_key)
                unique_courses.append(c)

        print_success(f"Discovered [bold]{len(unique_courses)}[/bold] unique courses from {len(selected_sites)} sources.")

        # 6. Apply Filters & Enroll
        categories_filter = _parse_list(categories)
        languages_filter = _parse_list(languages)

        settings_dict = {
            "categories": categories_filter,
            "languages": languages_filter,
            "min_rating": min_rating or 0.0,
            "max_enrollment_limit": limit or 0,
            "discounted_only": discounted_only,
        }

        print_header("Processing & Enrollment", "Dry Run" if dry_run else "Live Checkout")
        enrolled_results: List[Dict[str, Any]] = []

        with create_progress_bar() as progress:
            enroll_task = progress.add_task("[bold magenta]Processing courses...", total=len(unique_courses))

            for course in unique_courses:
                if limit and udemy_client.successfully_enrolled_c >= limit:
                    print_info(f"Reached specified limit of {limit} enrolled courses. Stopping.")
                    break

                try:
                    # Category / Language / Rating Filter
                    if udemy_client.is_course_excluded(course, settings_dict):
                        udemy_client.excluded_c += 1
                        continue

                    # Check if already enrolled in library
                    is_enrolled = udemy_client.is_already_enrolled(course)
                    if inspect.isawaitable(is_enrolled):
                        is_enrolled = await is_enrolled
                    elif not isinstance(is_enrolled, bool):
                        is_enrolled = False

                    if is_enrolled:
                        course.is_already_enrolled = True
                        udemy_client.already_enrolled_c += 1
                        progress.console.print(f"  [yellow]●[/yellow] [dim]{course.title[:45]:<45} [ALREADY OWNED][/dim]")
                        inst_list = getattr(course, "instructors", None)
                        inst_str = ", ".join(inst_list) if inst_list else getattr(course, "instructor", "Unknown")
                        enrolled_results.append(
                            {
                                "title": course.title,
                                "url": course.url,
                                "coupon_code": course.coupon_code,
                                "status": "ALREADY ENROLLED",
                                "price": float(course.price) if course.price else 0.0,
                                "instructor": inst_str,
                                "rating": course.rating,
                                "language": course.language,
                            }
                        )
                        continue

                    # Check coupon status on Udemy
                    try:
                        await udemy_client.check_course(course)
                    except Exception as e:
                        progress.console.print(f"  [dim]Check error for {course.title[:35]}: {e}[/dim]")

                    inst_list = getattr(course, "instructors", None)
                    inst_str = ", ".join(inst_list) if inst_list else getattr(course, "instructor", "Unknown")

                    is_already = getattr(course, "status", "") == "Already Enrolled" or getattr(course, "is_already_enrolled", False)
                    is_exp = (course.error and "expired" in str(course.error).lower()) or getattr(course, "is_expired", False)
                    # FM-036 / W3-02: price-gated free eligibility — fail-closed: price None => not free (FM036_PRICE_UNKNOWN=9999.0)
                    try:
                        _price_tmp = float(course.price) if course.price is not None else FM036_PRICE_UNKNOWN
                    except (ValueError, TypeError):
                        _price_tmp = FM036_PRICE_UNKNOWN
                    _coupon_free = bool(course.is_coupon_valid) and _price_tmp == 0
                    _explicit_free = bool(course.is_free) and _price_tmp == 0
                    is_valid_free = (_coupon_free or _explicit_free) and not is_exp and course.price is not None
                    is_definitely_paid = course.price is not None and _price_tmp > 0 and not _coupon_free and not _explicit_free  # noqa: F841 -- FM-036 guard

                    if not course.course_id and course.is_valid and not course.error:
                        course.course_id = course.slug or "mock_id"

                    if is_already:
                        udemy_client.already_enrolled_c += 1
                        status_str = "ALREADY ENROLLED"
                        progress.console.print(f"  [yellow]●[/yellow] [dim]{course.title[:45]:<45} [ALREADY OWNED][/dim]")
                    elif is_exp:
                        udemy_client.expired_c += 1
                        status_str = "EXPIRED"
                    elif is_definitely_paid:
                        status_str = "PAID / NOT 100% OFF"
                        progress.console.print(f"  [magenta]●[/magenta] [dim]{course.title[:45]:<45} [PAID / NOT 100% FREE][/dim]")
                    elif not course.is_valid or not course.course_id:
                        if "403" in str(course.error or ""):
                            status_str = "BLOCKED (403)"
                            udemy_client.unknown_c += 1
                            progress.console.print(f"  [red]⚠[/red] [dim]{course.title[:45]:<45} [BLOCKED (403 WAF)][/dim]")
                        else:
                            status_str = "EXTRACTION FAILED"
                            udemy_client.unknown_c += 1
                            progress.console.print(f"  [red]✗[/red] [dim]{course.title[:45]:<45} [EXTRACTION FAILED][/dim]")
                    elif is_valid_free:
                        status_str = "VALID FREE"
                        saved_val = float(course.list_price) if course.list_price else 0.0

                        if dry_run:
                            progress.console.print(
                                f"  [green]✓[/green] [DRY RUN] [bold white]{course.title[:45]:<45}[/bold white] "
                                f"[green]FREE[/green] (${saved_val:.2f}) [dim]({course.coupon_code or 'Direct'})[/dim]"
                            )
                            udemy_client.successfully_enrolled_c += 1
                            if saved_val > 0:
                                udemy_client.amount_saved_c += Decimal(str(saved_val))
                        else:
                            should_enroll = True
                            if interactive and is_tty():
                                progress.console.print(
                                    f"\n[bold white]Course:[/bold white] {course.title}\n"
                                    f"[dim]Instructor: {inst_str} | Rating: {course.rating or 'N/A'} | Price: ${saved_val:.2f}[/dim]"
                                )
                                answer = Confirm.ask("Enroll in this course?", default=True)
                                if not answer:
                                    should_enroll = False

                            if should_enroll:
                                success = await udemy_client.checkout_single(course)
                                if success is True:
                                    udemy_client.successfully_enrolled_c += 1
                                    if course.list_price and saved_val > 0:
                                        udemy_client.amount_saved_c += Decimal(str(saved_val))
                                    progress.console.print(
                                        f"  [bold green]★ ENROLLED[/bold green] [bold white]{course.title[:45]:<45}[/bold white] "
                                        f"[green]Saved ${saved_val:.2f}[/green]"
                                    )
                                elif getattr(course, "is_already_enrolled", False):
                                    udemy_client.already_enrolled_c += 1
                                    status_str = "ALREADY ENROLLED"
                                    progress.console.print(f"  [yellow]●[/yellow] [dim]{course.title[:45]:<45} [ALREADY OWNED][/dim]")
                                elif getattr(course, "error", "") == "checkout_circuit_open":
                                    udemy_client.unknown_c += 1
                                    status_str = "CIRCUIT OPEN"
                                    progress.console.print(
                                        f"  [yellow]⏸ CIRCUIT OPEN[/yellow]  {course.title[:45]:<45} [yellow]Cloudflare challenge cooldown active[/yellow]"
                                    )
                                else:
                                    udemy_client.unknown_c += 1
                                    status_str = "FAILED"
                                    if success is None:
                                        progress.console.print(f"  [yellow]?[/yellow] [dim]{course.title[:45]:<45} [INDETERMINATE / TIMEOUT][/dim]")
                                    else:
                                        progress.console.print(
                                            f"  [red]✗ FAILED[/red]   {course.title[:45]:<45} [red]Checkout failed[/red]"
                                        )

                                if not dry_run and getattr(course, "error", "") != "checkout_circuit_open":
                                    await asyncio.sleep(random.uniform(1.5, 2.5))
                    else:
                        status_str = "PAID / NOT 100% OFF"
                        progress.console.print(f"  [magenta]●[/magenta] [dim]{course.title[:45]:<45} [PAID / NOT 100% FREE][/dim]")

                    enrolled_results.append(
                        {
                            "title": course.title,
                            "url": course.url,
                            "coupon_code": course.coupon_code,
                            "status": status_str,
                            "price": float(course.price) if course.price else 0.0,
                            "instructor": inst_str,
                            "rating": course.rating,
                            "language": course.language,
                            "category": course.category,
                            "source": getattr(course, "source", "") or getattr(course, "site_name", "") or getattr(course, "site", ""),
                        }
                    )
                except Exception as course_err:
                    progress.console.print(f"  [dim red]Error processing course {course.title[:35]}: {course_err}[/dim red]")
                finally:
                    progress.advance(enroll_task, 1)

        # 7. Print Final KPI Report
        failed_count = udemy_client.unknown_c if isinstance(getattr(udemy_client, "unknown_c", None), (int, float)) else 0
        stats_summary = {
            "total_scraped": len(unique_courses),
            "enrolled": int(udemy_client.successfully_enrolled_c),
            "already_enrolled": int(udemy_client.already_enrolled_c),
            "expired": int(udemy_client.expired_c),
            "excluded": int(udemy_client.excluded_c),
            "failed": int(failed_count),
            "money_saved": float(udemy_client.amount_saved_c),
            "currency": str(udemy_client.currency),
        }
        print_kpi_summary(stats_summary, title="Enrollment Session Summary" if not dry_run else "Dry Run Summary")

        # 8. Export output file if requested
        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if out_path.suffix.lower() == ".json":
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump({"summary": stats_summary, "courses": enrolled_results}, f, indent=2)
            elif out_path.suffix.lower() == ".csv":
                with open(out_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=["title", "status", "price", "instructor", "rating", "language", "category", "coupon_code", "url", "source"],
                    )
                    writer.writeheader()
                    writer.writerows(enrolled_results)
            else:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(f"Udemy Enrollment Summary\n{'='*40}\n")
                    for k, v in stats_summary.items():
                        f.write(f"{k}: {v}\n")
            print_success(f"Results saved to [bold]{out_path.resolve()}[/bold]")

        return 0
    finally:
        await udemy_client.close()


def enroll_command(
    browser: Optional[str] = typer.Option(
        None,
        "--browser",
        "-b",
        help="Browser to auto-extract cookies from (chrome, edge, firefox, brave, opera, chromium, auto).",
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
        help="Manual Udemy csrf_token or csrftoken.",
    ),
    sites: Optional[str] = typer.Option(
        None,
        "--sites",
        "-s",
        help="Comma-separated scraper site names (default: all 17 scrapers).",
    ),
    workers: Optional[int] = typer.Option(
        None,
        "--workers",
        "-w",
        help="Number of concurrent scraper workers (default: settings.MAX_SCRAPER_WORKERS).",
    ),
    categories: Optional[str] = typer.Option(
        None,
        "--categories",
        help="Comma-separated category filters (e.g. 'Development,IT & Software').",
    ),
    languages: Optional[str] = typer.Option(
        None,
        "--languages",
        help="Comma-separated language filters (e.g. 'English,Spanish').",
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
        help="Maximum number of courses to successfully enroll.",
    ),
    discounted_only: bool = typer.Option(
        False,
        "--discounted-only",
        help="Include paid discounted courses (default: false, 100% free coupons only).",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to export run results (.json or .csv).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Simulate run and check coupon validity without performing live enrollment.",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Prompt for user confirmation before enrolling each course.",
    ),
    resync_library: bool = typer.Option(
        False,
        "--resync-library",
        help="Force a complete re-sync of active and archived library courses.",
    ),
) -> None:
    """Batch enroll in free Udemy courses from top coupon websites."""
    code = run_sync(
        _run_enrollment_pipeline(
            browser=browser,
            token=token,
            client_id=client_id,
            csrf=csrf,
            sites=sites,
            categories=categories,
            languages=languages,
            min_rating=min_rating,
            limit=limit,
            discounted_only=discounted_only,
            output=output,
            dry_run=dry_run,
            interactive=interactive,
            workers=workers,
            resync_library=resync_library,
        )
    )
    if code != 0:
        raise typer.Exit(code=code)
