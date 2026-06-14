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
    return templates.TemplateResponse("pages/public_deals.html", {"request": request})

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
