"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


# ── Auth ──────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str


class CookieLoginRequest(BaseModel):
    access_token: str
    client_id: str
    csrf_token: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    display_name: Optional[str] = None
    currency: Optional[str] = None


# ── Settings ──────────────────────────────────────────
class SitesConfig(BaseModel):
    real_discount: bool = True
    courson: bool = True
    idownloadcoupons: bool = True
    e_next: bool = True
    discudemy: bool = True
    udemy_freebies: bool = True
    course_joiner: bool = True
    course_vania: bool = True


class SettingsUpdate(BaseModel):
    sites: Optional[dict] = None
    languages: Optional[dict] = None
    categories: Optional[dict] = None
    instructor_exclude: Optional[list[str]] = None
    title_exclude: Optional[list[str]] = None
    min_rating: Optional[float] = None
    course_update_threshold_months: Optional[int] = None
    save_txt: Optional[bool] = None
    discounted_only: Optional[bool] = None


class SettingsResponse(BaseModel):
    sites: dict
    languages: dict
    categories: dict
    instructor_exclude: list[str]
    title_exclude: list[str]
    min_rating: float
    course_update_threshold_months: int
    save_txt: bool
    discounted_only: bool

    class Config:
        from_attributes = True


# ── Enrollment ────────────────────────────────────────
class EnrollmentStartRequest(BaseModel):
    """Request to start an enrollment run."""
    pass  # Uses current user settings


class EnrollmentStatus(BaseModel):
    run_id: int
    status: str
    total_courses_found: int
    total_processed: int
    successfully_enrolled: int
    already_enrolled: int
    expired: int
    excluded: int
    amount_saved: float
    currency: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class CourseInfo(BaseModel):
    title: str
    url: str
    slug: Optional[str] = None
    course_id: Optional[str] = None
    coupon_code: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    language: Optional[str] = None
    rating: Optional[float] = None
    site_source: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    enrolled_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Dashboard ─────────────────────────────────────────
class DashboardStats(BaseModel):
    total_runs: int
    total_enrolled: int
    total_amount_saved: float
    currency: str
    total_already_enrolled: int
    total_expired: int
    total_excluded: int
    recent_runs: list[EnrollmentStatus]


class ScrapingProgress(BaseModel):
    site: str
    progress: int
    total: int
    done: bool
    error: Optional[str] = None


class EnrollmentProgress(BaseModel):
    run_id: int
    status: str
    total_courses: int
    processed: int
    successfully_enrolled: int
    already_enrolled: int
    expired: int
    excluded: int
    amount_saved: float
    current_course_title: Optional[str] = None
    current_course_url: Optional[str] = None
    scraping_progress: list[ScrapingProgress] = []
