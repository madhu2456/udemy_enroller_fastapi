from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.database import get_db, EnrolledCourse

router = APIRouter(prefix="/udemycoupons", tags=["Public Deals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def public_deals_page(request: Request):
    """Render the public deals dashboard page."""
    import os
    import json
    
    initial_courses = []
    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "public_deals.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                all_courses = json.load(f)
            # Only valid coupons for initial SSR
            valid_courses = [c for c in all_courses if c.get("is_coupon_valid")]
            initial_courses = valid_courses[:24]
        except Exception:
            pass
            
    return templates.TemplateResponse("pages/public_deals.html", {"request": request, "initial_courses": initial_courses})

@router.get("/api/coupons")
def get_public_coupons(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(24, ge=1, le=100),
    search: str = Query(None),
    category: str = Query(None),
    status: str = Query(None)
):
    """API endpoint to fetch coupons for the public dashboard."""
    import os
    import json
    
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
        except Exception as e:
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
