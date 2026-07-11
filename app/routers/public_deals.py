from fastapi import APIRouter, Depends, Request, Query, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.database import get_db, EnrolledCourse
from app.security import _client_key, public_coupons_api_limiter
from app.services.public_deals_export import (
    category_slug as category_slug_fn,
    get_deals_for_category_slug,
    get_valid_deal_by_slug,
    list_category_summaries,
    list_valid_deals,
    public_deals_freshness,
    related_deals,
)

router = APIRouter(prefix="/udemycoupons", tags=["Public Deals"])
templates = Jinja2Templates(directory="app/templates")

# Page size for public coupon grid (SSR first paint + API pagination).
PUBLIC_COUPON_PAGE_SIZE = 12


@router.get("", response_class=HTMLResponse)
def public_deals_page(request: Request):
    """Render the public deals dashboard page."""
    initial_courses = []
    initial_total = 0
    initial_pages = 1
    freshness = {"valid_count": 0, "last_updated": None, "last_checked": None}
    categories = []
    try:
        valid_courses = list_valid_deals()
        initial_total = len(valid_courses)
        initial_courses = valid_courses[:PUBLIC_COUPON_PAGE_SIZE]
        initial_pages = max(
            1, (initial_total + PUBLIC_COUPON_PAGE_SIZE - 1) // PUBLIC_COUPON_PAGE_SIZE
        )
        freshness = public_deals_freshness()
        categories = list_category_summaries()
    except Exception:
        pass

    return templates.TemplateResponse(
        request,
        "pages/public_deals.html",
        {
            "initial_courses": initial_courses,
            "initial_total": initial_total,
            "initial_pages": initial_pages,
            "page_size": PUBLIC_COUPON_PAGE_SIZE,
            "freshness": freshness,
            "categories": categories,
        },
    )


@router.get("/category/{category_slug}", response_class=HTMLResponse)
def coupon_category_page(request: Request, category_slug: str):
    """Indexable category hub for free coupon listings."""
    name, deals = get_deals_for_category_slug(category_slug)
    if not name:
        raise HTTPException(status_code=404, detail="Category not found")
    freshness = public_deals_freshness()
    return templates.TemplateResponse(
        request,
        "pages/coupon_category.html",
        {
            "category_name": name,
            "category_slug": category_slug,
            "deals": deals,
            "deal_count": len(deals),
            "freshness": freshness,
            "categories": list_category_summaries(),
        },
    )


@router.get("/c/{slug}", response_class=HTMLResponse)
def coupon_detail_page(request: Request, slug: str):
    """Indexable on-site page for one valid free-coupon listing.

    URL uses a readable SEO slug (Udemy course slug or slugified title), e.g.
    ``/udemycoupons/c/web-development-bootcamp``. Numeric legacy IDs still resolve
    and 301 to the slug URL when possible.
    """
    course = get_valid_deal_by_slug(slug)
    if not course:
        raise HTTPException(
            status_code=404, detail="Coupon listing not found or no longer valid"
        )

    # Permanent redirect numeric /c/123 → /c/readable-name for SEO
    if slug.isdigit() and course.get("slug") and course["slug"] != slug:
        return RedirectResponse(
            url=f"/udemycoupons/c/{course['slug']}",
            status_code=301,
        )

    related = related_deals(course)
    cat_name = (course.get("category") or "Other").strip() or "Other"

    return templates.TemplateResponse(
        request,
        "pages/coupon_detail.html",
        {
            "course": course,
            "related": related,
            "category_name": cat_name,
            "category_slug": category_slug_fn(cat_name),
        },
    )


@router.get("/", include_in_schema=False)
async def public_deals_page_redirect():
    return RedirectResponse(url="/udemycoupons", status_code=307)

@router.get("/api/coupons")
def get_public_coupons(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(PUBLIC_COUPON_PAGE_SIZE, ge=1, le=100),
    search: str = Query(None),
    category: str = Query(None),
    status: str = Query(None)
):
    """API endpoint to fetch coupons for the public dashboard."""
    import os
    import json

    public_coupons_api_limiter.raise_if_limited(_client_key(request))

    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "public_deals.json")
    
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                all_courses = json.load(f)
                
            categories = sorted(list(set(c.get("category") for c in all_courses if c.get("category"))))
            
            if search:
                search_lower = search.lower()
                all_courses = [c for c in all_courses if search_lower in (c.get("title") or "").lower()]
                
            if category:
                all_courses = [c for c in all_courses if c.get("category") == category]
                
            if status and status.lower() != "all":
                is_valid_filter = status.lower() == "enrolled"
                all_courses = [c for c in all_courses if c.get("is_coupon_valid") == is_valid_filter]
                
            total = len(all_courses)
            start_idx = (page - 1) * limit
            paged_courses = all_courses[start_idx:start_idx + limit]
            
            return {
                "items": paged_courses,
                "categories": categories,
                "total": total,
                "page": page,
                "pages": (total + limit - 1) // limit
            }
        except Exception:
            pass # Fallback to DB
            
    query = db.query(EnrolledCourse)
    
    if search:
        query = query.filter(EnrolledCourse.title.ilike(f"%{search}%"))
        
    if category:
        query = query.filter(EnrolledCourse.category == category)
        
    if status and status.lower() != "all":
        is_valid_filter = status.lower() == "enrolled"
        query = query.filter(EnrolledCourse.is_coupon_valid == is_valid_filter)
        
    total = query.count()
    courses = query.order_by(desc(EnrolledCourse.enrolled_at)).offset((page - 1) * limit).limit(limit).all()
    
    # Extract unique categories for the filter
    categories = [cat[0] for cat in db.query(EnrolledCourse.category).filter(EnrolledCourse.category.isnot(None)).distinct().all()]
    
    return {
        "items": [
            {
                "id": c.id,
                "title": c.title,
                "url": c.url,
                "coupon_code": c.coupon_code,
                "price": c.price,
                "category": c.category,
                "language": c.language,
                "rating": c.rating,
                "is_coupon_valid": c.is_coupon_valid,
                "enrolled_at": c.enrolled_at.isoformat() + "Z" if c.enrolled_at else None,
                "last_checked_at": c.last_checked_at.isoformat() + "Z" if c.last_checked_at else None
            } for c in courses
        ],
        "categories": categories,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }
