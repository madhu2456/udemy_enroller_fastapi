"""Export valid coupons to public_deals.json for the /udemycoupons page.

Used by:
- scripts/coupon_checker.py (standalone validation job)
- enrollment pipeline when a run finishes (coupons already checked during enroll)

Also provides SEO-friendly slug helpers for /udemycoupons/c/{slug} detail pages.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import secrets
import unicodedata
import xml.sax.saxutils as xml_escape
from typing import Optional
from urllib.parse import urlparse

from loguru import logger
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.database import EnrolledCourse, SessionLocal

# Repo root / public_deals.json (same path coupon_checker and public_deals router use)
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
DEFAULT_PUBLIC_DEALS_PATH = os.path.join(_PROJECT_ROOT, "public_deals.json")
# Written whenever deals are exported so disk sitemap matches JSON (ops / backups)
DEFAULT_SITEMAP_PATH = os.path.join(_PROJECT_ROOT, "sitemap.generated.xml")
DEFAULT_SITEMAP_META_PATH = os.path.join(_PROJECT_ROOT, "sitemap.meta.json")
# Cap indexable deal pages / sitemap entries (matches export limit default)
SITEMAP_DEAL_LIMIT = 500
SITE_URL_DEFAULT = "https://udemyenroller.madhudadi.in"


def _atomic_write_text(path: str, content: str) -> None:
    """Publish text atomically through a writer-owned same-directory temp file."""
    target_path = os.path.abspath(path)
    directory = os.path.dirname(target_path) or "."
    basename = os.path.basename(target_path)
    file_descriptor: Optional[int] = None
    temp_path: Optional[str] = None

    for _ in range(10):
        candidate = os.path.join(
            directory,
            f".{basename}.{os.getpid()}.{secrets.token_hex(16)}.tmp",
        )
        try:
            file_descriptor = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o666,
            )
        except FileExistsError:
            continue
        temp_path = candidate
        break
    else:
        raise FileExistsError(f"Could not create a unique temp file for {path}")

    try:
        stream = os.fdopen(file_descriptor, "w", encoding="utf-8")
        file_descriptor = None
        with stream:
            stream.write(content)
        os.replace(temp_path, target_path)
    finally:
        if file_descriptor is not None:
            try:
                os.close(file_descriptor)
            except OSError:
                pass
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            except OSError as cleanup_error:
                logger.warning(
                    f"Could not clean temporary export file {temp_path}: "
                    f"{cleanup_error}"
                )


def slugify(text: str, *, max_len: int = 80) -> str:
    """URL-safe slug from a course title or similar string."""
    if not text:
        return "course"
    # Normalize unicode → ascii-ish
    text = unicodedata.normalize("NFKD", str(text))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    if not text:
        return "course"
    return text[:max_len].strip("-") or "course"


def extract_udemy_course_slug(url: Optional[str]) -> Optional[str]:
    """Pull /course/{slug}/ from a Udemy URL when present (stable, SEO-friendly)."""
    if not url:
        return None
    try:
        path = urlparse(url).path or ""
    except Exception:
        return None
    m = re.search(r"/course/([^/?#]+)/?", path, re.I)
    if not m:
        return None
    raw = m.group(1).strip()
    # Keep Udemy slug shape (usually already kebab-case)
    cleaned = re.sub(r"[^\w-]", "", raw.lower().replace("_", "-"))
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or None


def base_slug_for_deal(course: dict) -> str:
    """Preferred base slug: Udemy course path, then DB slug, then title."""
    from_url = extract_udemy_course_slug(course.get("url"))
    if from_url:
        return from_url
    db_slug = course.get("slug")
    if db_slug and isinstance(db_slug, str) and db_slug.strip():
        return slugify(db_slug)
    return slugify(course.get("title") or "course")


def assign_unique_slugs(deals: list[dict]) -> list[dict]:
    """Ensure each deal has a unique ``slug`` for /udemycoupons/c/{slug}.

    On collision, append ``-{id}`` so names stay readable and unique.
    Mutates and returns the list.
    """
    used: set[str] = set()
    for c in deals:
        base = base_slug_for_deal(c)
        cid = c.get("id")
        slug = base
        if slug in used:
            suffix = str(cid) if cid is not None else "x"
            slug = f"{base}-{suffix}"
        # Extreme collision safety
        n = 2
        while slug in used:
            slug = f"{base}-{cid}-{n}"
            n += 1
        c["slug"] = slug
        used.add(slug)
    return deals


def load_public_deals(path: Optional[str] = None) -> list[dict]:
    """Load deals from public_deals.json and ensure SEO slugs are present."""
    json_path = path or DEFAULT_PUBLIC_DEALS_PATH
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return assign_unique_slugs(data)
    except Exception as e:
        logger.warning(f"Could not load public_deals.json: {e}")
        return []


def get_valid_deal_by_id(course_id: int, path: Optional[str] = None) -> Optional[dict]:
    """Return a valid deal dict by EnrolledCourse id, or None."""
    for c in load_public_deals(path):
        try:
            if int(c.get("id", -1)) == int(course_id) and c.get("is_coupon_valid"):
                return c
        except (TypeError, ValueError):
            continue
    return None


def get_valid_deal_by_slug(slug: str, path: Optional[str] = None) -> Optional[dict]:
    """Return a valid deal by SEO slug (or numeric id string for legacy links)."""
    if not slug:
        return None
    slug = slug.strip().strip("/")
    # Legacy numeric URLs: /udemycoupons/c/14212
    if slug.isdigit():
        return get_valid_deal_by_id(int(slug), path)

    slug_l = slug.lower()
    for c in load_public_deals(path):
        if not c.get("is_coupon_valid"):
            continue
        if (c.get("slug") or "").lower() == slug_l:
            return c
    return None


def list_valid_deals(
    path: Optional[str] = None, *, limit: Optional[int] = None
) -> list[dict]:
    """All valid coupon deals (with slugs), newest first."""
    deals = [
        c
        for c in load_public_deals(path)
        if c.get("is_coupon_valid") and c.get("coupon_code")
    ]
    # Ensure slugs (load_public_deals already assigns)
    deals = [c for c in deals if c.get("slug")]
    deals.sort(
        key=lambda c: c.get("last_checked_at") or c.get("enrolled_at") or "",
        reverse=True,
    )
    if limit is not None:
        return deals[:limit]
    return deals


# Sitemap quality: avoid thin/garbage indexable URLs (short titles, missing fields)
SITEMAP_MIN_TITLE_LEN = 8
# Prefer deals checked within this many days when last_checked_at is present
SITEMAP_MAX_AGE_DAYS = 30


def is_sitemap_quality_deal(course: dict) -> bool:
    """Return True if a deal is worth listing in the sitemap / SEO detail index.

    Requires valid flag, coupon code, stable slug, and a non-trivial title.
    When ``last_checked_at`` is present and parseable, exclude deals older than
    ``SITEMAP_MAX_AGE_DAYS`` so stale inventory does not dominate the index.
    Deals without a check timestamp still pass other quality gates (legacy rows).
    """
    if not course.get("is_coupon_valid"):
        return False
    code = course.get("coupon_code")
    if not code or not str(code).strip():
        return False
    slug = course.get("slug")
    if not slug or not isinstance(slug, str):
        return False
    safe = slug.strip().strip("/")
    if not safe or "/" in safe or ".." in safe:
        return False
    title = (course.get("title") or "").strip()
    if len(title) < SITEMAP_MIN_TITLE_LEN:
        return False

    raw = course.get("last_checked_at") or course.get("enrolled_at")
    if raw and isinstance(raw, str) and len(raw) >= 10:
        try:
            # Accept 2026-07-06T14:24:07Z or isoformat with offset
            date_part = raw[:10]
            checked = datetime.date.fromisoformat(date_part)
            age = (datetime.date.today() - checked).days
            if age > SITEMAP_MAX_AGE_DAYS:
                return False
        except (TypeError, ValueError):
            pass
    return True


def list_valid_deals_for_sitemap(
    path: Optional[str] = None, *, limit: int = SITEMAP_DEAL_LIMIT
) -> list[dict]:
    """Quality-filtered valid coupons for sitemap / indexable detail URLs."""
    deals = [c for c in list_valid_deals(path) if is_sitemap_quality_deal(c)]
    if limit is not None:
        return deals[:limit]
    return deals


def public_deals_freshness(path: Optional[str] = None) -> dict:
    """Hub freshness stats: valid count + last updated (file mtime / latest check)."""
    json_path = path or DEFAULT_PUBLIC_DEALS_PATH
    deals = list_valid_deals(path)
    last_file = None
    if os.path.exists(json_path):
        try:
            mtime = os.path.getmtime(json_path)
            last_file = datetime.datetime.fromtimestamp(
                mtime, tz=datetime.UTC
            ).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            pass
    last_check = None
    for c in deals:
        raw = c.get("last_checked_at") or c.get("enrolled_at")
        if raw and isinstance(raw, str) and (last_check is None or raw > last_check):
            last_check = raw
    last_check_display = None
    if last_check and len(last_check) >= 10:
        # 2026-07-06T14:24:07Z → date + optional time
        last_check_display = last_check[:16].replace("T", " ") + " UTC"
    return {
        "valid_count": len(deals),
        "last_updated": last_file or last_check_display,
        "last_checked": last_check_display,
    }


def category_slug(name: Optional[str]) -> str:
    return slugify(name or "other", max_len=60)


def list_category_summaries(path: Optional[str] = None) -> list[dict]:
    """Categories with valid deals: name, slug, count (sorted by count desc)."""
    from collections import Counter

    deals = list_valid_deals(path)
    counts: Counter[str] = Counter()
    for d in deals:
        name = (d.get("category") or "Other").strip() or "Other"
        counts[name] += 1
    out = []
    for name, count in counts.most_common():
        out.append(
            {
                "name": name,
                "slug": category_slug(name),
                "count": count,
            }
        )
    return out


def get_deals_for_category_slug(
    cat_slug: str, path: Optional[str] = None, *, limit: int = 100
) -> tuple[Optional[str], list[dict]]:
    """Return (category_display_name, deals) for a category slug, or (None, [])."""
    if not cat_slug:
        return None, []
    want = cat_slug.strip().lower()
    matched_name = None
    for summary in list_category_summaries(path):
        if summary["slug"] == want:
            matched_name = summary["name"]
            break
    if not matched_name:
        return None, []
    deals = [
        d
        for d in list_valid_deals(path)
        if ((d.get("category") or "Other").strip() or "Other") == matched_name
    ]
    return matched_name, deals[:limit]


def related_deals(
    course: dict, path: Optional[str] = None, *, limit: int = 3
) -> list[dict]:
    """Same-category valid deals excluding the current course."""
    cat = (course.get("category") or "Other").strip() or "Other"
    cid = course.get("id")
    slug = course.get("slug")
    out = []
    for d in list_valid_deals(path):
        if d.get("id") == cid or d.get("slug") == slug:
            continue
        dcat = (d.get("category") or "Other").strip() or "Other"
        if dcat != cat:
            continue
        out.append(d)
        if len(out) >= limit:
            break
    # Fallback: any other deals if category thin
    if len(out) < limit:
        for d in list_valid_deals(path):
            if d.get("id") == cid or d.get("slug") == slug:
                continue
            if d in out:
                continue
            out.append(d)
            if len(out) >= limit:
                break
    return out


def build_sitemap_xml(
    *,
    site_url: str = SITE_URL_DEFAULT,
    deals_path: Optional[str] = None,
    limit: int = SITEMAP_DEAL_LIMIT,
) -> tuple[str, int]:
    """Build full sitemap XML from static pages + valid deal slugs in public_deals.json.

    Returns ``(xml_text, deal_url_count)``. Called on every ``GET /sitemap.xml``
    and after each deals export so listings stay in sync.
    """
    json_path = deals_path or DEFAULT_PUBLIC_DEALS_PATH
    deals_lastmod = None
    if os.path.exists(json_path):
        try:
            mtime = os.path.getmtime(json_path)
            deals_lastmod = datetime.datetime.fromtimestamp(
                mtime, tz=datetime.UTC
            ).strftime("%Y-%m-%d")
        except Exception:
            pass

    def maybe_lastmod(lastmod: str | None) -> str:
        return f"\n<lastmod>{lastmod}</lastmod>" if lastmod else ""

    def deal_lastmod(course: dict) -> str | None:
        raw = course.get("last_checked_at") or course.get("enrolled_at")
        if not raw or not isinstance(raw, str):
            return deals_lastmod
        return raw[:10] if len(raw) >= 10 else deals_lastmod

    pages: list[tuple[str, str | None, str, str]] = [
        ("/udemycoupons", deals_lastmod, "0.95", "daily"),
        ("/", deals_lastmod, "1.00", "daily"),
        ("/guides/free-udemy-coupons", deals_lastmod, "0.92", "weekly"),
        ("/faq", None, "0.90", "weekly"),
        ("/about", None, "0.80", "monthly"),
        ("/guides", None, "0.80", "weekly"),
        ("/privacy", None, "0.30", "monthly"),
    ]

    # Category hub pages (only categories that currently have valid deals)
    for cat in list_category_summaries(json_path):
        cslug = cat.get("slug")
        if not cslug:
            continue
        pages.append(
            (
                f"/udemycoupons/category/{cslug}",
                deals_lastmod,
                "0.75",
                "daily",
            )
        )

    deal_count = 0
    for course in list_valid_deals_for_sitemap(json_path, limit=limit):
        slug = course.get("slug")
        if not slug or not isinstance(slug, str):
            continue
        safe = slug.strip().strip("/")
        if not safe or "/" in safe or ".." in safe:
            continue
        pages.append(
            (f"/udemycoupons/c/{safe}", deal_lastmod(course), "0.55", "daily")
        )
        deal_count += 1

    site = site_url.rstrip("/")
    urls = "\n".join(
        f"""<url>
<loc>{xml_escape.escape(f"{site}{path}")}</loc>{maybe_lastmod(lastmod)}
<changefreq>{freq}</changefreq>
<priority>{prio}</priority>
</url>"""
        for path, lastmod, prio, freq in pages
    )
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>
"""
    return content, deal_count


def write_sitemap_files(
    *,
    site_url: str = SITE_URL_DEFAULT,
    deals_path: Optional[str] = None,
    sitemap_path: Optional[str] = None,
    meta_path: Optional[str] = None,
) -> int:
    """Regenerate on-disk sitemap snapshot + meta after deals export.

    ``GET /sitemap.xml`` still builds live from JSON; this writes a mirror for
    debugging and confirms export refreshed SEO listings.
    """
    xml, deal_count = build_sitemap_xml(site_url=site_url, deals_path=deals_path)
    out = sitemap_path or DEFAULT_SITEMAP_PATH
    meta_out = meta_path or DEFAULT_SITEMAP_META_PATH
    try:
        _atomic_write_text(out, xml)

        meta = {
            "generated_at": datetime.datetime.now(datetime.UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "deal_urls": deal_count,
            "total_urls": xml.count("<url>"),
            "deals_path": deals_path or DEFAULT_PUBLIC_DEALS_PATH,
            "sitemap_path": out,
        }
        _atomic_write_text(meta_out, json.dumps(meta, indent=2))

        logger.info(
            f"Sitemap refreshed: {deal_count} deal URLs "
            f"({meta['total_urls']} total) → {out}"
        )
        return deal_count
    except Exception as e:
        logger.error(f"Failed to write sitemap files: {e}")
        return -1


def export_public_deals_json(
    db: Optional[Session] = None,
    *,
    path: Optional[str] = None,
    limit: int = 500,
    refresh_sitemap: bool = True,
) -> int:
    """Write currently valid coupons to public_deals.json and refresh sitemap.

    Returns the number of courses exported. Safe to call from enrollment
    completion or the coupon checker; uses atomic replace via .tmp file.

    When ``refresh_sitemap`` is True (default), also regenerates the sitemap
    snapshot from the new JSON so /sitemap.xml deal URLs stay current.
    """
    owns_db = db is None
    if owns_db:
        db = SessionLocal()

    json_path = path or DEFAULT_PUBLIC_DEALS_PATH
    try:
        valid_courses = (
            db.query(EnrolledCourse)
            .filter(
                EnrolledCourse.is_coupon_valid.is_(True),
                EnrolledCourse.coupon_code.isnot(None),
            )
            .order_by(desc(EnrolledCourse.enrolled_at))
            .limit(limit)
            .all()
        )

        export_data = []
        for c in valid_courses:
            export_data.append(
                {
                    "id": c.id,
                    "title": c.title,
                    "url": c.url,
                    "slug": c.slug,  # may be None; assign_unique_slugs fills SEO slug
                    "coupon_code": c.coupon_code,
                    "price": c.price,
                    "category": c.category,
                    "language": c.language,
                    "rating": c.rating,
                    "is_coupon_valid": c.is_coupon_valid,
                    "enrolled_at": c.enrolled_at.isoformat() + "Z"
                    if c.enrolled_at
                    else None,
                    "last_checked_at": c.last_checked_at.isoformat() + "Z"
                    if c.last_checked_at
                    else None,
                }
            )

        assign_unique_slugs(export_data)

        _atomic_write_text(
            json_path,
            json.dumps(export_data, ensure_ascii=False, indent=2),
        )

        logger.info(
            f"Exported {len(export_data)} valid coupons to {json_path}"
        )

        # Keep sitemap deal URLs in lockstep with this JSON write
        if refresh_sitemap:
            write_sitemap_files(deals_path=json_path)

        return len(export_data)
    except Exception as e:
        logger.error(f"Failed to export public_deals.json: {e}")
        return 0
    finally:
        if owns_db and db is not None:
            db.close()
